import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/event_admission_controller.dart';

void main() {
  test('coalesces overlapping target windows into one event', () {
    final controller = EventAdmissionController(
      targetCooldownMs: 10000,
      collectionCooldownMs: 3000,
    );

    expect(
      controller
          .evaluate(deviceId: 'node_A01', target: true, occurredAtMs: 100000)
          .accepted,
      isTrue,
    );

    final overlapping = controller.evaluate(
      deviceId: 'node_A01',
      target: true,
      occurredAtMs: 100500,
    );
    expect(overlapping.accepted, isFalse);
    expect(overlapping.remainingMs, 9500);

    expect(
      controller
          .evaluate(deviceId: 'node_A01', target: true, occurredAtMs: 110000)
          .accepted,
      isTrue,
    );
  });

  test('keeps admission state independent per device and event bucket', () {
    final controller = EventAdmissionController();

    expect(
      controller
          .evaluate(deviceId: 'node_A01', target: true, occurredAtMs: 100000)
          .accepted,
      isTrue,
    );
    expect(
      controller
          .evaluate(deviceId: 'node_A02', target: true, occurredAtMs: 100500)
          .accepted,
      isTrue,
    );
    expect(
      controller
          .evaluate(deviceId: 'node_A01', target: false, occurredAtMs: 100500)
          .accepted,
      isTrue,
    );
  });

  test('rejects delayed out-of-order windows', () {
    final controller = EventAdmissionController(targetCooldownMs: 10000);

    controller.evaluate(
      deviceId: 'node_A01',
      target: true,
      occurredAtMs: 200000,
    );

    final delayed = controller.evaluate(
      deviceId: 'node_A01',
      target: true,
      occurredAtMs: 190000,
    );
    expect(delayed.accepted, isFalse);
    expect(delayed.remainingMs, greaterThan(10000));
  });

  test('collection windows are limited to their own shorter cadence', () {
    final controller = EventAdmissionController(collectionCooldownMs: 3000);

    expect(
      controller
          .evaluate(deviceId: 'node_A01', target: false, occurredAtMs: 100000)
          .accepted,
      isTrue,
    );
    expect(
      controller
          .evaluate(deviceId: 'node_A01', target: false, occurredAtMs: 102999)
          .accepted,
      isFalse,
    );
    expect(
      controller
          .evaluate(deviceId: 'node_A01', target: false, occurredAtMs: 103000)
          .accepted,
      isTrue,
    );
  });
}
