import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sound_detector_clean/classification_result.dart';
import 'package:sound_detector_clean/event_admission_controller.dart';
import 'package:sound_detector_clean/event_upload_queue.dart';
import 'package:sound_detector_clean/services/realtime_detection_state.dart';
import 'package:sound_detector_clean/target_sound_policy.dart';

Future<void> settle() => Future<void>.delayed(Duration.zero);

void main() {
  late List<Map<String, dynamic>> sent;
  late RealtimeDetectionState state;
  setUp(() {
    sent = [];
    state = RealtimeDetectionState(send: (value) async => sent.add(value));
    state.setConnected(true);
  });

  void inference(bool active, {double? confidence = 0.87}) => state.inference(
    session: state.session,
    active: active,
    observedAtMs: 123456,
    label: active ? 'Drone' : 'Car',
    confidence: confidence,
  );

  test(
    'target then non-target immediately reports both, including null score',
    () async {
      inference(true);
      await settle();
      inference(false, confidence: null);
      await settle();
      expect(sent.map((s) => s['active']), [true, false]);
      expect(sent.last['confidence'], isNull);
      expect(sent.last['label'], 'Car');
      expect(sent.last['observed_at_ms'], 123456);
    },
  );

  test('true to true reports every completed window', () async {
    for (var i = 0; i < 3; i++) {
      inference(true);
      await settle();
    }
    expect(sent.map((s) => s['sequence']), [1, 2, 3]);
    expect(sent.every((s) => s['active'] == true), isTrue);
  });

  test('sequence increases through 10, 11, 12 including false', () async {
    for (var i = 0; i < 12; i++) {
      inference(i.isEven);
      await settle();
    }
    expect(sent.skip(9).map((s) => s['sequence']), [10, 11, 12]);
  });

  test('false to false has no debounce or cooldown', () async {
    inference(false);
    await settle();
    inference(false);
    await settle();
    expect(sent.length, 2);
  });

  test(
    'offline buffers latest only and reconnect republishes a new sequence',
    () async {
      state.setConnected(false);
      inference(true);
      inference(false);
      expect(sent, isEmpty);
      expect(state.latest!['active'], false);
      state.setConnected(true);
      await settle();
      expect(sent.single['active'], false);
      expect(sent.single['sequence'], 3);
      expect(sent.single['observed_at_ms'], 123456);
    },
  );

  test('reconnect preserves inference time and sequence continues', () async {
    inference(true);
    await settle();
    state.setConnected(false);
    state.setConnected(true);
    await settle();
    expect(sent.last['sequence'], 2);
    expect(sent.last['observed_at_ms'], sent.first['observed_at_ms']);
  });

  test('stop sends false and rejects old in-flight inference session', () async {
    final oldSession = state.session;
    inference(true);
    await settle();
    state.stop(observedAtMs: 999);
    await settle();
    state.inference(session: oldSession, active: true, observedAtMs: 1000);
    // A window arriving during asynchronous microphone shutdown is rejected too.
    inference(true);
    await settle();
    expect(sent.length, 2);
    expect(sent.last['active'], false);
    expect(sent.last['sequence'], 2);
    state.startSession();
    inference(true);
    await settle();
    expect(sent.last['sequence'], 3);
    expect(sent.last['active'], true);
  });

  test('offline stop supersedes positive on reconnect', () async {
    state.setConnected(false);
    inference(true);
    state.stop(observedAtMs: 999);
    state.setConnected(true);
    await settle();
    expect(sent.single['active'], false);
  });

  test(
    'blocked transport coalesces pending state into one latest slot',
    () async {
      final blocked = Completer<void>();
      state = RealtimeDetectionState(
        send: (value) async {
          sent.add(value);
          if (sent.length == 1) await blocked.future;
        },
      );
      state.setConnected(true);
      inference(true);
      for (var i = 0; i < 1000; i++) {
        inference(i.isEven);
      }
      expect(sent.length, 1);
      blocked.complete();
      await settle();
      expect(sent.length, 2);
      expect(sent.last['sequence'], 1001);
      expect(sent.last['active'], false);
    },
  );

  test('send error is isolated from caller and future durable work', () async {
    state = RealtimeDetectionState(
      send: (_) async => throw StateError('offline'),
    );
    state.setConnected(true);
    inference(true);
    SharedPreferences.setMockInitialValues({});
    final queue = EventUploadQueue(preferenceKey: 'rt_failure_regression');
    await queue.enqueueEvent({'event_id': 'durable', 'path': 'original.wav'});
    expect((await queue.load()).single.eventJson['path'], 'original.wav');
    await queue.markMetadataUploaded('durable');
    expect((await queue.load()).single.state, 'audio_pending');
    await queue.markCompleted('durable');
    expect(await queue.load(), isEmpty);
    await settle();
    expect(state.latest!['active'], true);
    inference(false);
    expect(state.latest!['active'], false);
  });

  test(
    'old send failure does not disable a newly connected transport',
    () async {
      final blocked = Completer<void>();
      state = RealtimeDetectionState(
        send: (value) async {
          sent.add(value);
          if (sent.length == 1) await blocked.future;
        },
      );
      state.setConnected(true);
      inference(true);
      state.setConnected(false);
      state.setConnected(true);
      inference(false);
      blocked.completeError(StateError('old connection failed'));
      await settle();
      expect(sent.length, 2);
      expect(sent.last['active'], false);
      expect(sent.last['sequence'], 3);
    },
  );

  test('invalid score becomes null without suppressing negative', () async {
    inference(false, confidence: double.nan);
    await settle();
    expect(sent.single['confidence'], isNull);
    expect(sent.single['active'], false);
  });

  test(
    'original operational policy and event cooldown remain independent',
    () async {
      final admission = EventAdmissionController();
      final result = ClassificationResult.fromFiveClassScores(
        modelId: 'test',
        modelVersion: '1',
        scores: [0.3, 0.1, 0.4, 0.1, 0.1],
      );
      expect(
        isOperationalTargetLabel(result.operationalClass),
        result.isTarget,
      );
      expect(isOperationalTargetLabel('aircraft'), true);
      expect(isOperationalTargetLabel('drone'), true);
      expect(isOperationalTargetLabel('Drone'), false);
      expect(isOperationalTargetLabel('non_aircraft'), false);
      expect(
        admission
            .evaluate(deviceId: 'a', target: true, occurredAtMs: 0)
            .accepted,
        true,
      );
      inference(true);
      await settle();
      expect(
        admission
            .evaluate(deviceId: 'a', target: true, occurredAtMs: 1500)
            .accepted,
        false,
      );
      inference(true);
      await settle();
      inference(false);
      await settle();
      expect(sent.map((s) => s['active']), [true, true, false]);
      expect(admission.targetCooldownMs, 10000);
      expect(admission.collectionCooldownMs, 3000);
    },
  );
}
