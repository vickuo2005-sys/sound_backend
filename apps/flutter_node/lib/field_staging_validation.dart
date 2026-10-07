class FieldStagingConfigValidation {
  const FieldStagingConfigValidation({
    required this.errors,
    required this.appEnvironment,
    required this.backendHost,
    required this.uploadTokenPresent,
    required this.deviceTokenPresent,
    required this.observationShadowEnabled,
    required this.postInferenceLatencyTracingEnabled,
  });

  final List<String> errors;
  final String appEnvironment;
  final String backendHost;
  final bool uploadTokenPresent;
  final bool deviceTokenPresent;
  final bool observationShadowEnabled;
  final bool postInferenceLatencyTracingEnabled;

  bool get valid => errors.isEmpty;

  Map<String, dynamic> toSafeJson() => <String, dynamic>{
    'valid': valid,
    'errors': errors,
    'app_env': appEnvironment,
    'backend_host': backendHost,
    'upload_token_present': uploadTokenPresent,
    'device_token_present': deviceTokenPresent,
    'observation_shadow_enabled': observationShadowEnabled,
    'post_inference_latency_tracing_enabled':
        postInferenceLatencyTracingEnabled,
  };
}

FieldStagingConfigValidation validateFieldStagingConfig(
  Map<String, dynamic> config, {
  bool requireShadowEnabled = true,
  bool requirePostInferenceLatencyTracingEnabled = true,
  Set<String> approvedStagingHosts = const <String>{},
  Set<String> forbiddenProductionHosts = const <String>{
    'sound-backend.onrender.com',
  },
}) {
  final errors = <String>[];
  final environment = (config['APP_ENV'] ?? '').toString().trim().toLowerCase();
  final backendValue = (config['BACKEND_BASE_URL'] ?? '').toString().trim();
  final backendUri = Uri.tryParse(backendValue);
  final backendHost = backendUri?.host.toLowerCase() ?? '';
  final uploadTokenPresent = (config['UPLOAD_TOKEN'] ?? '')
      .toString()
      .trim()
      .isNotEmpty;
  final deviceTokenPresent = (config['DEVICE_TOKEN'] ?? '')
      .toString()
      .trim()
      .isNotEmpty;
  final observationShadowEnabled =
      (config['OBSERVATION_SHADOW_ENABLED'] ?? '').toString().toLowerCase() ==
      'true';
  final postInferenceLatencyTracingEnabled =
      (config['POST_INFERENCE_LATENCY_TRACING_ENABLED'] ?? '')
          .toString()
          .toLowerCase() ==
      'true';
  final normalizedApprovedStagingHosts = approvedStagingHosts
      .map((host) => host.trim().toLowerCase())
      .where((host) => host.isNotEmpty)
      .toSet();

  if (environment != 'staging') {
    errors.add('APP_ENV must be staging');
  }
  if (backendUri == null ||
      backendUri.scheme.toLowerCase() != 'https' ||
      backendHost.isEmpty) {
    errors.add('BACKEND_BASE_URL must be a non-empty HTTPS staging URL');
  }
  if (forbiddenProductionHosts.contains(backendHost)) {
    errors.add('BACKEND_BASE_URL points to a forbidden production host');
  }
  if (backendHost == 'localhost' || backendHost == '127.0.0.1') {
    errors.add('BACKEND_BASE_URL must not use localhost for field validation');
  }
  if (backendHost.isEmpty ||
      !normalizedApprovedStagingHosts.contains(backendHost)) {
    errors.add(
      'BACKEND_BASE_URL hostname is not in the approved staging allowlist',
    );
  }
  if (!uploadTokenPresent) {
    errors.add('A staging UPLOAD_TOKEN is required');
  }
  if (!deviceTokenPresent) {
    errors.add('A staging DEVICE_TOKEN is required');
  }
  if (requireShadowEnabled && !observationShadowEnabled) {
    errors.add('OBSERVATION_SHADOW_ENABLED must be true for a field run');
  }
  if (requirePostInferenceLatencyTracingEnabled &&
      !postInferenceLatencyTracingEnabled) {
    errors.add(
      'POST_INFERENCE_LATENCY_TRACING_ENABLED must be true for a field run',
    );
  }

  return FieldStagingConfigValidation(
    errors: List<String>.unmodifiable(errors),
    appEnvironment: environment,
    backendHost: backendHost,
    uploadTokenPresent: uploadTokenPresent,
    deviceTokenPresent: deviceTokenPresent,
    observationShadowEnabled: observationShadowEnabled,
    postInferenceLatencyTracingEnabled: postInferenceLatencyTracingEnabled,
  );
}
