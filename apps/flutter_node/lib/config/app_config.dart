enum AppEnvironment { development, staging, production }

class AppConfigValidationError {
  const AppConfigValidationError(this.code, this.message);

  final String code;
  final String message;

  @override
  String toString() => '$code: $message';
}

class AppConfig {
  const AppConfig({
    required this.environmentName,
    required this.backendBaseUrl,
    required this.uploadToken,
    required this.deviceToken,
    required this.liveAudioEnabled,
    required this.commandWebSocketEnabled,
    required this.restFallbackEnabled,
  });

  factory AppConfig.fromEnvironment() {
    return const AppConfig(
      environmentName: String.fromEnvironment('APP_ENV'),
      backendBaseUrl: String.fromEnvironment('BACKEND_BASE_URL'),
      uploadToken: String.fromEnvironment('UPLOAD_TOKEN'),
      deviceToken: String.fromEnvironment('DEVICE_TOKEN'),
      liveAudioEnabled: bool.fromEnvironment('LIVE_AUDIO_ENABLED'),
      commandWebSocketEnabled: bool.fromEnvironment(
        'COMMAND_WEBSOCKET_ENABLED',
        defaultValue: true,
      ),
      restFallbackEnabled: bool.fromEnvironment(
        'REST_FALLBACK_ENABLED',
        defaultValue: true,
      ),
    );
  }

  final String environmentName;
  final String backendBaseUrl;
  final String uploadToken;
  final String deviceToken;
  final bool liveAudioEnabled;
  final bool commandWebSocketEnabled;
  final bool restFallbackEnabled;

  static String get demoToken => ['test', 'token-123'].join('-');

  AppEnvironment? get environment {
    switch (environmentName.trim().toLowerCase()) {
      case 'development':
      case 'dev':
      case 'local':
        return AppEnvironment.development;
      case 'staging':
        return AppEnvironment.staging;
      case 'production':
      case 'prod':
        return AppEnvironment.production;
      default:
        return null;
    }
  }

  String get normalizedBackendBaseUrl {
    final trimmed = backendBaseUrl.trim();
    if (trimmed.endsWith('/')) {
      return trimmed.substring(0, trimmed.length - 1);
    }
    if (trimmed.endsWith('/events')) {
      return trimmed.substring(0, trimmed.length - '/events'.length);
    }
    return trimmed;
  }

  Uri? get backendUri => Uri.tryParse(normalizedBackendBaseUrl);

  String get eventsUrl => normalizedBackendBaseUrl.isEmpty
      ? ''
      : '$normalizedBackendBaseUrl/events';
  String get observationShadowUrl => normalizedBackendBaseUrl.isEmpty
      ? ''
      : '$normalizedBackendBaseUrl/observations/shadow';
  String get audioUploadUrl => '$normalizedBackendBaseUrl/upload-audio';
  String get tdoaClipUploadUrl => '$normalizedBackendBaseUrl/upload-tdoa-clip';
  String get locationUpdateUrl => '$normalizedBackendBaseUrl/location-update';
  String get nodeWebSocketUrl => _webSocketUrl('/ws/node/{device_id}');
  String get audioWebSocketUrl => _webSocketUrl('/ws/audio/{device_id}');

  bool get hasUploadToken => uploadToken.trim().isNotEmpty;
  bool get hasDeviceToken => deviceToken.trim().isNotEmpty;
  bool get isValid => validationErrors.isEmpty;
  bool get isRuntimeReady => isValid;

  List<AppConfigValidationError> get validationErrors {
    final errors = <AppConfigValidationError>[];
    final env = environment;
    final uri = backendUri;
    final host = uri?.host.toLowerCase() ?? '';
    final scheme = uri?.scheme.toLowerCase() ?? '';

    if (env == null) {
      errors.add(
        const AppConfigValidationError(
          'missing_app_env',
          'APP_ENV must be development, staging, or production.',
        ),
      );
    }

    if (normalizedBackendBaseUrl.isEmpty || uri == null || host.isEmpty) {
      errors.add(
        const AppConfigValidationError(
          'missing_backend_base_url',
          'BACKEND_BASE_URL is required.',
        ),
      );
    }

    if (!hasUploadToken) {
      errors.add(
        const AppConfigValidationError(
          'missing_upload_token',
          'UPLOAD_TOKEN is required.',
        ),
      );
    }

    if (!hasDeviceToken) {
      errors.add(
        const AppConfigValidationError(
          'missing_device_token',
          'DEVICE_TOKEN is required.',
        ),
      );
    }

    if (uploadToken == demoToken && env != AppEnvironment.development) {
      errors.add(
        const AppConfigValidationError(
          'demo_upload_token_rejected',
          'The demo upload token is not allowed in runtime config.',
        ),
      );
    }

    if (deviceToken == demoToken && env != AppEnvironment.development) {
      errors.add(
        const AppConfigValidationError(
          'demo_device_token_rejected',
          'The demo device token is not allowed in runtime config.',
        ),
      );
    }

    if (env == AppEnvironment.production) {
      if (scheme != 'https') {
        errors.add(
          const AppConfigValidationError(
            'production_requires_https',
            'Production BACKEND_BASE_URL must use https.',
          ),
        );
      }
      if (_isLocalHost(host)) {
        errors.add(
          const AppConfigValidationError(
            'production_rejects_localhost',
            'Production BACKEND_BASE_URL cannot be localhost.',
          ),
        );
      }
      if (host.contains('staging')) {
        errors.add(
          const AppConfigValidationError(
            'production_rejects_staging_host',
            'Production BACKEND_BASE_URL cannot point to staging.',
          ),
        );
      }
    }

    if (env == AppEnvironment.staging) {
      if (scheme != 'https') {
        errors.add(
          const AppConfigValidationError(
            'staging_requires_https',
            'Staging BACKEND_BASE_URL must use https.',
          ),
        );
      }
      if (host == 'sound-backend.onrender.com') {
        errors.add(
          const AppConfigValidationError(
            'staging_rejects_production_host',
            'Staging BACKEND_BASE_URL cannot point to the production host.',
          ),
        );
      }
    }

    if (env == AppEnvironment.development) {
      if (!_isLocalHost(host) && scheme != 'https') {
        errors.add(
          const AppConfigValidationError(
            'development_remote_requires_https',
            'Development BACKEND_BASE_URL must use https for remote hosts.',
          ),
        );
      }
    }

    return errors;
  }

  String get configStatusSummary {
    if (isValid) {
      return 'APP_ENV=$environmentName backend_configured=true token_configured=true';
    }
    final codes = validationErrors.map((error) => error.code).join(', ');
    return 'configuration_error: $codes';
  }

  @override
  String toString() {
    return 'AppConfig(environment=$environmentName, '
        'backend_configured=${normalizedBackendBaseUrl.isNotEmpty}, '
        'upload_token_configured=$hasUploadToken, '
        'device_token_configured=$hasDeviceToken, '
        'live_audio_enabled=$liveAudioEnabled, '
        'command_websocket_enabled=$commandWebSocketEnabled, '
        'rest_fallback_enabled=$restFallbackEnabled)';
  }

  String _webSocketUrl(String path) {
    final uri = backendUri;
    if (uri == null || uri.host.isEmpty) return '';
    final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
    return Uri(
      scheme: scheme,
      userInfo: uri.userInfo,
      host: uri.host,
      port: uri.hasPort ? uri.port : null,
      path: path,
    ).toString();
  }

  bool _isLocalHost(String host) {
    return host == 'localhost' ||
        host == '127.0.0.1' ||
        host == '0.0.0.0' ||
        host == '10.0.2.2';
  }
}
