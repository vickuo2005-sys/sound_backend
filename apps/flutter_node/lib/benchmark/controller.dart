import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import '../ai_sound_classifier.dart';
import 'stats.dart';
import 'store.dart';

String randomHex(int bytes) => List.generate(
  bytes,
  (_) => Random.secure().nextInt(256).toRadixString(16).padLeft(2, '0'),
).join();
String uuid() {
  final s = randomHex(16);
  return '${s.substring(0, 8)}-${s.substring(8, 12)}-4${s.substring(13, 16)}-a${s.substring(17, 20)}-${s.substring(20)}';
}

class BenchmarkController extends ChangeNotifier {
  static const channel = MethodChannel('sound_channel');
  static const endpoint = String.fromEnvironment('BENCHMARK_BASE_URL');
  final AiSoundClassifier classifier = AiSoundClassifier();
  final Stopwatch dartClock = Stopwatch()..start();
  BenchmarkStore? store;
  Map<String, dynamic> device = {}, session = {}, batch = {};
  String secret = '', message = '準備開始', upload = '結果會先保存在手機';
  bool running = false, finished = false, cancelled = false;
  double progress = 0;
  String? interruption;
  Map<String, dynamic>? activeRun, pending;
  bool processing = false;
  Future<void>? worker;
  Timer? retries;

  Future<void> initialize() async {
    channel.setMethodCallHandler(_event);
    device = Map<String, dynamic>.from(
      await channel.invokeMethod('benchmarkState') as Map,
    );
    store = await BenchmarkStore.open();
    await store!.recover();
    final previous = await store!.latest();
    if (previous != null) {
      session =
          jsonDecode(previous['session'] as String) as Map<String, dynamic>;
      batch = jsonDecode(previous['batch'] as String) as Map<String, dynamic>;
      finished = true;
    }
    await retryUploads();
    retries = Timer.periodic(
      const Duration(seconds: 30),
      (_) => unawaited(retryUploads()),
    );
    notifyListeners();
  }

  Future<void> retryUploads() async {
    if (store == null) return;
    await store!.retry(endpoint);
    final latest = await store!.latest();
    upload = latest?['uploaded'] == 1
        ? '已成功上傳'
        : endpoint.isEmpty
        ? '已保存在手機；此版本尚未設定收集伺服器'
        : '已保存在手機，等待上傳';
    notifyListeners();
  }

  Future<void> _delete(Map<String, dynamic>? event) async {
    final p = event?['path'];
    if (p is String) {
      try {
        final file = File(p);
        if (await file.exists()) await file.delete();
      } catch (_) {
        interruption = 'audio_cleanup_failed';
      }
    }
  }

  Future<void> _event(MethodCall call) async {
    if (call.method == 'audio_error' ||
        call.method == 'benchmark_interrupted' ||
        call.method == 'permission_denied') {
      interruption = call.method == 'benchmark_interrupted'
          ? '${call.arguments}'
          : call.method;
      return;
    }
    if (call.method != 'event_saved') return;
    final event = Map<String, dynamic>.from(call.arguments as Map);
    event['received_dart_us'] = dartClock.elapsedMicroseconds;
    if (activeRun == null ||
        event['benchmark_run_id'] != activeRun!['run_id']) {
      await _delete(event);
      return;
    }
    if (processing) {
      activeRun!['max_backlog'] = max(2, activeRun!['max_backlog'] as int);
      final previous = pending;
      pending = event;
      await _delete(previous);
      return;
    }
    processing = true;
    activeRun!['max_backlog'] = max(1, activeRun!['max_backlog'] as int);
    worker = _process(event);
    unawaited(worker);
  }

  Future<void> _process(Map<String, dynamic> first) async {
    Map<String, dynamic>? event = first;
    try {
      while (event != null) {
        final e = event;
        final run = activeRun;
        try {
          final queueMs =
              (dartClock.elapsedMicroseconds - (e['received_dart_us'] as int)) /
              1000;
          // Both acknowledgments are timestamped on Android elapsedRealtime.
          // They bound channel delivery and inference completion from above.
          final receivedNative = await channel.invokeMethod<int>(
            'benchmarkClock',
          );
          final result = await classifier.runOnWav(e['path'] as String);
          if (!result.success &&
              run != null &&
              !(run['errors'] as List).contains('inference_failed')) {
            (run['errors'] as List).add('inference_failed');
          }
          final finishedNative = await channel.invokeMethod<int>(
            'benchmarkClock',
          );
          if (run != null) {
            (run['samples'] as List).add(<String, dynamic>{
              'sequence': e['window_sequence'],
              'ready_native_ms': e['ready_native_ms'],
              'native_queue_ms': e['native_queue_delay_ms'],
              'native_save_ms': e['native_save_duration_ms'],
              // Includes Flutter pending time; report that overlap explicitly.
              'bridge_upper_ms': max(
                0,
                receivedNative! - (e['emit_native_ms'] as int),
              ),
              'flutter_queue_ms': queueMs,
              'preprocess_ms': classifier.lastPreprocessMs,
              'inference_ms': classifier.lastInferenceMs,
              'pipeline_upper_ms': max(
                0,
                finishedNative! - (e['ready_native_ms'] as int),
              ),
              'success': result.success,
            });
          }
        } catch (_) {
          interruption = 'pipeline_exception';
        } finally {
          await _delete(e);
        }
        event = pending;
        pending = null;
      }
    } finally {
      processing = false;
    }
  }

