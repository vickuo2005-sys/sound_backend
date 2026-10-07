import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/field_staging_validation.dart';

void main() {
  test('rejects development config pointed at production', () {
    final result = validateFieldStagingConfig(
      <String, dynamic>{
        'APP_ENV': 'development',
        'BACKEND_BASE_URL': 'https://sound-backend.onrender.com',
        'UPLOAD_TOKEN': 'production-token-must-not-be-used',
        'DEVICE_TOKEN': 'production-device-token-must-not-be-used',
        'POST_INFERENCE_LATENCY_TRACING_ENABLED': 'true',
      },
      approvedStagingHosts: <String>{'sound-backend-staging.example.test'},
    );

    expect(result.valid, isFalse);
    expect(result.errors, contains('APP_ENV must be staging'));
    expect(
      result.errors,
      contains('BACKEND_BASE_URL points to a forbidden production host'),
    );
    expect(result.toSafeJson().containsKey('upload_token'), isFalse);
  });

  test(
    'accepts complete staging-only field config without exposing tokens',
    () {
      final result = validateFieldStagingConfig(
        <String, dynamic>{
          'APP_ENV': 'staging',
          'BACKEND_BASE_URL': 'https://sound-backend-staging.example.test',
          'UPLOAD_TOKEN': 'staging-upload-token',
          'DEVICE_TOKEN': 'staging-device-token',
          'OBSERVATION_SHADOW_ENABLED': 'true',
          'POST_INFERENCE_LATENCY_TRACING_ENABLED': 'true',
        },
        approvedStagingHosts: <String>{'sound-backend-staging.example.test'},
      );

      expect(result.valid, isTrue);
      expect(result.toSafeJson()['upload_token_present'], isTrue);
      expect(
        result.toSafeJson().toString(),
        isNot(contains('staging-upload-token')),
      );
    },
  );

  test('rejects an otherwise valid config when the hostname is unknown', () {
    final result = validateFieldStagingConfig(
      <String, dynamic>{
        'APP_ENV': 'staging',
        'BACKEND_BASE_URL': 'https://unknown.example.test',
        'UPLOAD_TOKEN': 'staging-upload-token',
        'DEVICE_TOKEN': 'staging-device-token',
        'OBSERVATION_SHADOW_ENABLED': 'true',
        'POST_INFERENCE_LATENCY_TRACING_ENABLED': 'true',
      },
      approvedStagingHosts: <String>{'sound-backend-staging.example.test'},
    );

    expect(result.valid, isFalse);
    expect(
      result.errors,
      contains(
        'BACKEND_BASE_URL hostname is not in the approved staging allowlist',
      ),
    );
  });

  test('rejects a field config when latency tracing is disabled', () {
    final result = validateFieldStagingConfig(
      <String, dynamic>{
        'APP_ENV': 'staging',
        'BACKEND_BASE_URL': 'https://sound-backend-staging.example.test',
        'UPLOAD_TOKEN': 'staging-upload-token',
        'DEVICE_TOKEN': 'staging-device-token',
        'OBSERVATION_SHADOW_ENABLED': 'true',
        'POST_INFERENCE_LATENCY_TRACING_ENABLED': 'false',
      },
      approvedStagingHosts: <String>{'sound-backend-staging.example.test'},
    );

    expect(result.valid, isFalse);
    expect(
      result.errors,
      contains(
        'POST_INFERENCE_LATENCY_TRACING_ENABLED must be true for a field run',
      ),
    );
  });
}
