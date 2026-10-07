import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/ui/models/event_view_data.dart';
import 'package:sound_detector_clean/ui/models/sound_level_reading.dart';
import 'package:sound_detector_clean/ui/screens/events_view.dart';
import 'package:sound_detector_clean/ui/screens/monitor_view.dart';
import 'package:sound_detector_clean/ui/screens/system_view.dart';
import 'package:sound_detector_clean/ui/theme/app_theme.dart';
import 'package:sound_detector_clean/ui/widgets/classification_card.dart';
import 'package:sound_detector_clean/ui/widgets/event_list_item.dart';
import 'package:sound_detector_clean/ui/widgets/status_badge.dart';
import 'package:sound_detector_clean/ui/widgets/system_health_strip.dart';

void main() {
  Widget app(Widget child, {bool dark = false}) {
    return MaterialApp(
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: dark ? ThemeMode.dark : ThemeMode.light,
      home: Scaffold(body: SafeArea(child: child)),
    );
  }

  List<HealthStatusItem> healthyItems({int queueDepth = 0}) {
    return [
      const HealthStatusItem(
        label: '後端',
        detail: '已連線',
        icon: Icons.cloud_done,
        level: OperationalStatusLevel.healthy,
      ),
      const HealthStatusItem(
        label: 'GPS',
        detail: '±4.2 m',
        icon: Icons.location_on,
        level: OperationalStatusLevel.healthy,
      ),
      const HealthStatusItem(
        label: 'AI',
        detail: '已載入',
        icon: Icons.memory,
        level: OperationalStatusLevel.healthy,
      ),
      HealthStatusItem(
        label: '待傳',
        detail: '$queueDepth 筆待傳',
        icon: queueDepth == 0 ? Icons.sync_disabled : Icons.sync,
        level: queueDepth == 0
            ? OperationalStatusLevel.healthy
            : OperationalStatusLevel.warning,
      ),
    ];
  }

  MonitorView monitor({
    bool listening = false,
    String deviceId = 'node_A01',
    String classification = 'N/A',
    String statusLabel = '待命',
    IconData statusIcon = Icons.pause_circle_outline,
    OperationalStatusLevel statusLevel = OperationalStatusLevel.neutral,
    List<HealthStatusItem>? healthItems,
    ValueNotifier<SoundLevelReading>? soundLevel,
    String? listeningTime,
  }) {
    return MonitorView(
      deviceId: deviceId,
      statusLabel: statusLabel,
      statusIcon: statusIcon,
      statusLevel: statusLevel,
      healthItems: healthItems ?? healthyItems(),
      isListening: listening,
      listeningTime: listeningTime ?? (listening ? '00:12:43' : '00:00:00'),
      soundLevel:
          soundLevel ??
          ValueNotifier(
            SoundLevelReading(
              rms: listening ? 2048 : 0,
              estimatedDb: listening ? 70.9 : null,
            ),
          ),
      classificationLabel: classification,
      classificationConfidence: classification == 'N/A' ? null : 0.92,
      aircraftProbability: classification == 'N/A' ? null : 0.95,
      latestEvent: null,
      onOpenSystem: () {},
      onOpenEvents: () {},
      onToggleListening: () {},
    );
  }

  const sampleEvent = EventViewData(
    eventId: 'event-001',
    rawLabel: 'Drone',
    isTarget: true,
    time: '14:32:18',
    deviceId: 'node_A01',
    metadataUploadStatus: 'uploaded',
    localAudioPath: '/tmp/event.wav',
    audioAvailable: true,
    confidence: 0.92,
    aircraftProbability: 0.95,
    estimatedPeakDb: 80.6,
    estimatedAvgDb: 76.2,
    latitude: 25.033,
    longitude: 121.5654,
    gpsAccuracyM: 4.2,
  );

  SystemView systemView(
    TextEditingController controller, {
    ThemeMode themeMode = ThemeMode.dark,
    ValueChanged<ThemeMode>? onThemeModeChanged,
  }) {
    return SystemView(
      deviceIdController: controller,
      savedDeviceId: 'node_A01',
      isListening: false,
      dedicatedNodeMode: true,
      onSaveDeviceId: () {},
      selectedModelId: 'v1',
      modelOptions: const [SystemModelOption(id: 'v1', name: '預分類器 V1')],
      onModelChanged: (_) {},
      modelStatus: '已就緒',
      sampleRateHz: 16000,
      windowMs: 3000,
      hopMs: 1500,
      uploadMode: 'detection_only',
      onUploadModeChanged: (_) {},
      connectivity: const [
        SystemStatusData(
          label: '後端',
          value: '已連線',
          icon: Icons.check_circle,
          level: OperationalStatusLevel.healthy,
        ),
        SystemStatusData(
          label: '節點 WebSocket',
          value: '重新連線中',
          icon: Icons.sync,
          level: OperationalStatusLevel.warning,
        ),
        SystemStatusData(
          label: '待傳佇列',
          value: '0 筆待傳',
          icon: Icons.check_circle,
          level: OperationalStatusLevel.healthy,
        ),
      ],
      automation: const [SystemInfoData(label: '自動啟動', value: '未啟用')],
      diagnostics: const [
        SystemInfoData(label: 'GPS 原始位置', value: '25.033, 121.5654'),
      ],
      themeMode: themeMode,
      onThemeModeChanged: onThemeModeChanged ?? (_) {},
      onUploadLatestWav: () {},
      onClearLocalRecords: () {},
    );
  }

  testWidgets('Monitor stopped has one canonical standby presentation', (
    tester,
  ) async {
    await tester.pumpWidget(app(monitor()));

    expect(find.text('待命'), findsOneWidget);
    expect(find.text('聲音監聽\n未啟動'), findsOneWidget);
    expect(find.text('00:00:00'), findsOneWidget);
    expect(find.text('尚未取得聲音訊號'), findsOneWidget);
    expect(find.text('開始監聽'), findsOneWidget);
    expect(find.text('已停止'), findsNothing);
    expect(find.byIcon(Icons.play_arrow_rounded), findsOneWidget);
  });

  testWidgets('Monitor listening shows duration and live level meter', (
    tester,
  ) async {
    await tester.pumpWidget(
      app(
        monitor(
          listening: true,
          statusLabel: '監聽中',
          statusIcon: Icons.hearing,
          statusLevel: OperationalStatusLevel.healthy,
        ),
      ),
    );

    expect(find.text('正在監聽'), findsOneWidget);
    expect(find.text('00:12:43'), findsOneWidget);
    expect(find.text('70.9'), findsOneWidget);
    expect(find.text('dB 估算'), findsOneWidget);
    expect(find.byKey(const ValueKey('live-level-meter')), findsOneWidget);
    expect(find.text('停止監聽'), findsOneWidget);
  });

  testWidgets(
    'Monitor elapsed advances while listening and resets after stop',
    (tester) async {
      await tester.pumpWidget(
        app(
          monitor(
            listening: true,
            listeningTime: '00:00:01',
            statusLabel: '監聽中',
            statusIcon: Icons.hearing,
            statusLevel: OperationalStatusLevel.healthy,
          ),
        ),
      );
      expect(find.text('00:00:01'), findsOneWidget);

      await tester.pumpWidget(
        app(
          monitor(
            listening: true,
            listeningTime: '00:00:02',
            statusLabel: '監聽中',
            statusIcon: Icons.hearing,
            statusLevel: OperationalStatusLevel.healthy,
          ),
        ),
      );
      expect(find.text('00:00:02'), findsOneWidget);

      await tester.pumpWidget(app(monitor(listeningTime: '00:00:00')));
      expect(find.text('00:00:00'), findsOneWidget);
      expect(find.text('開始監聽'), findsOneWidget);
    },
  );

  testWidgets('Drone target uses icon and 目標 text, not color alone', (
    tester,
  ) async {
    await tester.pumpWidget(
      app(
        monitor(
          listening: true,
          classification: 'Drone',
          statusLabel: '目標偵測',
          statusIcon: Icons.notification_important,
          statusLevel: OperationalStatusLevel.target,
        ),
      ),
    );

    expect(find.text('Drone'), findsOneWidget);
    expect(find.text('無人機聲音'), findsOneWidget);
    expect(find.text('目標'), findsOneWidget);
    expect(find.text('TARGET／目標'), findsNothing);
    expect(find.text('TARGET'), findsNothing);
    expect(find.text('信心值'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('target-confidence-meter')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('classification-icon-Drone')),
      findsOneWidget,
    );
    expect(find.byIcon(Icons.notification_important), findsWidgets);
  });

  testWidgets('Backend offline and pending queue keep Monitor operational', (
    tester,
  ) async {
    await tester.pumpWidget(
      app(
        monitor(
          healthItems: const [
            HealthStatusItem(
              label: '後端',
              detail: '無法連線',
              icon: Icons.cloud_off,
              level: OperationalStatusLevel.error,
            ),
            HealthStatusItem(
              label: 'GPS',
              detail: '±27 m',
              icon: Icons.location_on,
              level: OperationalStatusLevel.warning,
            ),
            HealthStatusItem(
              label: 'AI',
              detail: '已就緒',
              icon: Icons.memory,
              level: OperationalStatusLevel.healthy,
            ),
            HealthStatusItem(
              label: '待傳',
              detail: '23 筆待傳',
              icon: Icons.sync,
              level: OperationalStatusLevel.warning,
            ),
          ],
        ),
      ),
    );

    expect(find.text('無法連線'), findsOneWidget);
    expect(find.byIcon(Icons.cloud_off), findsOneWidget);
    expect(find.text('23 筆待傳'), findsOneWidget);
    expect(find.byIcon(Icons.sync), findsOneWidget);
    expect(find.text('開始監聽'), findsOneWidget);
  });

  testWidgets('Monitor primary information is visible at 360 by 800', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(360, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(app(monitor(listening: true)));

    for (final key in const [
      ValueKey('node-identity-header'),
      ValueKey('live-detection-card'),
      ValueKey('classification-result-card'),
      ValueKey('system-health-strip'),
      ValueKey('latest-event-card'),
      ValueKey('monitor-primary-action'),
    ]) {
      expect(find.byKey(key).hitTestable(), findsOneWidget);
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('Events renders an empty state', (tester) async {
    await tester.pumpWidget(
      app(
        EventsView(
          events: const [],
          filter: EventFilter.all,
          playingEventId: null,
          onFilterChanged: (_) {},
          onOpen: (_) {},
          onPlay: (_) {},
        ),
      ),
    );

    expect(find.text('尚無事件'), findsOneWidget);
    expect(find.byIcon(Icons.inbox_outlined), findsOneWidget);
  });

  testWidgets('Events compact row shows classification, time, and upload', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(360, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      app(
        EventListItem(
          event: sampleEvent,
          isPlaying: false,
          onTap: () {},
          onPlay: () {},
        ),
      ),
    );

    final row = find.byKey(const ValueKey('event-row-event-001'));
    expect(find.text('Drone · 無人機聲音'), findsOneWidget);
    expect(find.textContaining('14:32:18'), findsOneWidget);
    expect(find.text('已上傳'), findsOneWidget);
    expect(find.text('目標'), findsOneWidget);
    expect(find.text('TARGET／目標'), findsNothing);
    expect(tester.getSize(row).height, inInclusiveRange(88, 110));
    expect(find.byIcon(Icons.delete_outline), findsNothing);
  });

  testWidgets('System diagnostics content is not built until expanded', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(500, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final controller = TextEditingController(text: 'node_A01');
    addTearDown(controller.dispose);

    await tester.pumpWidget(app(systemView(controller)));

    expect(
      find.byKey(const ValueKey('system-diagnostics-content')),
      findsNothing,
    );
    expect(find.text('GPS 原始位置'), findsNothing);

    final header = find.byKey(const ValueKey('system-diagnostics-header'));
    await tester.ensureVisible(header);
    await tester.tap(header);
    await tester.pump();

    expect(
      find.byKey(const ValueKey('system-diagnostics-content')),
      findsOneWidget,
    );
    expect(find.text('GPS 原始位置'), findsOneWidget);
  });

  testWidgets('System default has no placeholder or eager expansion block', (
    tester,
  ) async {
    final controller = TextEditingController(text: 'node_A01');
    addTearDown(controller.dispose);

    await tester.pumpWidget(app(systemView(controller)));

    expect(find.byType(Placeholder), findsNothing);
    expect(find.byType(ExpansionTile), findsNothing);
    expect(
      find.byKey(const ValueKey('system-diagnostics-content')),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('System uses Chinese connectivity labels', (tester) async {
    await tester.binding.setSurfaceSize(const Size(500, 1000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final controller = TextEditingController(text: 'node_A01');
    addTearDown(controller.dispose);

    await tester.pumpWidget(app(systemView(controller)));
    await tester.ensureVisible(find.text('重新連線中'));
    await tester.pump();

    expect(find.text('已連線'), findsOneWidget);
    expect(find.text('重新連線中'), findsOneWidget);
    expect(find.text('0 筆待傳'), findsOneWidget);
  });

  testWidgets('System theme selector reports the selected mode', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(360, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final controller = TextEditingController(text: 'node_A01');
    addTearDown(controller.dispose);
    ThemeMode? selectedMode;

    await tester.pumpWidget(
      app(
        systemView(
          controller,
          onThemeModeChanged: (mode) => selectedMode = mode,
        ),
      ),
    );

    expect(find.text('深色'), findsOneWidget);
    expect(find.text('系統'), findsOneWidget);
    expect(find.text('跟隨系統'), findsNothing);
    expect(find.text('淺色'), findsOneWidget);
    await tester.tap(find.text('系統'));
    await tester.pump();
    expect(selectedMode, ThemeMode.system);
    expect(tester.takeException(), isNull);
  });

  testWidgets('System only shows saved Node ID helper after input changes', (
    tester,
  ) async {
    final controller = TextEditingController(text: 'node_A01');
    addTearDown(controller.dispose);

    await tester.pumpWidget(app(systemView(controller)));
    expect(find.textContaining('已儲存節點 ID'), findsNothing);
    expect(find.byKey(const ValueKey('system-node-id-unsaved')), findsNothing);

    await tester.enterText(
      find.byKey(const ValueKey('system-node-id-field')),
      'node_A02',
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey('system-node-id-unsaved')),
      findsOneWidget,
    );
    expect(find.textContaining('目前已儲存：node_A01'), findsOneWidget);
  });

  testWidgets('RMS ValueNotifier can be disposed after Monitor removal', (
    tester,
  ) async {
    final notifier = ValueNotifier(
      const SoundLevelReading(rms: 2048, estimatedDb: 70.9),
    );

    await tester.pumpWidget(
      app(monitor(listening: true, soundLevel: notifier)),
    );
    notifier.value = const SoundLevelReading(rms: 4096, estimatedDb: 76.9);
    await tester.pump();
    await tester.pumpWidget(app(const SizedBox.shrink()));
    notifier.dispose();

    expect(tester.takeException(), isNull);
  });

  testWidgets('dark operational theme renders Monitor', (tester) async {
    await tester.pumpWidget(app(monitor(listening: true), dark: true));

    final context = tester.element(
      find.byKey(const ValueKey('node-identity-header')),
    );
    expect(Theme.of(context).brightness, Brightness.dark);
    expect(Theme.of(context).scaffoldBackgroundColor, const Color(0xFF0B1220));
    expect(find.byKey(const ValueKey('live-level-meter')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('long Node ID does not overflow at 360 px', (tester) async {
    await tester.binding.setSurfaceSize(const Size(360, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      app(
        monitor(
          deviceId:
              'node_A01-with-a-very-long-field-deployment-identifier-2026',
        ),
      ),
    );

    expect(find.textContaining('A01-with-a-very-long'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('ClassificationCard supports every declared 5-class label', (
    tester,
  ) async {
    const expected = <String, String>{
      'Airplane': '航空器聲音',
      'Car': '車輛聲音',
      'Drone': '無人機聲音',
      'Electric_saw': '電鋸聲音',
      'Rainfall': '降雨聲音',
    };

    for (final entry in expected.entries) {
      await tester.pumpWidget(
        app(ClassificationCard(label: entry.key, confidence: 0.82)),
      );
      expect(find.text(entry.value), findsOneWidget);
    }
  });
}