  void cancel([String reason = 'cancelled']) {
    if (!running) return;
    cancelled = true;
    interruption = reason;
    message = '正在停止並保存結果';
    notifyListeners();
  }

  Future<void> start() async {
    if (running) return;
    running = true;
    finished = false;
    cancelled = false;
    interruption = null;
    session = {};
    batch = {};
    secret = '';
    progress = 0;
    message = '正在準備麥克風及模型';
    notifyListeners();
    try {
      if (await channel.invokeMethod<bool>('benchmarkPermission') != true) {
        throw StateError('麥克風權限未允許');
      }
      await classifier.loadStrict(AiSoundClassifier.defaultModelId);
      final option = AiSoundClassifier.modelOptionForId(
        classifier.activeModelId,
      );
      final bytes = await rootBundle.load(option.assetPath);
      final modelHash = sha256
          .convert(
            bytes.buffer.asUint8List(bytes.offsetInBytes, bytes.lengthInBytes),
          )
          .toString();
      // No fallback allowed; exact same model/preprocessing as the monitoring default.
      if (classifier.activeModelId != AiSoundClassifier.defaultModelId) {
        throw StateError('model_mismatch');
      }
      await rootBundle
          .loadString(AiSoundClassifier.preclassifierLabelsAssetPath)
          .then(jsonDecode);
      secret = randomHex(32);
      session = {
        'session_id': uuid(),
        for (final key in [
          'brand',
          'model',
          'android_version',
          'abi',
          'cores',
          'memory_mb',
          'app_version',
        ])
          key: device[key],
        'model_id': classifier.activeModelId,
        'model_version': classifier.activeModelVersion,
        'model_sha256': modelHash,
        'model_metadata_sha256': sha256
            .convert(
              utf8.encode(
                await rootBundle.loadString(
                  AiSoundClassifier.preclassifierLabelsAssetPath,
                ),
              ),
            )
            .toString(),
        'pipeline_version': 'native-wav-ai.v1',
        'inference_settings': 'tflite_flutter-0.12.1-default-options',
        'input_shape': classifier.inputShape,
        'output_shape': classifier.outputShape,
        'started_at': DateTime.now().toUtc().toIso8601String(),
      };
      batch = {
        'session_id': session['session_id'],
        'completed_at': DateTime.now().toUtc().toIso8601String(),
        'status': 'interrupted',
        'reason': 'in_progress',
        'criteria_version': criteriaVersion,
        'runs': <Map<String, dynamic>>[],
      };
      await _checkpoint();
      final candidates = <int>[];
      var consecutiveFailures = 0;
      for (
        var i = 0;
        i < benchmarkHops.length && !cancelled && interruption == null;
        i++
      ) {
        final hop = benchmarkHops[i];
        message = '正在分析手機效能（${i + 1}/${benchmarkHops.length}）';
        progress = i / (benchmarkHops.length + 2);
        notifyListeners();
        await _run(hop, 'warmup');
        if (cancelled || interruption != null) break;
        final run = await _run(hop, 'survey');
        await _checkpoint();
        if (evaluateRun(run)['passed'] == true) {
          candidates.add(hop);
          consecutiveFailures = 0;
        } else {
          consecutiveFailures++;
        }
        if (consecutiveFailures >= 2) break;
      }
      for (final hop in candidates.reversed) {
        if (cancelled || interruption != null) break;
        message = '正在進行較長時間的穩定性複測';
        progress = .85;
        notifyListeners();
        await _run(hop, 'warmup');
        if (cancelled || interruption != null) break;
        final run = await _run(hop, 'confirmation');
        await _checkpoint();
        // A recommendation also requires a confirmed 20% timing margin.
        if (evaluateRun(run)['recommended'] == true) break;
      }
      batch['status'] = cancelled
          ? (interruption == 'cancelled' ? 'cancelled' : 'interrupted')
          : interruption != null
          ? 'failed'
          : 'completed';
      batch['reason'] =
          interruption ??
          (decide(
                    (batch['runs'] as List).cast<Map<String, dynamic>>(),
                  )['lowest_stable_hop'] ==
                  null
              ? 'no_confirmed_stable_hop'
              : 'completed');
      await _checkpoint();
      finished = true;
      progress = 1;
      message = '測試完成';
    } catch (e) {
      message = '測試未完成：$e';
      if (batch.isNotEmpty && secret.isNotEmpty) {
        batch['status'] = 'failed';
        batch['reason'] = 'controller_error';
        try {
          await _checkpoint();
          finished = true;
        } catch (_) {
          message = '結果儲存失敗：$e';
        }
      }
    } finally {
      try {
        await channel.invokeMethod('benchmarkStop');
      } catch (_) {
        /* surfaced by the run */
      }
      classifier.close();
      running = false;
      notifyListeners();
      unawaited(retryUploads());
    }
  }

