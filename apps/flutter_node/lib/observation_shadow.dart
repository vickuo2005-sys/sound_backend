import 'dart:convert';

import 'package:http/http.dart' as http;

import 'classification_result.dart';

const String observationShadowFieldJsonBase64Marker =
    '[OBSERVATION_SHADOW_FIELD_JSON_B64]';
const String classificationInferenceFieldJsonBase64Marker =
    '[CLASSIFICATION_INFERENCE_FIELD_JSON_B64]';

/// Encodes one field sample into bounded ASCII log lines. Android logcat can
/// truncate long messages, which would turn a valid JSON sample into unusable
/// field evidence. Base64 chunks stay independently below that boundary and
/// are reassembled by the Phase 4 analyzer.
List<String> encodeObservationShadowFieldLogLines(
  Map<String, dynamic> sample, {
  int chunkChars = 480,
}) {
  return _encodeBoundedFieldLogLines(
    sample,
    marker: observationShadowFieldJsonBase64Marker,
    identityField: 'observation_id',
    chunkChars: chunkChars,
  );
}

List<String> encodeClassificationInferenceFieldLogLines(
  Map<String, dynamic> sample, {
  int chunkChars = 480,
}) {
  return _encodeBoundedFieldLogLines(
    sample,
    marker: classificationInferenceFieldJsonBase64Marker,
    identityField: 'inference_id',
    chunkChars: chunkChars,
  );
}

List<String> _encodeBoundedFieldLogLines(
  Map<String, dynamic> sample, {
  required String marker,
  required String identityField,
  required int chunkChars,
}) {
  if (chunkChars < 100 || chunkChars > 600) {
    throw ArgumentError.value(chunkChars, 'chunkChars', 'must be 100..600');
  }
  final identity = '${sample[identityField] ?? ''}'.trim();
  if (identity.isEmpty) {
    throw ArgumentError('$identityField is required for field log chunks');
  }
  final encoded = base64Encode(utf8.encode(jsonEncode(sample)));
  final total = (encoded.length + chunkChars - 1) ~/ chunkChars;
  final lines = <String>[];
  for (var index = 0; index < total; index += 1) {
    final start = index * chunkChars;
    final end = start + chunkChars < encoded.length
        ? start + chunkChars
        : encoded.length;
    lines.add(
      '$marker '
      '$identityField=${Uri.encodeComponent(identity)} '
      'chunk=${index + 1}/$total data=${encoded.substring(start, end)}',
    );
  }
  return lines;
}

class ObservationIdentity {
  const ObservationIdentity({
    required this.observationId,
    required this.sequence,
    required this.processSessionId,
  });

  final String observationId;
  final int sequence;
  final String processSessionId;
}

class ObservationSequence {
  ObservationSequence({required this.processSessionId});

  final String processSessionId;
  final Map<String, int> _lastSequenceByDevice = <String, int>{};

  int get lastSequence => _lastSequenceByDevice.values.fold<int>(
    0,
    (current, value) => value > current ? value : current,
  );

  int lastSequenceForDevice(String deviceId) {
    return _lastSequenceByDevice[_normalizedDeviceId(deviceId)] ?? 0;
  }

  ObservationIdentity next(String deviceId) {
    final safeDeviceId = _normalizedDeviceId(deviceId);
    final nextSequence = (_lastSequenceByDevice[safeDeviceId] ?? 0) + 1;
    _lastSequenceByDevice[safeDeviceId] = nextSequence;
    return ObservationIdentity(
      observationId: 'obs_${safeDeviceId}_${processSessionId}_$nextSequence',
      sequence: nextSequence,
      processSessionId: processSessionId,
    );
  }

  String _normalizedDeviceId(String deviceId) {
    return deviceId.trim().replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
  }
}

class ObservationShadowPayload {
  const ObservationShadowPayload({
    required this.identity,
    required this.deviceId,
    required this.observedAt,
    required this.eventTimeMs,
    required this.label,
    required this.confidence,
    required this.aircraftProbability,
    required this.rmsPeak,
    required this.avgRms,
    required this.estimatedPeakDb,
    required this.estimatedAvgDb,
    required this.nodePositionSource,
    required this.latitude,
    required this.longitude,
    required this.gpsAccuracyM,
    this.timeSync,
    required this.modelId,
    required this.modelName,
    required this.aiInferenceTimeMs,
    required this.windowDurationMs,
    required this.hopDurationMs,
    required this.sampleRateHz,
    this.classification,
  });

