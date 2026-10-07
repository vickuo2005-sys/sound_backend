import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sound_detector_clean/event_upload_queue.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  test('persists pending event upload lifecycle', () async {
    final queue = EventUploadQueue(preferenceKey: 'test_queue');
    await queue.enqueueEvent(<String, dynamic>{
      'event_id': 'event_001',
      'device_id': 'node_A01',
      'path': '/tmp/event.wav',
    });

    var items = await queue.load();
    expect(items, hasLength(1));
    expect(items.single.eventId, 'event_001');
    expect(items.single.state, 'metadata_pending');

    await queue.markMetadataUploaded('event_001');
    items = await queue.load();
    expect(items.single.metadataUploaded, isTrue);
    expect(items.single.state, 'audio_pending');

    await queue.recordFailure('event_001', 'upload_failed_500');
    items = await queue.load();
    expect(items.single.attempts, 1);
    expect(items.single.state, 'audio_retry_wait');
    expect(items.single.lastError, 'upload_failed_500');

    await queue.markCompleted('event_001');
    items = await queue.load();
    expect(items, isEmpty);
  });

  test('pending event preserves nested classification metadata', () async {
    final queue = EventUploadQueue(preferenceKey: 'test_classification_queue');
    final classification = <String, dynamic>{
      'schema_version': 'classification.v1',
      'model_label': 'Drone',
      'class_scores': <String, double>{
        'Airplane': 0.03,
        'Car': 0.02,
        'Drone': 0.92,
        'Electric_saw': 0.01,
        'Rainfall': 0.02,
      },
    };

    await queue.enqueueEvent(<String, dynamic>{
      'event_id': 'classified_event',
      'classification': classification,
    });

    final restored = (await queue.load()).single.eventJson;
    expect(restored['classification'], classification);
  });

  test('serializes concurrent queue mutations without losing events', () async {
    final queue = EventUploadQueue(preferenceKey: 'test_concurrent_queue');

    await Future.wait(
      List.generate(12, (index) {
        return queue.enqueueEvent(<String, dynamic>{
          'event_id': 'event_$index',
          'device_id': 'node_A01',
          'path': '/tmp/event_$index.wav',
        });
      }),
    );

    final items = await queue.load();
    expect(items, hasLength(12));
    expect(items.map((item) => item.eventId).toSet(), hasLength(12));
  });

  test('caps pending uploads to prevent an offline backlog storm', () async {
    final queue = EventUploadQueue(
      preferenceKey: 'test_capped_queue',
      maxPendingItems: 3,
    );

    for (var index = 0; index < 5; index += 1) {
      await queue.enqueueEvent(<String, dynamic>{
        'event_id': 'event_$index',
        'device_id': 'node_A01',
        'path': '/tmp/event_$index.wav',
      });
      await Future<void>.delayed(const Duration(milliseconds: 2));
    }

    final items = await queue.load();
    expect(items, hasLength(3));
    expect(
      items.map((item) => item.eventId),
      orderedEquals(<String>['event_2', 'event_3', 'event_4']),
    );
  });

  test('discards stale metadata sooner than uploaded metadata audio', () async {
    final queue = EventUploadQueue(preferenceKey: 'test_expiring_queue');
    await queue.enqueueEvent(<String, dynamic>{
      'event_id': 'metadata_stale',
      'device_id': 'node_A01',
      'path': '/tmp/metadata_stale.wav',
    });
    await queue.enqueueEvent(<String, dynamic>{
      'event_id': 'audio_still_fresh',
      'device_id': 'node_A01',
      'path': '/tmp/audio_still_fresh.wav',
    });
    await queue.markMetadataUploaded('audio_still_fresh');

    final itemsBefore = await queue.load();
    final createdAtMs = itemsBefore.first.createdAtMs;
    final expired = await queue.discardExpired(
      metadataMaxAgeMs: 30000,
      audioMaxAgeMs: 300000,
      nowMs: createdAtMs + 31000,
    );

    expect(expired.map((item) => item.eventId), contains('metadata_stale'));
    expect(
      expired.map((item) => item.eventId),
      isNot(contains('audio_still_fresh')),
    );
    final retained = await queue.load();
    expect(retained.map((item) => item.eventId), contains('audio_still_fresh'));
  });

  test('prioritizes due metadata before audio retries', () async {
    final queue = EventUploadQueue(preferenceKey: 'test_priority_queue');
    await queue.enqueueEvent(<String, dynamic>{
      'event_id': 'audio_pending',
      'device_id': 'node_A01',
      'path': '/tmp/audio_pending.wav',
    });
    await queue.markMetadataUploaded('audio_pending');
    await queue.enqueueEvent(<String, dynamic>{
      'event_id': 'metadata_pending',
      'device_id': 'node_A01',
      'path': '/tmp/metadata_pending.wav',
    });

    final due = await queue.dueItems(limit: 2);
    expect(due.first.eventId, 'metadata_pending');
    expect(due.last.eventId, 'audio_pending');
  });

  test('fast metadata lane starts HTTP before persistence completes', () async {
    final queue = EventUploadQueue(preferenceKey: 'test_fast_lane_order');
    final order = <String>[];

    final status = await queue.enqueueWithImmediateMetadataSend(
      <String, dynamic>{'event_id': 'fast_event', 'device_id': 'node_A01'},
      () async {
        order.add('http_started');
        await Future<void>.delayed(const Duration(milliseconds: 5));
        return 'uploaded';
      },
      onPersisted: () => order.add('persisted'),
    );

    expect(status, 'uploaded');
    expect(order.first, 'http_started');
    final items = await queue.load();
    expect(items.single.metadataUploaded, isTrue);
    expect(items.single.state, 'audio_pending');
  });

  test('fast metadata lane retains a failed request for retry', () async {
    final queue = EventUploadQueue(preferenceKey: 'test_fast_lane_retry');

    final status = await queue.enqueueWithImmediateMetadataSend(
      <String, dynamic>{'event_id': 'retry_event', 'device_id': 'node_A01'},
      () async => 'upload_failed_503',
    );

    expect(status, 'upload_failed_503');
    final items = await queue.load();
    expect(items.single.metadataUploaded, isFalse);
    expect(items.single.state, 'metadata_retry_wait');
    expect(items.single.attempts, 1);
    expect(items.single.lastError, 'upload_failed_503');
  });
}
