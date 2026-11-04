import 'package:flutter/material.dart';
import 'benchmark/controller.dart';
import 'benchmark/stats.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BenchmarkApp());
}

class BenchmarkApp extends StatelessWidget {
  const BenchmarkApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Drone Audio Benchmark',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      colorSchemeSeed: const Color(0xff146C60),
    ),
    home: const BenchmarkPage(),
  );
}

class BenchmarkPage extends StatefulWidget {
  const BenchmarkPage({super.key});
  @override
  State<BenchmarkPage> createState() => _BenchmarkPageState();
}

class _BenchmarkPageState extends State<BenchmarkPage>
    with WidgetsBindingObserver {
  final controller = BenchmarkController();
  bool consent = false;
  String? error;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    controller.addListener(_update);
    controller.initialize().catchError((Object e) {
      if (mounted) setState(() => error = '$e');
    });
  }

  void _update() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      controller.cancel('app_backgrounded_or_locked');
    }
    if (state == AppLifecycleState.resumed) controller.retryUploads();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    controller.removeListener(_update);
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = controller;
    final result = c.batch.isEmpty
        ? <String, int?>{}
        : decide((c.batch['runs'] as List).cast<Map<String, dynamic>>());
    String hop(String key) =>
        result[key] == null ? '未找到通過複測的結果' : '${result[key]} ms';
    return PopScope(
      canPop: !c.running,
      child: Scaffold(
        appBar: AppBar(title: const Text('聲音偵測效能測試')),
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  Icon(
                    c.running
                        ? Icons.graphic_eq
                        : c.finished
                        ? Icons.check_circle_outline
                        : Icons.mic_none,
                    size: 72,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(height: 24),
                  Text(
                    '${c.device['brand'] ?? ''} ${c.device['model'] ?? '正在讀取手機型號'}',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 24),
                  if (error != null) Text('無法初始化：$error'),
                  if (c.running) ...[
                    const Text('正在分析手機效能'),
                    const SizedBox(height: 16),
                    LinearProgressIndicator(value: c.progress),
                    const SizedBox(height: 16),
                    Text(c.message),
                    const SizedBox(height: 16),
                    const Text('請保持此畫面開啟，測試可能需要數分鐘。切換 App 或鎖定螢幕會中止測試。'),
                    const SizedBox(height: 24),
                    OutlinedButton(
                      onPressed: c.cancel,
                      child: const Text('取消測試'),
                    ),
                  ] else if (c.finished) ...[
                    Text(
                      c.batch['status'] == 'completed'
                          ? '測試完成'
                          : '測試已停止（${c.batch['reason']}）',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 16),
                    Text('最低穩定 Hop：${hop('lowest_stable_hop')}'),
                    Text('建議 Hop：${hop('recommended_hop')}'),
                    const SizedBox(height: 16),
                    Text(c.upload),
                    const SizedBox(height: 16),
                    const Text(
                      '這是本機音訊與 AI 處理效能，不代表聲音出現到偵測的延遲。穩定性僅經本次至少 2 分鐘複測。',
                    ),
                    const SizedBox(height: 24),
                    FilledButton.icon(
                      onPressed: () async {
                        try {
                          await c.export();
                        } catch (e) {
                          if (context.mounted) {
                            ScaffoldMessenger.of(
                              context,
                            ).showSnackBar(SnackBar(content: Text('匯出失敗：$e')));
                          }
                        }
                      },
                      icon: const Icon(Icons.share),
                      label: const Text('匯出測試結果（CSV / JSON）'),
                    ),
                    OutlinedButton(
                      onPressed: () => setState(() {
                        c.finished = false;
                        consent = false;
                      }),
                      child: const Text('重新測試'),
                    ),
                  ] else ...[
                    const Text('使用真實麥克風與聲音辨識模型，測試這台手機的音訊處理效能。'),
                    const SizedBox(height: 16),
                    const Text(
                      '只蒐集手機型號、系統與硬體基本資訊、模型版本及效能數據。已設定伺服器的版本會自動上傳效能結果。錄音只作暫存，處理後刪除；不會上傳錄音、GPS 或身分資訊。',
                    ),
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      value: consent,
                      onChanged: (v) => setState(() => consent = v ?? false),
                      title: const Text('我同意使用麥克風及蒐集上述效能資料'),
                    ),
                    FilledButton(
                      onPressed: consent && c.store != null && error == null
                          ? c.start
                          : null,
                      child: const Text('開始測試'),
                    ),
                    const SizedBox(height: 16),
                    Text(c.message),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