  final ObservationIdentity identity;
  final String deviceId;
  final String observedAt;
  final int eventTimeMs;
  final String label;
  final double? confidence;
  final double? aircraftProbability;
  final double rmsPeak;
  final double avgRms;
  final double estimatedPeakDb;
  final double estimatedAvgDb;
  final String nodePositionSource;
  final double? latitude;
  final double? longitude;
  final double? gpsAccuracyM;
  final ObservationTimeSyncSnapshot? timeSync;
  final String modelId;
  final String modelName;
  final int aiInferenceTimeMs;
  final int windowDurationMs;
  final int hopDurationMs;
  final int sampleRateHz;
  final ClassificationResult? classification;

  String get observationId => identity.observationId;
  String get traceId => identity.observationId;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'message_type': 'observation.v1',
      'schema_version': 1,
      'observation_id': identity.observationId,
      'device_id': deviceId,
      'observed_at': observedAt,
      'event_time_ms': eventTimeMs,
      'sequence': identity.sequence,
      'process_session_id': identity.processSessionId,
      'label': label,
      'confidence': confidence,
      'aircraft_probability': aircraftProbability,
      'rms_peak': rmsPeak,
      'avg_rms': avgRms,
      'estimated_peak_db': estimatedPeakDb,
      'estimated_avg_db': estimatedAvgDb,
      'location': <String, dynamic>{
        'source': nodePositionSource,
        'latitude': latitude,
        'longitude': longitude,
        'accuracy_m': gpsAccuracyM,
      },
      'time_sync': timeSync?.toJson(),
      'model_id': modelId,
      'model_name': modelName,
      'ai_inference_time_ms': aiInferenceTimeMs,
      'window_duration_ms': windowDurationMs,
      'hop_duration_ms': hopDurationMs,
      'sample_rate_hz': sampleRateHz,
      if (classification != null) 'classification': classification!.toJson(),
      'audio_ref': null,
      'alert_candidate': true,
      'trace_id': traceId,
    };
  }
}

class ObservationTimeSyncSnapshot {
  const ObservationTimeSyncSnapshot({
    required this.version,
    required this.quality,
    required this.offsetMs,
    required this.rttMs,
    required this.ageMs,
    this.deviceWallClockMs,
    this.deviceMonotonicMs,
    this.monotonicSessionId,
  });

  final int? version;
  final String? quality;
  final double? offsetMs;
  final double? rttMs;
  final int? ageMs;
  final int? deviceWallClockMs;
  final double? deviceMonotonicMs;
  final String? monotonicSessionId;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'version': version,
    'quality': quality,
    'offset_ms': offsetMs,
    'rtt_ms': rttMs,
    'age_ms': ageMs,
    'device_wall_clock_ms': deviceWallClockMs,
    'device_monotonic_ms': deviceMonotonicMs,
    'monotonic_session_id': monotonicSessionId,
  };
}

enum ObservationUploadStatus { disabled, uploaded, failed }

class ObservationUploadResult {
  const ObservationUploadResult({
    required this.status,
    required this.payloadBytes,
    required this.estimatedRequestBytes,
    required this.httpDurationMs,
    this.statusCode,
    this.error,
  });

  final ObservationUploadStatus status;
  final int payloadBytes;
  final int estimatedRequestBytes;
  final double httpDurationMs;
  final int? statusCode;
  final String? error;
}

class ObservationShadowClient {
  ObservationShadowClient({required this.enabled, http.Client? client})
    : _client = client ?? http.Client();

  final bool enabled;
  final http.Client _client;
  bool _closed = false;

  Future<ObservationUploadStatus> upload({
    required Uri uri,
    required String uploadToken,
    required ObservationShadowPayload observation,
    Duration timeout = const Duration(seconds: 15),
  }) async {
    final result = await uploadWithTelemetry(
      uri: uri,
      uploadToken: uploadToken,
      observation: observation,
      timeout: timeout,
    );
    return result.status;
  }

  Future<ObservationUploadResult> uploadWithTelemetry({
    required Uri uri,
    required String uploadToken,
    required ObservationShadowPayload observation,
    Duration timeout = const Duration(seconds: 15),
  }) async {
    return uploadJsonWithTelemetry(
      uri: uri,
      uploadToken: uploadToken,
      payload: observation.toJson(),
      timeout: timeout,
    );
  }

