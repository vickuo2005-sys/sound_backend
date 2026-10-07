import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as path;
import 'package:sound_detector_clean/observation_retry_queue.dart';
import 'package:sound_detector_clean/observation_shadow.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class MutableClock {
  MutableClock(this.value);
  DateTime value;

  DateTime call() => value;

  void advance(Duration duration) {
    value = value.add(duration);
  }
}

Map<String, dynamic> observationPayload(
  int sequence, {
  String processSessionId = 'process-old',
}) {
  final eventTimeMs = 1787616000000 + sequence * 1500;
  return <String, dynamic>{
    'message_type': 'observation.v1',
    'schema_version': 1,
    'observation_id': 'obs_A01_${processSessionId}_$sequence',
    'device_id': 'A01',
    'observed_at': DateTime.fromMillisecondsSinceEpoch(
      eventTimeMs,
      isUtc: true,
    ).toIso8601String(),
    'event_time_ms': eventTimeMs,
    'sequence': sequence,
    'process_session_id': processSessionId,
    'label': 'drone',
    'confidence': 0.9,
    'aircraft_probability': 0.1,
    'rms_peak': 0.5,
    'avg_rms': 0.3,
    'estimated_peak_db': 78.0,
    'estimated_avg_db': 74.0,
    'location': <String, dynamic>{
      'source': 'cached_device_gps',
      'latitude': 25.033,
      'longitude': 121.565,
      'accuracy_m': 8.0,
    },
    'time_sync': null,
    'model_id': 'model-1',
    'model_name': 'Model 1',
    'ai_inference_time_ms': 42,
    'window_duration_ms': 3000,
    'hop_duration_ms': 1500,
    'sample_rate_hz': 16000,
    'audio_ref': null,
    'alert_candidate': true,
    'trace_id': 'obs_A01_${processSessionId}_$sequence',
    'classification': <String, dynamic>{
      'schema_version': 'classification.v1',
      'model_id': 'v1_1_0_flower_drone_audio',
      'model_version': '1.1.0',
      'model_label': 'Drone',
      'confidence': 0.92,
      'class_scores': <String, double>{
        'Airplane': 0.03,
        'Car': 0.02,
        'Drone': 0.92,
        'Electric_saw': 0.01,
        'Rainfall': 0.02,
      },
      'operational_class': 'drone',
      'aircraft_probability': 0.95,
      'is_target': true,
      'drone_subtype': null,
    },
  };
}

ObservationUploadResult uploadedResult() => const ObservationUploadResult(
  status: ObservationUploadStatus.uploaded,
  payloadBytes: 1000,
  estimatedRequestBytes: 1200,
  httpDurationMs: 10,
  statusCode: 202,
);

ObservationUploadResult networkFailure() => const ObservationUploadResult(
  status: ObservationUploadStatus.failed,
  payloadBytes: 1000,
  estimatedRequestBytes: 1200,
  httpDurationMs: 5,
  error: 'SocketException',
);

