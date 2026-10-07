import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/config/app_config.dart';

void main() {
  group('AppConfig validation', () {
    test('rejects missing runtime configuration', () {
      const config = AppConfig(
        environmentName: '',
        backendBaseUrl: '',
        uploadToken: '',
        deviceToken: '',
        liveAudioEnabled: false,
        commandWebSocketEnabled: true,
        restFallbackEnabled: true,
      );

      expect(config.isValid, isFalse);
      expect(
        config.validationErrors.map((error) => error.code),
        containsAll(<String>[
          'missing_app_env',
          'missing_backend_base_url',
          'missing_upload_token',
          'missing_device_token',
        ]),
      );
    });

    test('rejects demo upload token without exposing secrets', () {
      final config = AppConfig(
        environmentName: 'staging',
        backendBaseUrl: 'https://sound-backend-staging.onrender.com',
        uploadToken: AppConfig.demoToken,
        deviceToken: 'test-only-device-token',
        liveAudioEnabled: false,
        commandWebSocketEnabled: true,
        restFallbackEnabled: true,
      );

      expect(config.isValid, isFalse);
      expect(
        config.validationErrors.map((error) => error.code),
        contains('demo_upload_token_rejected'),
      );
      expect(config.toString(), isNot(contains(config.uploadToken)));
      expect(
        config.validationErrors.join('\n'),
        isNot(contains(config.uploadToken)),
      );
    });

    test('allows demo upload token for development integration backend', () {
      final config = AppConfig(
        environmentName: 'development',
        backendBaseUrl: 'https://sound-backend.onrender.com',
        uploadToken: AppConfig.demoToken,
        deviceToken: 'test-only-device-token',
        liveAudioEnabled: false,
        commandWebSocketEnabled: true,
        restFallbackEnabled: true,
      );

      expect(config.isValid, isTrue);
    });

    test('rejects localhost in production', () {
      const config = AppConfig(
        environmentName: 'production',
        backendBaseUrl: 'http://localhost:8000',
        uploadToken: 'prod-upload-token',
        deviceToken: 'prod-device-token',
        liveAudioEnabled: false,
        commandWebSocketEnabled: true,
        restFallbackEnabled: true,
      );

      expect(config.isValid, isFalse);
      expect(
        config.validationErrors.map((error) => error.code),
        containsAll(<String>[
          'production_requires_https',
          'production_rejects_localhost',
        ]),
      );
    });

    test(
      'accepts internal-test development config for current integration backend',
      () {
        const config = AppConfig(
          environmentName: 'development',
          backendBaseUrl: 'https://sound-backend.onrender.com',
          uploadToken: 'integration-upload-token',
          deviceToken: 'integration-device-token',
          liveAudioEnabled: false,
          commandWebSocketEnabled: true,
          restFallbackEnabled: true,
        );

        expect(config.isValid, isTrue);
        expect(
          config.nodeWebSocketUrl,
          'wss://sound-backend.onrender.com/ws/node/%7Bdevice_id%7D',
        );
        expect(
          config.audioWebSocketUrl,
          'wss://sound-backend.onrender.com/ws/audio/%7Bdevice_id%7D',
        );
      },
    );

    test('accepts valid production config and builds wss URLs', () {
      const config = AppConfig(
        environmentName: 'production',
        backendBaseUrl: 'https://sound-backend.onrender.com/',
        uploadToken: 'prod-upload-token',
        deviceToken: 'prod-device-token',
        liveAudioEnabled: true,
        commandWebSocketEnabled: true,
        restFallbackEnabled: true,
      );

      expect(config.isValid, isTrue);
      expect(config.eventsUrl, 'https://sound-backend.onrender.com/events');
      expect(
        config.nodeWebSocketUrl,
        'wss://sound-backend.onrender.com/ws/node/%7Bdevice_id%7D',
      );
      expect(config.toString(), isNot(contains(config.uploadToken)));
    });

    test('accepts valid staging config', () {
      const config = AppConfig(
        environmentName: 'staging',
        backendBaseUrl: 'https://sound-backend-staging.example.test',
        uploadToken: 'staging-upload-token',
        deviceToken: 'staging-device-token',
        liveAudioEnabled: false,
        commandWebSocketEnabled: true,
        restFallbackEnabled: true,
      );

      expect(config.isValid, isTrue);
    });

    test('rejects the known production backend in staging', () {
      const config = AppConfig(
        environmentName: 'staging',
        backendBaseUrl: 'https://sound-backend.onrender.com',
        uploadToken: 'staging-upload-token',
        deviceToken: 'staging-device-token',
        liveAudioEnabled: false,
        commandWebSocketEnabled: true,
        restFallbackEnabled: true,
      );

      expect(config.isValid, isFalse);
      expect(
        config.validationErrors.map((error) => error.code),
        contains('staging_rejects_production_host'),
      );
    });
  });
}