  Future<ObservationUploadResult> uploadJsonWithTelemetry({
    required Uri uri,
    required String uploadToken,
    required Map<String, dynamic> payload,
    Duration timeout = const Duration(seconds: 15),
  }) async {
    final body = jsonEncode(payload);
    final payloadBytes = utf8.encode(body).length;
    final estimatedRequestBytes = _estimateRequestBytes(
      uri: uri,
      uploadToken: uploadToken,
      payloadBytes: payloadBytes,
    );
    if (!enabled) {
      return ObservationUploadResult(
        status: ObservationUploadStatus.disabled,
        payloadBytes: payloadBytes,
        estimatedRequestBytes: estimatedRequestBytes,
        httpDurationMs: 0,
        error: 'disabled',
      );
    }
    if (_closed) {
      return ObservationUploadResult(
        status: ObservationUploadStatus.failed,
        payloadBytes: payloadBytes,
        estimatedRequestBytes: estimatedRequestBytes,
        httpDurationMs: 0,
        error: 'client_closed',
      );
    }
    final stopwatch = Stopwatch()..start();
    try {
      final response = await _client
          .post(
            uri,
            headers: <String, String>{
              'Content-Type': 'application/json',
              'x-upload-token': uploadToken,
            },
            body: body,
          )
          .timeout(timeout);
      stopwatch.stop();
      return ObservationUploadResult(
        status: response.statusCode >= 200 && response.statusCode < 300
            ? ObservationUploadStatus.uploaded
            : ObservationUploadStatus.failed,
        payloadBytes: payloadBytes,
        estimatedRequestBytes: estimatedRequestBytes,
        httpDurationMs: stopwatch.elapsedMicroseconds / 1000.0,
        statusCode: response.statusCode,
      );
    } catch (error) {
      stopwatch.stop();
      return ObservationUploadResult(
        status: ObservationUploadStatus.failed,
        payloadBytes: payloadBytes,
        estimatedRequestBytes: estimatedRequestBytes,
        httpDurationMs: stopwatch.elapsedMicroseconds / 1000.0,
        error: error.runtimeType.toString(),
      );
    }
  }

  int _estimateRequestBytes({
    required Uri uri,
    required String uploadToken,
    required int payloadBytes,
  }) {
    final requestLine =
        'POST ${uri.path}${uri.hasQuery ? '?${uri.query}' : ''} HTTP/1.1\r\n';
    final headers = <String>[
      'Host: ${uri.host}\r\n',
      'Content-Type: application/json\r\n',
      'Content-Length: $payloadBytes\r\n',
      'x-upload-token: $uploadToken\r\n',
      '\r\n',
    ].join();
    return payloadBytes +
        utf8.encode(requestLine).length +
        utf8.encode(headers).length;
  }

  void close() {
    if (_closed) return;
    _closed = true;
    _client.close();
  }
}

class ObservationShadowMetrics {
  int rawAiObservationCount = 0;
  int observationCreatedCount = 0;
  int uploadAttemptCount = 0;
  int observationUploadedCount = 0;
  int currentProcessObservationUploadedCount = 0;
  int recoveredObservationUploadedCount = 0;
  int observationUploadFailedCount = 0;
  int alertAdmittedCount = 0;
  int cooldownRejectedCount = 0;
  int payloadBytes = 0;
  int estimatedRequestBytes = 0;

  Map<String, dynamic> toJson() {
    final rawToUploadLoss =
        rawAiObservationCount - currentProcessObservationUploadedCount;
    final boundedLoss = rawToUploadLoss < 0 ? 0 : rawToUploadLoss;
    final deliveryPercent = rawAiObservationCount == 0
        ? null
        : (currentProcessObservationUploadedCount *
                  100.0 /
                  rawAiObservationCount)
              .clamp(0.0, 100.0);
    return <String, dynamic>{
      'raw_valid_target_count': rawAiObservationCount,
      'raw_created_this_process': rawAiObservationCount,
      'observation_created_count': observationCreatedCount,
      'upload_attempt_count': uploadAttemptCount,
      'upload_success_count': observationUploadedCount,
      'observation_uploaded_count': observationUploadedCount,
      'uploaded_this_process': observationUploadedCount,
      'uploaded_current_process_observations':
          currentProcessObservationUploadedCount,
      'recovered_uploaded_this_process': recoveredObservationUploadedCount,
      'observation_upload_failed_count': observationUploadFailedCount,
      'alert_admitted_count': alertAdmittedCount,
      'cooldown_rejected_count': cooldownRejectedCount,
      'payload_bytes': payloadBytes,
      'estimated_request_bytes': estimatedRequestBytes,
      'raw_to_upload_loss_count': boundedLoss,
      'overall_app_delivery_percent': deliveryPercent,
    };
  }
}