  Future<void> _checkpoint() async {
    batch['completed_at'] = DateTime.now().toUtc().toIso8601String();
    // Freeze counts and samples before any database await lets inference append.
    final snapshot = jsonDecode(jsonEncode(batch)) as Map<String, dynamic>;
    await store!.save(session, snapshot, secret);
  }

  Future<Map<String, dynamic>> _run(int hop, String phase) async {
    final run = <String, dynamic>{
      'run_id': uuid(),
      'hop_ms': hop,
      'window_ms': 3000,
      'phase': phase == 'warmup' ? 'survey' : phase,
      'duration_ms': 0,
      'generated': 0,
      'processed': 0,
      'dropped': 0,
      'max_backlog': 0,
      'thermal_max': null,
      'cpu_ms': null,
      'errors': <String>[],
      'samples': <Map<String, dynamic>>[],
    };
    activeRun = run;
    if (phase != 'warmup') (batch['runs'] as List).add(run);
    final timer = Stopwatch()..start();
    var lastCheckpointMs = 0;
    Map<String, dynamic>? state;
    try {
      final actual = await channel.invokeMapMethod<String, dynamic>(
        'benchmarkStart',
        {'hop_ms': hop, 'run_id': run['run_id']},
      );
      if (actual?['hop_ms'] != hop || actual?['run_id'] != run['run_id']) {
        throw StateError('native_configuration_mismatch');
      }
      final target = phase == 'warmup'
          ? 3
          : phase == 'confirmation'
          ? 60
          : 30;
      final maxMs = phase == 'confirmation'
          ? 180000
          : phase == 'warmup'
          ? 30000
          : 90000;
      while (!cancelled &&
          interruption == null &&
          timer.elapsedMilliseconds < maxMs) {
        await Future<void>.delayed(const Duration(milliseconds: 500));
        state = await channel.invokeMapMethod<String, dynamic>(
          'benchmarkState',
        );
        final thermal = state?['thermal'] as int?;
        if (thermal != null) {
          run['thermal_max'] = max(thermal, (run['thermal_max'] as int?) ?? 0);
        }
        if (thermal != null && thermal >= 3) {
          interruption = 'severe_thermal';
          break;
        }
        final samples = run['samples'] as List;
        if (phase != 'warmup' &&
            timer.elapsedMilliseconds - lastCheckpointMs >= 5000) {
          _updateRunCounts(run, state, timer.elapsedMilliseconds);
          await _checkpoint();
          lastCheckpointMs = timer.elapsedMilliseconds;
        }
        if (samples.length >= target &&
            (phase != 'confirmation' || timer.elapsedMilliseconds >= 120000)) {
          break;
        }
        if (samples.length >= 10 && phase != 'warmup') {
          final p = summarize(
            samples.map((s) => s['pipeline_upper_ms'] as num),
          );
          if (p!['p95']! > 2 * hop ||
              samples.where((s) => s['success'] != true).length >= 2) {
            break;
          }
        }
      }
    } catch (_) {
      interruption = 'native_pipeline_error';
    } finally {
      try {
        state = await channel.invokeMapMethod<String, dynamic>('benchmarkStop');
      } catch (_) {
        interruption = 'native_stop_failed';
      }
      // Stop acknowledgment follows the native writer barrier; drain Dart inference too.
      await worker;
      activeRun = null;
      pending = null;
    }
    _updateRunCounts(run, state, timer.elapsedMilliseconds);
    if (interruption != null) (run['errors'] as List).add(interruption!);
    return run;
  }

  void _updateRunCounts(
    Map<String, dynamic> run,
    Map<String, dynamic>? state,
    int elapsedMs,
  ) {
    run['duration_ms'] = elapsedMs;
    run['processed'] = (run['samples'] as List).length;
    run['generated'] = max(
      (state?['generated'] as int?) ?? 0,
      run['processed'] as int,
    );
    run['dropped'] = (run['generated'] as int) - (run['processed'] as int);
    run['max_backlog'] = max(
      run['max_backlog'] as int,
      (state?['max_backlog'] as int?) ?? 0,
    );
    run['cpu_ms'] = state?['cpu_ms'];
  }

  Future<void> export() async {
    final paths = await store!.export(session, batch);
    await channel.invokeMethod('benchmarkShare', paths);
  }

  @override
  void dispose() {
    retries?.cancel();
    super.dispose();
  }
}
