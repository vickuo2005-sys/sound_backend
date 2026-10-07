import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sound_detector_clean/event_admission_controller.dart';
import 'package:sound_detector_clean/classification_result.dart';
import 'package:sound_detector_clean/observation_shadow.dart';

class RecordingObservationClient extends http.BaseClient {
  int requestCount = 0;
  Map<String, dynamic>? lastPayload;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requestCount += 1;
    lastPayload =
        jsonDecode(await request.finalize().bytesToString())
            as Map<String, dynamic>;
    return http.StreamedResponse(
      Stream<List<int>>.value(utf8.encode('{"status":"accepted"}')),
      202,
    );
  }
}

ObservationShadowPayload payloadFor(ObservationIdentity identity) {
  return ObservationShadowPayload(
    identity: identity,
    deviceId: 'A01',
    observedAt: '2026-08-25T00:00:00Z',
    eventTimeMs: 1000 + identity.sequence * 1500,
    label: 'drone',
    confidence: 0.91,
    aircraftProbability: 0.02,
    rmsPeak: 0.5,
    avgRms: 0.3,
    estimatedPeakDb: 78,
    estimatedAvgDb: 74,
    nodePositionSource: 'cached_device_gps',
    latitude: 25.033,
    longitude: 121.565,
    gpsAccuracyM: 8,
    timeSync: const ObservationTimeSyncSnapshot(
      version: 1,
      quality: 'good',
      offsetMs: 12.5,
      rttMs: 20,
      ageMs: 1000,
      deviceWallClockMs: 1787616000000,
      deviceMonotonicMs: 1234.5,
      monotonicSessionId: 'process-1',
    ),
    modelId: 'v1_1_0_flower_drone_audio',
    modelName: 'V1.1.0',
    aiInferenceTimeMs: 42,
    windowDurationMs: 3000,
    hopDurationMs: 1500,
    sampleRateHz: 16000,
    classification: ClassificationResult.fromFiveClassScores(
      modelId: 'v1_1_0_flower_drone_audio',
      modelVersion: '1.1.0',
      scores: const <double>[0.03, 0.02, 0.92, 0.01, 0.02],
    ),
  );
}