void main() {
  sqfliteFfiInit();

  late Directory temporaryDirectory;
  late String databasePath;
  late MutableClock clock;
  final openStores = <ObservationSqliteStore>[];

  ObservationSqliteStore newStore() {
    final store = ObservationSqliteStore(
      databasePath: databasePath,
      databaseFactoryOverride: databaseFactoryFfi,
    );
    openStores.add(store);
    return store;
  }

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'observation_retry_queue_test_',
    );
    databasePath = path.join(temporaryDirectory.path, 'queue.db');
    clock = MutableClock(DateTime.utc(2026, 8, 25, 12));
  });

  tearDown(() async {
    for (final store in openStores) {
      try {
        await store.close();
      } catch (_) {
        // A restart test may already have closed the store.
      }
    }
    openStores.clear();
    if (temporaryDirectory.existsSync()) {
      await temporaryDirectory.delete(recursive: true);
    }
  });

  test('queue persists before first send', () async {
    final store = newStore();
    var uploaderCalls = 0;
    var persistedBeforeSend = false;
    final dispatcher = ObservationRetryDispatcher(
      store: store,
      now: clock.call,
      autoDrain: false,
      uploader: (payload) async {
        uploaderCalls += 1;
        persistedBeforeSend = (await store.records()).isNotEmpty;
        return uploadedResult();
      },
    );

    await dispatcher.initialize();
    await dispatcher.enqueuePayload(observationPayload(1));

    expect(uploaderCalls, 0);
    expect((await store.records()).single.state, ObservationQueueState.pending);
    await dispatcher.drainNow();
    expect(persistedBeforeSend, isTrue);
    expect(await store.records(), isEmpty);
  });

  test('HTTP failure keeps observation and reconnect drains it', () async {
    final store = newStore();
    var online = false;
    final dispatcher = ObservationRetryDispatcher(
      store: store,
      now: clock.call,
      autoDrain: false,
      policy: const ObservationQueuePolicy(jitterRatio: 0),
      uploader: (_) async => online ? uploadedResult() : networkFailure(),
    );

    await dispatcher.initialize();
    await dispatcher.enqueuePayload(observationPayload(1));
    await dispatcher.drainNow();
    var records = await store.records();
    expect(records.single.state, ObservationQueueState.retryWait);
    expect(records.single.attemptCount, 1);

    online = true;
    await dispatcher.drainNow(forceNetworkProbe: true);
    records = await store.records();
    expect(records, isEmpty);
    final metrics = await dispatcher.snapshot();
    expect(metrics.retryTotal, 1);
    expect(metrics.retrySuccessTotal, 1);
    expect(metrics.uploadSuccessTotal, 1);
  });

  test('retry preserves the exact enqueue-time classification', () async {
    final store = newStore();
    final attemptedClassifications = <Map<String, dynamic>>[];
    var online = false;
    final dispatcher = ObservationRetryDispatcher(
      store: store,
      now: clock.call,
      autoDrain: false,
      policy: const ObservationQueuePolicy(jitterRatio: 0),
      uploader: (payload) async {
        attemptedClassifications.add(
          Map<String, dynamic>.from(payload['classification'] as Map),
        );
        return online ? uploadedResult() : networkFailure();
      },
    );
    final original = observationPayload(1);

    await dispatcher.initialize();
    await dispatcher.enqueuePayload(original);
    await dispatcher.drainNow();
    online = true;
    await dispatcher.drainNow(forceNetworkProbe: true);

    expect(attemptedClassifications, hasLength(2));
    expect(attemptedClassifications[0], original['classification']);
    expect(attemptedClassifications[1], original['classification']);
    expect(attemptedClassifications[1], attemptedClassifications[0]);
  });

  test(
    'App restart restores IN_FLIGHT and preserves original session',
    () async {
      final firstStore = newStore();
      final firstDispatcher = ObservationRetryDispatcher(
        store: firstStore,
        now: clock.call,
        autoDrain: false,
        uploader: (_) async => uploadedResult(),
      );
      await firstDispatcher.initialize();
      await firstDispatcher.enqueuePayload(
        observationPayload(1, processSessionId: 'original-session'),
      );
      final claimed = await firstStore.claimNextDue(
        nowMs: clock().millisecondsSinceEpoch,
      );
      expect(claimed?.state, ObservationQueueState.inFlight);
      await firstStore.close();

      final uploadedSessions = <String>[];
      final restartedStore = newStore();
      final restarted = ObservationRetryDispatcher(
        store: restartedStore,
        now: clock.call,
        autoDrain: false,
        currentProcessSessionId: 'new-process-session',
        uploader: (payload) async {
          uploadedSessions.add(payload['process_session_id'] as String);
          return uploadedResult();
        },
      );
      await restarted.initialize();
      await restarted.drainNow();

      expect(uploadedSessions, <String>['original-session']);
      expect((await restarted.snapshot()).recoveredAfterRestartTotal, 1);
      expect(await restartedStore.records(), isEmpty);
    },
  );

  test(
    'App restart counts persisted RETRY_WAIT rows from a previous session',
    () async {
      final firstStore = newStore();
      final firstDispatcher = ObservationRetryDispatcher(
        store: firstStore,
        now: clock.call,
        autoDrain: false,
        currentProcessSessionId: 'old-process-session',
        policy: const ObservationQueuePolicy(jitterRatio: 0),
        uploader: (_) async => networkFailure(),
      );
      await firstDispatcher.initialize();
      await firstDispatcher.enqueuePayload(
        observationPayload(1, processSessionId: 'old-process-session'),
      );
      await firstDispatcher.drainNow();
      expect(
        (await firstStore.records()).single.state,
        ObservationQueueState.retryWait,
      );
      await firstStore.close();

      final restartedStore = newStore();
      final restarted = ObservationRetryDispatcher(
        store: restartedStore,
        now: clock.call,
        autoDrain: false,
        currentProcessSessionId: 'new-process-session',
        uploader: (_) async => uploadedResult(),
      );
      await restarted.initialize();

      final snapshot = await restarted.snapshot();
      expect(snapshot.depth, 1);
      expect(snapshot.recoveredAfterRestartTotal, 1);
      expect(snapshot.toJson()['persisted_from_previous_process_total'], 1);
    },
  );

  test(
    'duplicate enqueue is idempotent and oldest pending sends first',
    () async {
      final store = newStore();
      final sent = <int>[];
      final dispatcher = ObservationRetryDispatcher(
        store: store,
        now: clock.call,
        autoDrain: false,
        uploader: (payload) async {
          sent.add(payload['sequence'] as int);
          return uploadedResult();
        },
      );
      await dispatcher.initialize();
      await dispatcher.enqueuePayload(observationPayload(1));
      await dispatcher.enqueuePayload(observationPayload(1));
      clock.advance(const Duration(milliseconds: 1));
      await dispatcher.enqueuePayload(observationPayload(2));
      clock.advance(const Duration(milliseconds: 1));
      await dispatcher.enqueuePayload(observationPayload(3));

      expect((await store.records()).length, 3);
      expect((await dispatcher.snapshot()).queuedTotal, 3);
      await dispatcher.drainNow();
      expect(sent, <int>[1, 2, 3]);
    },
  );

  test(
    'one poison record becomes permanent and does not block later rows',
    () async {
      final store = newStore();
      final attempted = <int>[];
      final dispatcher = ObservationRetryDispatcher(
        store: store,
        now: clock.call,
        autoDrain: false,
        uploader: (payload) async {
          final sequence = payload['sequence'] as int;
          attempted.add(sequence);
          if (sequence == 1) {
            return const ObservationUploadResult(
              status: ObservationUploadStatus.failed,
              payloadBytes: 1000,
              estimatedRequestBytes: 1200,
              httpDurationMs: 10,
              statusCode: 422,
              error: 'invalid_payload',
            );
          }
          return uploadedResult();
        },
      );
      await dispatcher.initialize();
      await dispatcher.enqueuePayload(observationPayload(1));
      clock.advance(const Duration(milliseconds: 1));
      await dispatcher.enqueuePayload(observationPayload(2));
      await dispatcher.drainNow();

      expect(attempted, <int>[1, 2]);
      final records = await store.records();
      expect(records.single.sequence, 1);
      expect(records.single.state, ObservationQueueState.failedPermanent);
      expect((await dispatcher.snapshot()).permanentFailureTotal, 1);
    },
  );

  test('expiry and storage bounds are explicit metrics', () async {
    final store = newStore();
    const policy = ObservationQueuePolicy(
      maxEntries: 2,
      maxBytes: 1024 * 1024,
      maxAge: Duration(seconds: 10),
    );
    final dispatcher = ObservationRetryDispatcher(
      store: store,
      now: clock.call,
      autoDrain: false,
      policy: policy,
      uploader: (_) async => uploadedResult(),
    );
    await dispatcher.initialize();
    await dispatcher.enqueuePayload(observationPayload(1));
    clock.advance(const Duration(milliseconds: 1));
    await dispatcher.enqueuePayload(observationPayload(2));
    clock.advance(const Duration(milliseconds: 1));
    await dispatcher.enqueuePayload(observationPayload(3));

    expect((await store.records()).map((record) => record.sequence), <int>[
      2,
      3,
    ]);
    expect((await dispatcher.snapshot()).overflowTotal, 1);

    clock.advance(const Duration(seconds: 11));
    await dispatcher.drainNow();
    expect(await store.records(), isEmpty);
    final metrics = await dispatcher.snapshot();
    expect(metrics.expiredTotal, 2);
    expect(metrics.depth, 0);
    expect(metrics.bytes, 0);
  });

  test('offline circuit uses bounded exponential retry delay', () async {
    final store = newStore();
    final dispatcher = ObservationRetryDispatcher(
      store: store,
      now: clock.call,
      autoDrain: false,
      policy: const ObservationQueuePolicy(jitterRatio: 0),
      uploader: (_) async => networkFailure(),
    );
    await dispatcher.initialize();
    await dispatcher.enqueuePayload(observationPayload(1));

    await dispatcher.drainNow();
    expect((await dispatcher.snapshot()).retryDelayMs, 1000);
    clock.advance(const Duration(seconds: 1));
    await dispatcher.drainNow();
    expect((await dispatcher.snapshot()).retryDelayMs, 2000);
    clock.advance(const Duration(seconds: 2));
    await dispatcher.drainNow();
    expect((await dispatcher.snapshot()).retryDelayMs, 4000);
  });
}