void main() {
  test('observation sequence is monotonic within one device process', () {
    final sequence = ObservationSequence(processSessionId: 'process-1');
    final first = sequence.next('A01');
    final second = sequence.next('A01');
    final third = sequence.next('A01');

    expect([first.sequence, second.sequence, third.sequence], [1, 2, 3]);
    expect(first.observationId, 'obs_A01_process-1_1');
    expect(second.observationId, 'obs_A01_process-1_2');
  });

  test('observation sequence domains are independent per device', () {
    final sequence = ObservationSequence(processSessionId: 'process-1');

    expect(sequence.next('A01').sequence, 1);
    expect(sequence.next('A02').sequence, 1);
    expect(sequence.next('A01').sequence, 2);
    expect(sequence.lastSequenceForDevice('A01'), 2);
    expect(sequence.lastSequenceForDevice('A02'), 1);
  });

  test('process restart creates a distinct identity and restarts sequence', () {
    final firstProcess = ObservationSequence(processSessionId: 'process-1');
    final secondProcess = ObservationSequence(processSessionId: 'process-2');

    expect(firstProcess.next('A01').sequence, 1);
    expect(firstProcess.next('A01').sequence, 2);
    final restarted = secondProcess.next('A01');

    expect(restarted.sequence, 1);
    expect(restarted.processSessionId, 'process-2');
    expect(restarted.observationId, isNot('obs_A01_process-1_1'));
  });

  test('cooldown rejected target still has an independent observation', () {
    final sequence = ObservationSequence(processSessionId: 'process-1');
    final admission = EventAdmissionController(targetCooldownMs: 10000);
    final observations = <ObservationShadowPayload>[];

    for (final eventTimeMs in [1000, 2500]) {
      observations.add(payloadFor(sequence.next('A01')));
      admission.evaluate(
        deviceId: 'A01',
        target: true,
        occurredAtMs: eventTimeMs,
      );
    }

    final rejected = admission.evaluate(
      deviceId: 'A01',
      target: true,
      occurredAtMs: 4000,
    );
    observations.add(payloadFor(sequence.next('A01')));

    expect(rejected.accepted, isFalse);
    expect(observations.map((item) => item.identity.sequence), [1, 2, 3]);
  });

  test('shadow upload is lightweight and contains no audio fields', () async {
    final transport = RecordingObservationClient();
    final client = ObservationShadowClient(enabled: true, client: transport);
    final sequence = ObservationSequence(processSessionId: 'process-1');

    final status = await client.upload(
      uri: Uri.parse('https://example.test/observations/shadow'),
      uploadToken: 'shadow-token',
      observation: payloadFor(sequence.next('A01')),
    );

    expect(status, ObservationUploadStatus.uploaded);
    expect(transport.requestCount, 1);
    expect(transport.lastPayload?['message_type'], 'observation.v1');
    expect(transport.lastPayload?['sequence'], 1);
    expect(
      (transport.lastPayload?['classification'] as Map)['class_scores'],
      <String, double>{
        'Airplane': 0.03,
        'Car': 0.02,
        'Drone': 0.92,
        'Electric_saw': 0.01,
        'Rainfall': 0.02,
      },
    );
    expect(
      (transport.lastPayload?['time_sync'] as Map)['device_wall_clock_ms'],
      1787616000000,
    );
    final serialized = jsonEncode(transport.lastPayload);
    for (final forbidden in [
      'audio_path',
      'audio_file_name',
      'audio_format',
      'tdoa_clip',
      'local_audio_path',
    ]) {
      expect(serialized.contains(forbidden), isFalse);
    }
  });

  test(
    'upload telemetry reports exact JSON and bounded request estimate',
    () async {
      final transport = RecordingObservationClient();
      final client = ObservationShadowClient(enabled: true, client: transport);
      final observation = payloadFor(
        ObservationSequence(processSessionId: 'process-1').next('A01'),
      );

      final result = await client.uploadWithTelemetry(
        uri: Uri.parse('https://example.test/observations/shadow'),
        uploadToken: 'shadow-token',
        observation: observation,
      );

      expect(result.status, ObservationUploadStatus.uploaded);
      expect(
        result.payloadBytes,
        utf8.encode(jsonEncode(observation.toJson())).length,
      );
      expect(result.estimatedRequestBytes, greaterThan(result.payloadBytes));
      expect(result.httpDurationMs, greaterThanOrEqualTo(0));
    },
  );

  test('app reconciliation exposes delivery and byte counters', () {
    final metrics = ObservationShadowMetrics()
      ..rawAiObservationCount = 3
      ..observationCreatedCount = 3
      ..uploadAttemptCount = 3
      ..observationUploadedCount = 2
      ..currentProcessObservationUploadedCount = 2
      ..observationUploadFailedCount = 1
      ..payloadBytes = 1200
      ..estimatedRequestBytes = 1800;

    expect(metrics.toJson()['raw_to_upload_loss_count'], 1);
    expect(
      metrics.toJson()['overall_app_delivery_percent'],
      closeTo(66.67, 0.01),
    );
  });

  test('recovered uploads cannot make current-process loss negative', () {
    final metrics = ObservationShadowMetrics()
      ..rawAiObservationCount = 0
      ..observationUploadedCount = 6
      ..recoveredObservationUploadedCount = 6;

    expect(metrics.toJson()['raw_to_upload_loss_count'], 0);
    expect(metrics.toJson()['overall_app_delivery_percent'], isNull);
    expect(metrics.toJson()['uploaded_this_process'], 6);
    expect(metrics.toJson()['recovered_uploaded_this_process'], 6);
  });

  test('field JSON is emitted as bounded reassemblable logcat chunks', () {
    final sample = <String, dynamic>{
      'observation_id': 'obs-A01-process-1-9',
      'device_id': 'A01',
      'payload': List<String>.filled(200, 'long-value'),
    };

    final lines = encodeObservationShadowFieldLogLines(sample);

    expect(lines.length, greaterThan(1));
    expect(lines.every((line) => utf8.encode(line).length < 800), isTrue);
    final encoded = lines.map((line) => line.split(' data=').last).join();
    expect(jsonDecode(utf8.decode(base64Decode(encoded))), equals(sample));
  });

  test('classification inference JSON uses its own bounded marker', () {
    final sample = <String, dynamic>{
      'inference_id': 'inf-A01-process-1-1000',
      'observation_id': null,
      'event_id': null,
      'classification': payloadFor(
        const ObservationIdentity(
          observationId: 'obs-1',
          sequence: 1,
          processSessionId: 'process-1',
        ),
      ).classification!.toJson(),
    };

    final lines = encodeClassificationInferenceFieldLogLines(sample);

    expect(lines, isNotEmpty);
    expect(
      lines.every(
        (line) => line.startsWith(
          '$classificationInferenceFieldJsonBase64Marker inference_id=',
        ),
      ),
      isTrue,
    );
    expect(lines.every((line) => utf8.encode(line).length < 800), isTrue);
    final encoded = lines.map((line) => line.split(' data=').last).join();
    expect(jsonDecode(utf8.decode(base64Decode(encoded))), equals(sample));
  });

  test('feature flag off performs no network request', () async {
    final transport = RecordingObservationClient();
    final client = ObservationShadowClient(enabled: false, client: transport);
    final sequence = ObservationSequence(processSessionId: 'process-1');

    final status = await client.upload(
      uri: Uri.parse('https://example.test/observations/shadow'),
      uploadToken: 'shadow-token',
      observation: payloadFor(sequence.next('A01')),
    );

    expect(status, ObservationUploadStatus.disabled);
    expect(transport.requestCount, 0);
  });

  test('integration queues observation without blocking alert admission', () {
    final source = File('lib/main.dart').readAsStringSync();
    final shadowIndex = source.indexOf(
      'unawaited(enqueueTargetObservationShadow(observation))',
    );
    final admissionIndex = source.indexOf(
      'final admission = eventAdmissionController.evaluate',
      shadowIndex,
    );

    expect(shadowIndex, greaterThan(0));
    expect(admissionIndex, greaterThan(shadowIndex));
    expect(
      source.contains('await enqueueTargetObservationShadow(observation)'),
      isFalse,
    );
    expect(source, contains("'OBSERVATION_SHADOW_ENABLED'"));
    expect(source, contains('defaultValue: false'));
    expect(source, contains('encodeObservationShadowFieldLogLines'));
    expect(source, contains("'classification': observation['classification']"));
  });
}
