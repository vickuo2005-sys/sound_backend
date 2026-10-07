import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:vibration/vibration.dart';

import 'ai_sound_classifier.dart';
import 'classification_result.dart';
import 'target_sound_policy.dart';
import 'config/app_config.dart';
import 'event_admission_controller.dart';
import 'event_upload_queue.dart';
import 'event_timing_metadata.dart';
import 'listening_elapsed_counter.dart';
import 'observation_shadow.dart';
import 'observation_retry_queue.dart';
import 'post_inference_latency.dart';
import 'services/live_audio_stream_service.dart';
import 'services/metadata_upload_client.dart';
import 'services/node_connection_service.dart';
import 'smart_audio_upload.dart';
import 'time_sync_metadata.dart';
import 'ui/models/event_view_data.dart';
import 'ui/models/sound_level_reading.dart';
import 'ui/screens/events_view.dart';
import 'ui/screens/monitor_view.dart';
import 'ui/screens/system_view.dart';
import 'ui/theme/app_theme.dart';
import 'ui/theme/theme_mode_preference.dart';
import 'ui/widgets/event_list_item.dart';
import 'ui/widgets/status_badge.dart';
import 'ui/widgets/system_health_strip.dart';

void main() {
  runApp(const MyApp());
}

class AudioEvent {
  final String eventId;
  final String deviceId;
  final String time;
  final String duration;
  final String path;

  final double avgRms;
  final double peakRms;

  // Technical values: dBFS, usually negative.
  final double avgDb;
  final double peakDb;

  // Public-readable estimated dB.
  final double estimatedAvgDb;
  final double estimatedPeakDb;

  final double? latitude;
  final double? longitude;
  final double? gpsSpeedMps;
  final double? gpsHeadingDeg;
  final double? gpsAccuracyM;
  final String locationStatus;
  final String uploadStatus;
  final String aiLabel;
  final double? aircraftProbability;
  final double? aiConfidence;
  final String aiInferenceStatus;
  final int? aiInferenceTimeMs;
  final ClassificationResult? classification;
  final String uploadMode;
  final String? cloudAudioPath;
  final String? audioFormat;
  final int? audioSizeBytes;
  final int? sourcePcmSizeBytes;
  final String? audioEncodingStatus;
  final String? tdoaClipPath;
  final String? tdoaClipFormat;
  final int? tdoaClipSizeBytes;
  final int? tdoaClipStartSample;
  final int? tdoaClipEndSample;
  final int? tdoaClipPeakSample;
  final int? tdoaClipDurationMs;
  final String? tdoaClipSource;
  final double? deviceEventTimeMs;
  final double? eventStartTimeMs;
  final double? eventEndTimeMs;
  final double? rmsPeakOffsetMs;
  final int? sampleRate;
  final double? audioDurationMs;
  final int? timeSyncVersion;
  final double? timeSyncOffsetMs;
  final double? timeSyncRttMs;
  final String? timeSyncQuality;
  final int? timeSyncSyncedAtMs;
  final int? timeSyncAgeMs;
  final EventTimingMetadata? timingMetadata;
  final String? latencyDiagnostics;
  final Map<String, dynamic> latencyTrace;

  AudioEvent({
    required this.eventId,
    required this.deviceId,
    required this.time,
    required this.duration,
    required this.path,
    required this.avgRms,
    required this.peakRms,
    required this.avgDb,
    required this.peakDb,
    required this.estimatedAvgDb,
    required this.estimatedPeakDb,
    required this.latitude,
    required this.longitude,
    required this.gpsSpeedMps,
    required this.gpsHeadingDeg,
    required this.gpsAccuracyM,
    required this.locationStatus,
    required this.uploadStatus,
    required this.aiLabel,
    required this.aircraftProbability,
    required this.aiConfidence,
    required this.aiInferenceStatus,
    required this.aiInferenceTimeMs,
    this.classification,
    required this.uploadMode,
    this.cloudAudioPath,
    this.audioFormat,
    this.audioSizeBytes,
    this.sourcePcmSizeBytes,
    this.audioEncodingStatus,
    this.tdoaClipPath,
    this.tdoaClipFormat,
    this.tdoaClipSizeBytes,
    this.tdoaClipStartSample,
    this.tdoaClipEndSample,
    this.tdoaClipPeakSample,
    this.tdoaClipDurationMs,
    this.tdoaClipSource,
    this.deviceEventTimeMs,
    this.eventStartTimeMs,
    this.eventEndTimeMs,
    this.rmsPeakOffsetMs,
    this.sampleRate,
    this.audioDurationMs,
    this.timeSyncVersion,
    this.timeSyncOffsetMs,
    this.timeSyncRttMs,
    this.timeSyncQuality,
    this.timeSyncSyncedAtMs,
    this.timeSyncAgeMs,
    this.timingMetadata,
    this.latencyDiagnostics,
    Map<String, dynamic>? latencyTrace,
  }) : latencyTrace = latencyTrace ?? <String, dynamic>{};

  String get traceId => latencyTrace['trace_id']?.toString() ?? eventId;

  Map<String, dynamic> toJson() {
    return {
      "event_id": eventId,
      "device_id": deviceId,
      "time": time,
      "duration": duration,
      "path": path,
      "avg_rms": avgRms,
      "peak_rms": peakRms,
      "avg_db": avgDb,
      "peak_db": peakDb,
      "estimated_avg_db": estimatedAvgDb,
      "estimated_peak_db": estimatedPeakDb,
      "estimated_db_avg": estimatedAvgDb,
      "estimated_db_peak": estimatedPeakDb,
      "latitude": latitude,
      "longitude": longitude,
      "gps_speed_mps": gpsSpeedMps,
      "gps_heading_deg": gpsHeadingDeg,
      "gps_accuracy_m": gpsAccuracyM,
      "location_status": locationStatus,
      "upload_status": uploadStatus,
      "ai_label": aiLabel,
      "aircraft_probability": aircraftProbability,
      "ai_confidence": aiConfidence,
      "ai_inference_status": aiInferenceStatus,
      "ai_inference_time_ms": aiInferenceTimeMs,
      "classification": classification?.toJson(),
      "upload_mode": uploadMode,
      "cloud_audio_path": cloudAudioPath,
      "audio_format": audioFormat,
      "audio_size_bytes": audioSizeBytes,
      "source_pcm_size_bytes": sourcePcmSizeBytes,
      "audio_encoding_status": audioEncodingStatus,
      "tdoa_clip_path": tdoaClipPath,
      "tdoa_clip_format": tdoaClipFormat,
      "tdoa_clip_size_bytes": tdoaClipSizeBytes,
      "tdoa_clip_start_sample": tdoaClipStartSample,
      "tdoa_clip_end_sample": tdoaClipEndSample,
      "tdoa_clip_peak_sample": tdoaClipPeakSample,
      "tdoa_clip_duration_ms": tdoaClipDurationMs,
      "tdoa_clip_source": tdoaClipSource,
      "device_event_time_ms": deviceEventTimeMs,
      "event_start_time_ms": eventStartTimeMs,
      "event_end_time_ms": eventEndTimeMs,
      "rms_peak_offset_ms": rmsPeakOffsetMs,
      "sample_rate": sampleRate,
      "audio_duration_ms": audioDurationMs,
      "time_sync_version": timeSyncVersion,
      "time_sync_offset_ms": timeSyncOffsetMs,
      "time_sync_rtt_ms": timeSyncRttMs,
      "time_sync_quality": timeSyncQuality,
      "time_sync_synced_at_ms": timeSyncSyncedAtMs,
      "time_sync_age_ms": timeSyncAgeMs,
      "latency_diagnostics": latencyDiagnostics,
      "trace_id": traceId,
      "latency_trace": latencyTrace,
      if (timingMetadata != null) ...timingMetadata!.toJson(),
    };
  }

  factory AudioEvent.fromJson(Map<String, dynamic> json) {
    final avgDbfs = _toDouble(json["avg_db"] ?? json["db_avg"]);
    final peakDbfs = _toDouble(json["peak_db"] ?? json["db_peak"]);

    final estimatedAvg =
        _toNullableDouble(
          json["estimated_avg_db"] ?? json["estimated_db_avg"],
        ) ??
        avgDbfs + 95.0;
    final estimatedPeak =
        _toNullableDouble(
          json["estimated_peak_db"] ?? json["estimated_db_peak"],
        ) ??
        peakDbfs + 95.0;

    return AudioEvent(
      eventId: json["event_id"]?.toString() ?? "",
      deviceId: json["device_id"]?.toString() ?? "unknown_device",
      time:
          json["time"]?.toString() ??
          json["timestamp"]?.toString() ??
          "unknown time",
      duration:
          json["duration"]?.toString() ??
          "${json["duration_s"]?.toString() ?? "0"} s",
      path:
          json["path"]?.toString() ??
          json["local_audio_path"]?.toString() ??
          "unknown path",
      avgRms: _toDouble(json["avg_rms"] ?? json["rms_avg"]),
      peakRms: _toDouble(json["peak_rms"] ?? json["rms_peak"]),
      avgDb: avgDbfs,
      peakDb: peakDbfs,
      estimatedAvgDb: estimatedAvg,
      estimatedPeakDb: estimatedPeak,
      latitude: _toNullableDouble(json["latitude"]),
      longitude: _toNullableDouble(json["longitude"]),
      gpsSpeedMps: _toNullableDouble(json["gps_speed_mps"]),
      gpsHeadingDeg: _toNullableDouble(json["gps_heading_deg"]),
      gpsAccuracyM: _toNullableDouble(json["gps_accuracy_m"]),
      locationStatus: json["location_status"]?.toString() ?? "unknown",
      uploadStatus: json["upload_status"]?.toString() ?? "unknown",
      aiLabel: json["ai_label"]?.toString() ?? "sound_event",
      aircraftProbability: _toNullableDouble(json["aircraft_probability"]),
      aiConfidence: _toNullableDouble(json["ai_confidence"]),
      aiInferenceStatus:
          json["ai_inference_status"]?.toString() ?? "not_available",
      aiInferenceTimeMs: _toNullableInt(json["ai_inference_time_ms"]),
      classification: ClassificationResult.fromJsonOrNull(
        json["classification"],
      ),
      uploadMode: json["upload_mode"]?.toString() ?? "detection_only",
      cloudAudioPath:
          json["cloud_audio_path"]?.toString() ??
          json["audio_path"]?.toString(),
      audioFormat: json["audio_format"]?.toString(),
      audioSizeBytes: _toNullableInt(json["audio_size_bytes"]),
      sourcePcmSizeBytes: _toNullableInt(json["source_pcm_size_bytes"]),
      audioEncodingStatus: json["audio_encoding_status"]?.toString(),
      tdoaClipPath: json["tdoa_clip_path"]?.toString(),
      tdoaClipFormat: json["tdoa_clip_format"]?.toString(),
      tdoaClipSizeBytes: _toNullableInt(json["tdoa_clip_size_bytes"]),
      tdoaClipStartSample: _toNullableInt(json["tdoa_clip_start_sample"]),
      tdoaClipEndSample: _toNullableInt(json["tdoa_clip_end_sample"]),
      tdoaClipPeakSample: _toNullableInt(json["tdoa_clip_peak_sample"]),
      tdoaClipDurationMs: _toNullableInt(json["tdoa_clip_duration_ms"]),
      tdoaClipSource: json["tdoa_clip_source"]?.toString(),
      deviceEventTimeMs: _toNullableDouble(json["device_event_time_ms"]),
      eventStartTimeMs: _toNullableDouble(json["event_start_time_ms"]),
      eventEndTimeMs: _toNullableDouble(json["event_end_time_ms"]),
      rmsPeakOffsetMs: _toNullableDouble(json["rms_peak_offset_ms"]),
      sampleRate: _toNullableInt(json["sample_rate"]),
      audioDurationMs: _toNullableDouble(json["audio_duration_ms"]),
      timeSyncVersion: _toNullableInt(json["time_sync_version"]),
      timeSyncOffsetMs: _toNullableDouble(json["time_sync_offset_ms"]),
      timeSyncRttMs: _toNullableDouble(json["time_sync_rtt_ms"]),
      timeSyncQuality: json["time_sync_quality"]?.toString(),
      timeSyncSyncedAtMs: _toNullableInt(json["time_sync_synced_at_ms"]),
      timeSyncAgeMs: _toNullableInt(json["time_sync_age_ms"]),
      timingMetadata: EventTimingMetadata.fromJsonOrNull(json),
      latencyDiagnostics: json["latency_diagnostics"]?.toString(),
      latencyTrace: json["latency_trace"] is Map
          ? Map<String, dynamic>.from(json["latency_trace"] as Map)
          : <String, dynamic>{},
    );
  }

  AudioEvent copyWith({
    String? uploadStatus,
    String? cloudAudioPath,
    String? audioFormat,
    int? audioSizeBytes,
    int? sourcePcmSizeBytes,
    String? audioEncodingStatus,
    String? tdoaClipPath,
    String? tdoaClipFormat,
    int? tdoaClipSizeBytes,
    int? tdoaClipStartSample,
    int? tdoaClipEndSample,
    int? tdoaClipPeakSample,
    int? tdoaClipDurationMs,
    String? tdoaClipSource,
    bool clearTdoaClip = false,
  }) {
    return AudioEvent(
      eventId: eventId,
      deviceId: deviceId,
      time: time,
      duration: duration,
      path: path,
      avgRms: avgRms,
      peakRms: peakRms,
      avgDb: avgDb,
      peakDb: peakDb,
      estimatedAvgDb: estimatedAvgDb,
      estimatedPeakDb: estimatedPeakDb,
      latitude: latitude,
      longitude: longitude,
      gpsSpeedMps: gpsSpeedMps,
      gpsHeadingDeg: gpsHeadingDeg,
      gpsAccuracyM: gpsAccuracyM,
      locationStatus: locationStatus,
      uploadStatus: uploadStatus ?? this.uploadStatus,
      aiLabel: aiLabel,
      aircraftProbability: aircraftProbability,
      aiConfidence: aiConfidence,
      aiInferenceStatus: aiInferenceStatus,
      aiInferenceTimeMs: aiInferenceTimeMs,
      classification: classification,
      uploadMode: uploadMode,
      cloudAudioPath: cloudAudioPath ?? this.cloudAudioPath,
      audioFormat: audioFormat ?? this.audioFormat,
      audioSizeBytes: audioSizeBytes ?? this.audioSizeBytes,
      sourcePcmSizeBytes: sourcePcmSizeBytes ?? this.sourcePcmSizeBytes,
      audioEncodingStatus: audioEncodingStatus ?? this.audioEncodingStatus,
      tdoaClipPath: clearTdoaClip ? null : tdoaClipPath ?? this.tdoaClipPath,
      tdoaClipFormat: clearTdoaClip
          ? null
          : tdoaClipFormat ?? this.tdoaClipFormat,
      tdoaClipSizeBytes: clearTdoaClip
          ? null
          : tdoaClipSizeBytes ?? this.tdoaClipSizeBytes,
      tdoaClipStartSample: clearTdoaClip
          ? null
          : tdoaClipStartSample ?? this.tdoaClipStartSample,
      tdoaClipEndSample: clearTdoaClip
          ? null
          : tdoaClipEndSample ?? this.tdoaClipEndSample,
      tdoaClipPeakSample: clearTdoaClip
          ? null
          : tdoaClipPeakSample ?? this.tdoaClipPeakSample,
      tdoaClipDurationMs: clearTdoaClip
          ? null
          : tdoaClipDurationMs ?? this.tdoaClipDurationMs,
      tdoaClipSource: clearTdoaClip
          ? null
          : tdoaClipSource ?? this.tdoaClipSource,
      deviceEventTimeMs: deviceEventTimeMs,
      eventStartTimeMs: eventStartTimeMs,
      eventEndTimeMs: eventEndTimeMs,
      rmsPeakOffsetMs: rmsPeakOffsetMs,
      sampleRate: sampleRate,
      audioDurationMs: audioDurationMs,
      timeSyncVersion: timeSyncVersion,
      timeSyncOffsetMs: timeSyncOffsetMs,
      timeSyncRttMs: timeSyncRttMs,
      timeSyncQuality: timeSyncQuality,
      timeSyncSyncedAtMs: timeSyncSyncedAtMs,
      timeSyncAgeMs: timeSyncAgeMs,
      timingMetadata: timingMetadata,
      latencyDiagnostics: latencyDiagnostics,
      latencyTrace: latencyTrace,
    );
  }

  static double _toDouble(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? "") ?? 0.0;
  }

  static double? _toNullableDouble(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString());
  }

  static int? _toNullableInt(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toInt();
    return int.tryParse(value.toString());
  }
}

class AudioUploadResponseInfo {
  final String audioPath;
  final String? audioFormat;
  final int? sizeBytes;

  const AudioUploadResponseInfo({
    required this.audioPath,
    this.audioFormat,
    this.sizeBytes,
  });
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  ThemeMode _themeMode = ThemeMode.dark;

  @override
  void initState() {
    super.initState();
    unawaited(_loadThemeMode());
  }

  Future<void> _loadThemeMode() async {
    try {
      final storedThemeMode = await ThemeModePreference.load();
      if (!mounted || storedThemeMode == _themeMode) return;
      setState(() => _themeMode = storedThemeMode);
    } catch (_) {
      // Keep the fail-safe dark default when a local preference cannot load.
    }
  }

  void _changeThemeMode(ThemeMode mode) {
    if (_themeMode != mode) {
      setState(() => _themeMode = mode);
    }
    unawaited(_saveThemeMode(mode));
  }

  Future<void> _saveThemeMode(ThemeMode mode) async {
    try {
      await ThemeModePreference.save(mode);
    } catch (_) {
      // The current session still uses the selected theme if storage fails.
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: SoundDetectorPage(
        themeMode: _themeMode,
        onThemeModeChanged: _changeThemeMode,
      ),
      debugShowCheckedModeBanner: false,
      title: "聲音偵測節點",
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: _themeMode,
    );
  }
}

class SoundDetectorPage extends StatefulWidget {
  const SoundDetectorPage({
    super.key,
    required this.themeMode,
    required this.onThemeModeChanged,
  });

  final ThemeMode themeMode;
  final ValueChanged<ThemeMode> onThemeModeChanged;

  @override
  State<SoundDetectorPage> createState() => _SoundDetectorPageState();
}

class _SoundDetectorPageState extends State<SoundDetectorPage>
    with WidgetsBindingObserver {
  static const platform = MethodChannel('sound_channel');

  // Temporary calibration offset.
  // estimated dB = dBFS + 95
  // Later, this should be calibrated with a real sound level meter.
  static const double calibrationOffsetDb = 95.0;
  static final AppConfig runtimeConfig = AppConfig.fromEnvironment();
  static const String deviceCommandPath = "/device-command";
  static const String deviceCommandAckPath = "/device-command-ack";
  static const String defaultDeviceId = "node_A01";
  static const String deviceIdPreferenceKey = "device_id";
  static const String uploadModePreferenceKey = "upload_mode";
  static const String aiModelPreferenceKey = "ai_model_id";
  static const String uploadModeDetectionOnly = "detection_only";
  static const String uploadModeCollectAll = "collect_all";
  static const int staleMetadataUploadAgeMs = 30000;
  static const int staleAudioUploadAgeMs = 300000;
  static const bool fastMetadataUploadEnabled = bool.fromEnvironment(
    'FAST_METADATA_UPLOAD_ENABLED',
    defaultValue: true,
  );
  static const bool persistentMetadataHttpClientEnabled = bool.fromEnvironment(
    'PERSISTENT_METADATA_HTTP_CLIENT_ENABLED',
    defaultValue: true,
  );
  static const bool postInferenceLatencyTracingEnabled = bool.fromEnvironment(
    'POST_INFERENCE_LATENCY_TRACING_ENABLED',
    defaultValue: true,
  );
  static const bool observationShadowEnabled = bool.fromEnvironment(
    'OBSERVATION_SHADOW_ENABLED',
    defaultValue: false,
  );
  static const bool classificationV1Enabled = bool.fromEnvironment(
    'CLASSIFICATION_V1_ENABLED',
    defaultValue: true,
  );
  static const double candidateMinEstimatedPeakDb = 70.0;
  static const bool dedicatedNodeModeEnabled = true;
  static const bool keepScreenOnEnabled = true;
  static const bool foregroundNodeServiceEnabled = false;
  static const bool autoStartListeningOnLaunch = false;
  static const bool immersiveModeEnabled = true;
  static const bool kioskModeEnabled = true;
  static const bool autoLaunchOnBootEnabled = true;

  final AudioPlayer audioPlayer = AudioPlayer();
  late final StreamSubscription<void> audioPlayerCompleteSubscription;
  final AiSoundClassifier aiClassifier = AiSoundClassifier();
  final SmartAudioUploadService smartAudioUpload = SmartAudioUploadService();
  final LiveAudioStreamService liveAudioStreamService =
      LiveAudioStreamService();
  final EventUploadQueue eventUploadQueue = EventUploadQueue();
  final MetadataUploadClient metadataUploadClient = MetadataUploadClient();
  final EventAdmissionController eventAdmissionController =
      EventAdmissionController();
  final Stopwatch postInferenceMonotonicClock = Stopwatch()..start();
  final String postInferenceMonotonicSessionId =
      '${DateTime.now().microsecondsSinceEpoch}-${Random.secure().nextInt(1 << 31)}';
  late final ObservationSequence observationSequence = ObservationSequence(
    processSessionId: postInferenceMonotonicSessionId,
  );
  late final ObservationShadowClient observationShadowClient =
      ObservationShadowClient(enabled: observationShadowEnabled);
  late final ObservationRetryDispatcher observationRetryDispatcher =
      ObservationRetryDispatcher(
        store: ObservationSqliteStore(),
        uploader: uploadQueuedObservation,
        currentProcessSessionId: postInferenceMonotonicSessionId,
        onAttempt: handleObservationQueueAttempt,
        onMetrics: handleObservationQueueMetrics,
      );
  final ObservationShadowMetrics observationShadowMetrics =
      ObservationShadowMetrics();
  ObservationQueueSnapshot? latestObservationQueueSnapshot;
  late final NodeConnectionService nodeConnectionService;

  final TextEditingController deviceIdController = TextEditingController(
    text: defaultDeviceId,
  );

  final TextEditingController backendUrlController = TextEditingController(
    text: runtimeConfig.eventsUrl,
  );

  String status = "Idle";
  String backendStatus = "Not tested";
  String lastUploadStatus = "No upload yet";
  String lastAudioUploadStatus = "No audio upload yet";
  String lastCloudAudioPath = "No cloud audio path yet";
  String lastLocationUploadStatus = "No location upload yet";
  String lastLocationUploadTime = "N/A";
  String aiModelStatus = "AI model: loading";
  String aiInferenceStatus = "No AI inference yet";
  String lastAiLabel = "N/A";
  String lastAircraftProbability = "N/A";
  String lastAiConfidence = "N/A";
  String lastAiInferenceTime = "N/A";
  String remoteCommandStatus = "No remote command yet";
  String lastRemoteCommand = "N/A";
  String lastRemoteCommandResult = "N/A";
  String nodeWebSocketStatus = "WebSocket disconnected";
  String nodeWebSocketConnectionId = "N/A";
  int nodeWebSocketReconnectCount = 0;
  String liveAudioStatus = "Live audio stopped";
  String lastTimeSyncStatus = "尚未同步";
  String lastTimeSyncAt = "N/A";
  String savedDeviceId = defaultDeviceId;
  String uploadMode = uploadModeDetectionOnly;
  String selectedAiModelId = AiSoundClassifier.defaultModelId;
  String keepScreenOnStatus = "啟用";
  String autoStartStatus = "未啟用";
  String immersiveModeStatus = "等待啟用";
  String kioskStatus = "嘗試中";
  String kioskError = "N/A";
  String bootReceiverStatus = "已設定";
  String lastAutoStartResult = "APP 啟動後等待本機或遠端開始";

  bool isListening = false;
  bool detectionEnabled = false;
  bool isUploadingLocation = false;
  bool isPollingCommand = false;
  bool isHandlingRemoteCommand = false;
  bool autoStartAttempted = false;

  double? currentLatitude;
  double? currentLongitude;
  double? currentGpsSpeedMps;
  double? currentGpsHeadingDeg;
  double? currentGpsAccuracyM;

  double currentRms = 0.0;
  final ValueNotifier<SoundLevelReading> currentSoundLevelNotifier =
      ValueNotifier(const SoundLevelReading(rms: 0));
  double currentEventPeakRms = 0.0;
  double currentEventRmsSum = 0.0;
  int currentEventRmsCount = 0;
  double? currentEventStartTimeMs;
  double? currentEventPeakTimeMs;
  double? timeSyncOffsetMs;
  double? timeSyncRttMs;
  TimeSyncMetadata? timeSyncMetadata;

  final ListeningElapsedCounter listeningElapsed = ListeningElapsedCounter();
  Timer? listeningTimer;
  Timer? locationUploadTimer;
  Timer? commandPollingTimer;
  Timer? timeSyncTimer;
  Timer? eventUploadRetryTimer;
  String? pendingLocationUploadDeviceId;
  bool isProcessingEventUploadQueue = false;
  final Set<String> fastMetadataUploadsInFlight = <String>{};
  final Set<String> audioUploadInFlightIds = <String>{};
  bool isProcessingSavedAudioWindow = false;
  Map<String, dynamic>? latestPendingAudioWindow;
  int skippedAudioWindowCount = 0;

  List<AudioEvent> events = [];
  String? playingPath;
  String? latestCloudEventId;
  int latestEventUploadQueueDepth = 0;
  int selectedDestinationIndex = 0;
  EventFilter selectedEventFilter = EventFilter.all;

  String get deviceId {
    final text = savedDeviceId.trim();
    if (text.isEmpty) return defaultDeviceId;
    return text;
  }

  String get backendUrl {
    if (backendBaseUrl.isEmpty) return "";
    return "$backendBaseUrl/events";
  }

  String get backendBaseUrl {
    final configuredUrl = normalizeBackendBaseUrl(
      appConfig.normalizedBackendBaseUrl,
    );
    if (configuredUrl.isNotEmpty) return configuredUrl;
    return normalizeBackendBaseUrl(backendUrlController.text);
  }

  String normalizeBackendBaseUrl(String value) {
    var url = value.trim();
    while (url.endsWith("/")) {
      url = url.substring(0, url.length - 1);
    }
    if (url.endsWith("/events")) {
      return url.substring(0, url.length - "/events".length);
    }
    return url;
  }

  AppConfig get appConfig => runtimeConfig;

  String get runtimeConfigErrorText {
    return appConfig.validationErrors.map((error) => error.code).join(", ");
  }

  bool get isBackendRuntimeConfigured {
    return appConfig.isRuntimeReady && backendBaseUrl.isNotEmpty;
  }

  String get selectedAiModelName {
    return AiSoundClassifier.modelOptionForId(selectedAiModelId).name;
  }

  String get uploadToken => appConfig.uploadToken.trim();

  String get audioUploadUrl {
    if (backendBaseUrl.isEmpty) return "";
    return "$backendBaseUrl/upload-audio";
  }

  String get tdoaClipUploadUrl {
    if (backendBaseUrl.isEmpty) return "";
    return "$backendBaseUrl/upload-tdoa-clip";
  }

  String get locationUpdateUrl {
    if (backendBaseUrl.isEmpty) return "";
    return "$backendBaseUrl/location-update";
  }

  String get uploadModeTitle {
    return uploadMode == uploadModeCollectAll ? "資料蒐集模式" : "偵測模式";
  }

  String get uploadModeShortTitle {
    return displayUploadMode(uploadMode);
  }

  String get uploadModeApiValue {
    return uploadMode == uploadModeCollectAll ? "collection" : "detection";
  }

  bool get isNodeWebSocketConnected {
    return nodeConnectionService.status == NodeConnectionStatus.connected;
  }

  String get aiStatusApiValue {
    final normalized = aiModelStatus.toLowerCase();
    if (normalized.contains("loaded")) return "loaded";
    if (normalized.contains("failed")) return "failed";
    return "loading";
  }

  String get appStatusApiValue {
    if (isListening) return "listening";
    if (status.toLowerCase().contains("recording")) return "recording";
    return "stopped";
  }

  String get commandPollUrl {
    return "$backendBaseUrl$deviceCommandPath/${Uri.encodeComponent(deviceId)}";
  }

  String get commandAckUrl {
    return "$backendBaseUrl$deviceCommandAckPath";
  }

  String get timeSyncUrl {
    return "$backendBaseUrl/time-sync";
  }

  String get uploadModeDescription {
    return uploadMode == uploadModeCollectAll
        ? "上傳所有聲音事件"
        : "只上傳無人機 / aircraft 目標聲";
  }

  String get uploadModeShortDescription {
    return uploadMode == uploadModeCollectAll
        ? "資料蒐集：所有事件都會上傳，方便建立資料集"
        : "偵測模式：只有目標聲才會上傳到後端";
  }

  String get mainStatusLabel {
    final normalized = status.toLowerCase();

    if (normalized.contains("uploading") || status.contains("上傳")) {
      return "上傳中";
    }

    if (normalized.contains("recording") ||
        normalized.contains("target") ||
        normalized.contains("saved + uploaded") ||
        status.contains("目標")) {
      return "目標";
    }

    if (isListening) {
      return "監聽中";
    }

    return "待命";
  }

  bool get gpsOnline {
    final hasLocationFix = currentLatitude != null && currentLongitude != null;
    final gpsBlocked =
        lastLocationUploadStatus.startsWith("GPS is disabled") ||
        lastLocationUploadStatus.startsWith("GPS permission") ||
        lastLocationUploadStatus.startsWith("GPS error");

    return hasLocationFix && !gpsBlocked;
  }

  String get gpsBadgeText {
    if (gpsOnline) return "在線";
    if (isUploadingLocation) return "更新中";
    if (lastLocationUploadStatus == "No location upload yet") return "等待中";
    return "離線";
  }

  Color get gpsBadgeColor {
    if (gpsOnline) return Colors.green;
    if (isUploadingLocation ||
        lastLocationUploadStatus == "No location upload yet") {
      return Colors.orange;
    }
    return Colors.red;
  }

  String get aiBadgeText {
    if (aiModelStatus.contains("loaded")) return "已載入";
    if (aiModelStatus.contains("failed")) return "失敗";
    return "載入中";
  }

  String get backendBadgeText {
    if (backendStatus == "Connected" || hasSuccessfulLocationUpload) {
      return "已連線";
    }
    if (backendStatus == "Not tested") return "未測試";
    return "離線";
  }

  bool get hasSuccessfulLocationUpload {
    return lastLocationUploadStatus.startsWith("Location uploaded");
  }

  String get backendStatusApiValue {
    if (isNodeWebSocketConnected ||
        backendStatus == "Connected" ||
        hasSuccessfulLocationUpload) {
      return "connected";
    }
    if (backendStatus == "Testing..." || backendStatus == "Not tested") {
      return "pending";
    }
    if (backendStatus == "Not reached") {
      return "transient_error";
    }
    return backendStatus;
  }

  bool get isTimeSyncFresh => timeSyncMetadata?.isFresh ?? false;

  double? get effectiveTimeSyncOffsetMs {
    return isTimeSyncFresh ? timeSyncMetadata?.offsetMs : null;
  }

  double? get effectiveTimeSyncRttMs {
    return isTimeSyncFresh ? timeSyncMetadata?.rttMs : null;
  }

  String get effectiveTimeSyncQuality {
    final metadata = timeSyncMetadata;
    if (metadata == null) return "missing";
    return metadata.isFresh ? metadata.quality : "stale";
  }

  String? get effectiveLastTimeSyncAt {
    final metadata = timeSyncMetadata;
    if (metadata == null) return null;
    return metadata.syncedAtIso;
  }

  double get currentEventAvgRms {
    if (currentEventRmsCount == 0) return 0.0;
    return currentEventRmsSum / currentEventRmsCount;
  }

  double? nullableDouble(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    return double.tryParse(value.toString());
  }

  int? nullableInt(dynamic value) {
    if (value == null) return null;
    if (value is num) return value.toInt();
    return int.tryParse(value.toString());
  }

  double rmsToDbfs(double rms) {
    if (rms <= 0) return -120.0;
    return 20 * log(rms / 32768.0) / ln10;
  }

  double dbfsToEstimatedDb(double dbfs) {
    return dbfs + calibrationOffsetDb;
  }

  String estimatedDbTextFromDbfs(double dbfs) {
    return "${dbfsToEstimatedDb(dbfs).toStringAsFixed(1)} dB";
  }

  String estimatedDbText(double estimatedDb) {
    return "${estimatedDb.toStringAsFixed(1)} dB";
  }

  String displayUploadMode(String mode) {
    if (mode == uploadModeCollectAll || mode == "collection") {
      return "蒐集模式";
    }
    if (mode == uploadModeDetectionOnly || mode == "detection") {
      return "偵測模式";
    }
    return mode.isEmpty ? "未設定" : mode;
  }

  String displayAiLabel(String label) {
    switch (label) {
      case "aircraft":
      case "drone":
        return "目標聲";
      case "non_aircraft":
      case "other":
        return "非目標聲";
      case "ai_failed":
        return "AI 判斷失敗";
      case "sound_event":
        return "聲音事件";
      default:
        return label.isEmpty ? "未知" : label;
    }
  }

  String displayCommand(String command) {
    switch (command) {
      case "start_listening":
        return "開始監聽";
      case "stop_listening":
        return "停止監聽";
      case "set_detection_mode":
        return "切換偵測模式";
      case "set_collection_mode":
        return "切換蒐集模式";
      case "N/A":
        return "無";
      default:
        return command.isEmpty ? "無" : command;
    }
  }

  String displayStatusText(String value) {
    if (value.isEmpty) return "無";

    final exact = <String, String>{
      "N/A": "無",
      "Idle": "待命",
      "Listening...": "監聽中...",
      "Stopped": "已停止",
      "Silent": "安靜中",
      "Recording...": "錄音中...",
      "Sound detected / Recording...": "偵測到聲音，錄音中...",
      "Getting GPS...": "取得 GPS 中...",
      "Running AI inference...": "AI 判斷中...",
      "Target detected": "偵測到目標聲",
      "Collection event saved": "蒐集事件已儲存",
      "Non-target ignored": "非目標聲，已忽略",
      "AI failed, ignored": "AI 判斷失敗，已忽略",
      "Microphone permission denied": "麥克風權限被拒絕",
      "Audio error": "音訊錯誤",
      "Start failed": "開始失敗",
      "File not found": "找不到音檔",
      "Playing audio...": "正在播放音檔...",
      "Play failed": "播放失敗",
      "Deleted event": "事件已刪除",
      "Delete failed": "刪除失敗",
      "Local records cleared": "本機紀錄已清除",
      "Loaded local records": "已載入本機紀錄",
      "Load local records failed": "載入本機紀錄失敗",
      "Device ID cannot be empty": "Device ID 不可空白",
      "No upload yet": "尚未上傳",
      "No audio upload yet": "尚未上傳音檔",
      "No cloud audio path yet": "尚無雲端音檔路徑",
      "No location upload yet": "尚未回傳位置",
      "No AI inference yet": "尚未執行 AI 判斷",
      "No remote command yet": "尚未收到遠端指令",
      "Connected": "已連線",
      "connected": "已連線",
      "Disconnected": "無法連線",
      "disconnected": "無法連線",
      "WebSocket disconnected": "WebSocket 無法連線",
      "connecting": "連線中",
      "authenticating": "驗證中",
      "degraded": "連線不穩定",
      "reconnecting": "重新連線中",
      "stopped": "已停止",
      "Available": "可用",
      "Ready": "已就緒",
      "Not synced": "尚未同步",
      "Live audio stopped": "即時音訊已停止",
      "Live audio streaming": "即時音訊串流中",
      "Not tested": "未測試",
      "Not reached": "無法連線",
      "Testing...": "測試中...",
      "Backend connected": "後端已連線",
      "Backend URL is empty": "後端 URL 不可空白",
      "Backend not reached": "後端無法連線",
      "AI model: loading": "AI 模型：載入中",
      "AI model: loaded": "AI 模型：已載入",
      "AI model: failed": "AI 模型：載入失敗",
      "AI inference: running": "AI 判斷：執行中",
      "AI inference: success": "AI 判斷：成功",
      "uploaded": "已上傳",
      "uploaded_collection_other": "蒐集模式：非目標聲已上傳",
      "uploaded_collection_failed": "蒐集模式：AI 失敗事件已上傳",
      "local_only_non_target": "非目標聲，僅儲存在本機",
      "local_only_ai_failed": "AI 失敗，僅儲存在本機",
      "pending": "等待處理",
      "ok": "正常",
      "no_location": "無位置",
      "success": "成功",
      "failed": "失敗",
      "done": "完成",
      "already listening": "已經在監聽",
      "listening started": "已開始監聽",
      "already stopped": "已經停止",
      "listening stopped": "已停止監聽",
      "Mode changed to Detection": "已切換為偵測模式",
      "Mode changed to Collection": "已切換為蒐集模式",
    };
    if (exact.containsKey(value)) return exact[value]!;

    if (value.startsWith("done: ")) {
      return "完成：${displayStatusText(value.substring(6))}";
    }
    if (value.startsWith("failed: ")) {
      return "失敗：${displayStatusText(value.substring(8))}";
    }

    if (value.startsWith("Upload mode saved:")) {
      return "上傳模式已儲存：${displayUploadMode(uploadMode)}";
    }
    if (value.startsWith("Remote mode set:")) {
      return "遠端模式已切換：${displayUploadMode(uploadMode)}";
    }
    if (value.startsWith("Device ID saved:")) {
      return value.replaceFirst("Device ID saved:", "Device ID 已儲存：");
    }
    if (value.startsWith("Backend error:")) {
      return value.replaceFirst("Backend error:", "後端錯誤：");
    }
    if (value.startsWith("Error ")) {
      return value.replaceFirst("Error ", "錯誤 ");
    }
    if (value.startsWith("AI inference:")) {
      return value.replaceFirst("AI inference:", "AI 判斷：");
    }
    if (value.startsWith("Live audio failed:")) {
      return value.replaceFirst("Live audio failed:", "即時音訊失敗：");
    }
    if (value.startsWith("Location uploaded:")) {
      return value.replaceFirst("Location uploaded:", "位置已回傳：");
    }
    if (value.startsWith("Location upload failed:")) {
      return value.replaceFirst("Location upload failed:", "位置回傳失敗：");
    }
    if (value == "Uploading location...") return "位置回傳中...";
    if (value == "Location upload timeout") return "位置回傳逾時";
    if (value == "Location network error") return "位置回傳網路錯誤";
    if (value.startsWith("Location upload error:")) {
      return value.replaceFirst("Location upload error:", "位置回傳錯誤：");
    }
    if (value == "GPS is disabled") return "GPS 已關閉";
    if (value == "GPS permission denied") return "GPS 權限被拒絕";
    if (value == "GPS permission permanently denied") {
      return "GPS 權限被永久拒絕";
    }
    if (value.startsWith("GPS error:")) {
      return value.replaceFirst("GPS error:", "GPS 錯誤：");
    }
    if (value.startsWith("Command poll failed:")) {
      return value.replaceFirst("Command poll failed:", "遠端指令輪詢失敗：");
    }
    if (value == "No pending command") return "目前沒有待執行指令";
    if (value == "Invalid command payload") return "遠端指令格式錯誤";
    if (value == "Command poll timeout") return "遠端指令輪詢逾時";
    if (value == "Command network error") return "遠端指令網路錯誤";
    if (value.startsWith("Command poll error:")) {
      return value.replaceFirst("Command poll error:", "遠端指令輪詢錯誤：");
    }
    if (value.startsWith("Executing command #")) {
      return value.replaceFirst("Executing command #", "正在執行指令 #");
    }
    if (value.startsWith("Command #") && value.endsWith(" acknowledged")) {
      return value
          .replaceFirst("Command #", "指令 #")
          .replaceFirst(" acknowledged", " 已回報");
    }
    if (value.startsWith("Command ack failed:")) {
      return value.replaceFirst("Command ack failed:", "指令回報失敗：");
    }
    if (value.startsWith("Command ack error:")) {
      return value.replaceFirst("Command ack error:", "指令回報錯誤：");
    }
    if (value == "WAV file not found, metadata saved") {
      return "找不到 WAV，metadata 已儲存";
    }
    if (value == "Audio upload failed, metadata saved") {
      return "音檔上傳失敗，metadata 已儲存";
    }
    if (value == "Metadata + audio uploaded") {
      return "metadata 與音檔已上傳";
    }
    if (value == "400: not a WAV file") return "400：不是 WAV 檔";
    if (value == "401: upload token is wrong") return "401：上傳 token 錯誤";
    if (value == "500: backend or GCS error") {
      return "500：後端或 GCS 錯誤";
    }
    if (value.startsWith("Upload failed:")) {
      return value.replaceFirst("Upload failed:", "上傳失敗：");
    }
    if (value == "Audio file not found") return "找不到音檔";
    if (value == "Uploading WAV...") return "WAV 上傳中...";
    if (value.startsWith("Audio uploaded:")) {
      return value.replaceFirst("Audio uploaded:", "音檔已上傳：");
    }
    if (value == "Network error: upload timeout") return "網路錯誤：上傳逾時";
    if (value == "Network error: cannot connect") return "網路錯誤：無法連線";
    if (value.startsWith("Network error:")) {
      return value.replaceFirst("Network error:", "網路錯誤：");
    }
    if (value == "No local WAV event to upload") {
      return "沒有可上傳的本機 WAV 事件";
    }
    if (value == "Saved + uploaded") return "已儲存並上傳";
    if (value == "Collection event uploaded") return "蒐集事件已上傳";
    if (value == "Non-target sound, saved locally only") {
      return "非目標聲，僅儲存在本機";
    }
    if (value == "AI failed, saved locally only") {
      return "AI 失敗，僅儲存在本機";
    }
    if (value.startsWith("Saved but ")) {
      return value.replaceFirst("Saved but ", "已儲存，但 ");
    }

    return value;
  }

  String displayTimeSyncQuality(String value) {
    return switch (value.toLowerCase()) {
      'good' => '良好',
      'medium' => '中等',
      'poor' => '偏低',
      'bad' => '不佳',
      'stale' => '資料已過期',
      'missing' => '尚無資料',
      _ => displayStatusText(value),
    };
  }

  Future<File> getLocalEventsFile() async {
    final dir = await getApplicationDocumentsDirectory();
    return File("${dir.path}/local_events.json");
  }

  Future<void> saveEventsToLocal() async {
    try {
      final file = await getLocalEventsFile();
      final data = events.map((event) => event.toJson()).toList();
      await file.writeAsString(jsonEncode(data));
    } catch (_) {}
  }

  Future<void> loadEventsFromLocal() async {
    try {
      final file = await getLocalEventsFile();

      if (!await file.exists()) return;

      final content = await file.readAsString();
      final decoded = jsonDecode(content);

      if (decoded is List) {
        final loadedEvents = decoded
            .map((item) => AudioEvent.fromJson(Map<String, dynamic>.from(item)))
            .toList();

        setState(() {
          events = loadedEvents;
          status = "Loaded local records";
        });
      }
    } catch (_) {
      setState(() {
        status = "Load local records failed";
      });
    }
  }

  Future<void> loadDeviceIdFromLocal() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final storedDeviceId = prefs.getString(deviceIdPreferenceKey);
      final nextDeviceId =
          storedDeviceId == null || storedDeviceId.trim().isEmpty
          ? defaultDeviceId
          : storedDeviceId.trim();

      if (!mounted) return;

      setState(() {
        savedDeviceId = nextDeviceId;
        deviceIdController.text = nextDeviceId;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        savedDeviceId = defaultDeviceId;
        deviceIdController.text = defaultDeviceId;
      });
    }
  }

  Future<void> loadUploadModeFromLocal() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final storedMode = prefs.getString(uploadModePreferenceKey);
      final nextMode = storedMode == uploadModeCollectAll
          ? uploadModeCollectAll
          : uploadModeDetectionOnly;

      if (!mounted) return;

      setState(() {
        uploadMode = nextMode;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        uploadMode = uploadModeDetectionOnly;
      });
    }
  }

  Future<void> loadAiModelPreferenceFromLocal() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final storedModelId = prefs.getString(aiModelPreferenceKey);
      final option = AiSoundClassifier.modelOptionForId(storedModelId);

      if (!mounted) return;

      setState(() {
        selectedAiModelId = option.id;
      });
    } catch (_) {
      if (!mounted) return;

      setState(() {
        selectedAiModelId = AiSoundClassifier.defaultModelId;
      });
    }
  }

  Future<void> saveUploadModeToLocal(String nextMode) async {
    if (isListening) return;

    final normalizedMode = nextMode == uploadModeCollectAll
        ? uploadModeCollectAll
        : uploadModeDetectionOnly;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(uploadModePreferenceKey, normalizedMode);

    if (!mounted) return;

    setState(() {
      uploadMode = normalizedMode;
      status = "Upload mode saved: $uploadModeShortTitle";
    });
  }

  Future<void> saveAiModelToLocal(String? nextModelId) async {
    if (nextModelId == null || nextModelId.isEmpty) return;

    if (isListening) {
      setState(() {
        status = "請先停止監聽，再切換 AI 模型";
      });
      return;
    }

    final option = AiSoundClassifier.modelOptionForId(nextModelId);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(aiModelPreferenceKey, option.id);

    if (!mounted) return;

    setState(() {
      selectedAiModelId = option.id;
      aiModelStatus = "AI model: loading";
      aiInferenceStatus = "No AI inference yet";
      status = "AI 模型切換中：${option.name}";
    });

    await loadAiModel();

    if (!mounted) return;

    setState(() {
      status = aiClassifier.isLoaded
          ? "AI 模型已切換：${aiClassifier.activeModelName}"
          : "AI 模型切換失敗：${option.name}";
    });
  }

  Future<void> applyRemoteUploadMode(String nextMode) async {
    final normalizedMode = nextMode == uploadModeCollectAll
        ? uploadModeCollectAll
        : uploadModeDetectionOnly;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(uploadModePreferenceKey, normalizedMode);

    if (!mounted) return;

    setState(() {
      uploadMode = normalizedMode;
      status = "Remote mode set: $uploadModeShortTitle";
    });

    unawaited(uploadCurrentLocation());
  }

  Future<void> saveDeviceIdToLocal() async {
    final nextDeviceId = deviceIdController.text.trim();
    final previousDeviceId = deviceId;

    if (nextDeviceId.isEmpty) {
      setState(() {
        status = "Device ID cannot be empty";
      });
      return;
    }

    if (isListening) {
      setState(() {
        status = "請先停止監聽，再切換節點 ID";
      });
      return;
    }

    final identityChanged = previousDeviceId != nextDeviceId;
    if (identityChanged) {
      await nodeConnectionService.stop(notifyStopped: false);
      stopCommandPollingTimer();

      if (!mounted) return;

      setState(() {
        nodeWebSocketStatus = "switching_device";
        nodeWebSocketConnectionId = "N/A";
        nodeWebSocketReconnectCount = 0;
        remoteCommandStatus =
            "Switching node: $previousDeviceId -> $nextDeviceId";
      });
    }

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(deviceIdPreferenceKey, nextDeviceId);

    if (!mounted) return;

    setState(() {
      savedDeviceId = nextDeviceId;
      status = identityChanged
          ? "Device ID switched: $previousDeviceId -> $nextDeviceId"
          : "Device ID saved: $nextDeviceId";
    });

    if (isBackendRuntimeConfigured) {
      unawaited(reconnectNodeControlWebSocket());
      unawaited(pollRemoteCommand());
      startCommandPollingTimer();
      await uploadCurrentLocation(overrideDeviceId: nextDeviceId);
    }
  }

  String formatListeningTime(int totalSeconds) {
    final hours = totalSeconds ~/ 3600;
    final minutes = (totalSeconds % 3600) ~/ 60;
    final seconds = totalSeconds % 60;

    return "${hours.toString().padLeft(2, '0')}:"
        "${minutes.toString().padLeft(2, '0')}:"
        "${seconds.toString().padLeft(2, '0')}";
  }

  void startListeningTimer() {
    listeningTimer?.cancel();

    listeningTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted || !isListening) return;

      setState(() {
        listeningElapsed.tick(isListening: isListening);
      });
    });
  }

  void stopListeningTimer() {
    listeningTimer?.cancel();
    listeningTimer = null;
  }

  String get currentLocationText {
    if (currentLatitude == null || currentLongitude == null) {
      return "N/A";
    }

    return "${currentLatitude!.toStringAsFixed(6)}, "
        "${currentLongitude!.toStringAsFixed(6)}";
  }

  void startLocationUploadTimer() {
    locationUploadTimer?.cancel();
    locationUploadTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      uploadCurrentLocation();
    });
  }

  void stopLocationUploadTimer() {
    locationUploadTimer?.cancel();
    locationUploadTimer = null;
  }

  void startCommandPollingTimer() {
    if (!appConfig.restFallbackEnabled) {
      return;
    }
    commandPollingTimer?.cancel();
    commandPollingTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      pollRemoteCommand();
    });
  }

  void stopCommandPollingTimer() {
    commandPollingTimer?.cancel();
    commandPollingTimer = null;
  }

  void startTimeSyncTimer() {
    timeSyncTimer?.cancel();
    timeSyncTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      syncTimeWithBackend();
    });
  }

  void stopTimeSyncTimer() {
    timeSyncTimer?.cancel();
    timeSyncTimer = null;
  }

  void startEventUploadRetryTimer() {
    eventUploadRetryTimer?.cancel();
    eventUploadRetryTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      unawaited(processEventUploadQueue());
    });
  }

  void stopEventUploadRetryTimer() {
    eventUploadRetryTimer?.cancel();
    eventUploadRetryTimer = null;
  }

  Future<void> processEventUploadQueue() async {
    if (!isBackendRuntimeConfigured) {
      return;
    }
    if (fastMetadataUploadsInFlight.isNotEmpty) return;
    if (isProcessingEventUploadQueue) return;
    isProcessingEventUploadQueue = true;
    try {
      final expired = await eventUploadQueue.discardExpired(
        metadataMaxAgeMs: staleMetadataUploadAgeMs,
        audioMaxAgeMs: staleAudioUploadAgeMs,
      );
      if (expired.isNotEmpty) {
        // ignore: avoid_print
        print(
          '[UPLOAD_QUEUE] discarded_stale=${expired.length} '
          'event_ids=${expired.map((item) => item.eventId).join(',')}',
        );
      }

      while (true) {
        final dueItems = await eventUploadQueue.dueItems(limit: 1);
        if (dueItems.isEmpty) break;
        final item = dueItems.first;
        final event = AudioEvent.fromJson(item.eventJson);
        if (event.eventId.isEmpty) {
          await eventUploadQueue.markPermanentFailure(
            item.eventId,
            "invalid_event_payload",
          );
          continue;
        }
        if (!item.metadataUploaded) {
          final metadataStatus = await uploadEventToBackend(event);
          await updateEventUploadStatus(event.eventId, metadataStatus);
          if (metadataStatus != "uploaded") {
            await eventUploadQueue.recordFailure(event.eventId, metadataStatus);
            continue;
          }
          await eventUploadQueue.markMetadataUploaded(event.eventId);
          // Re-read the queue so newly arrived metadata always stays ahead of
          // slower MP3/GCS work.
          continue;
        }

        await uploadAudioForEventInBackground(event);
      }
    } finally {
      isProcessingEventUploadQueue = false;
      unawaited(refreshEventUploadQueueDepth());
    }
  }

  Future<void> startEventCloudPipeline({required AudioEvent event}) async {
    final trace = event.latencyTrace;
    final metadataQueueStopwatch = Stopwatch()..start();
    if (postInferenceLatencyTracingEnabled) {
      trace['metadata_enqueue_started_at'] = DateTime.now()
          .toUtc()
          .millisecondsSinceEpoch;
    }
    try {
      if (fastMetadataUploadEnabled) {
        if (postInferenceLatencyTracingEnabled) {
          trace['metadata_fast_path_called_at_monotonic'] =
              postInferenceMonotonicClock.elapsedMicroseconds / 1000.0;
        }
        fastMetadataUploadsInFlight.add(event.eventId);
        try {
          final metadataStatus = await eventUploadQueue
              .enqueueWithImmediateMetadataSend(
                event.toJson(),
                () => uploadEventToBackend(event),
                onPersisted: () {
                  metadataQueueStopwatch.stop();
                  if (!postInferenceLatencyTracingEnabled) return;
                  trace['metadata_enqueue_finished_at'] = DateTime.now()
                      .toUtc()
                      .millisecondsSinceEpoch;
                  // ignore: avoid_print
                  print(
                    '[POST_INFERENCE_LATENCY] event_id=${event.eventId} '
                    'trace_id=${event.traceId} metadata_queue_ms='
                    '${metadataQueueStopwatch.elapsedMicroseconds / 1000.0}',
                  );
                },
              );
          await updateEventUploadStatus(event.eventId, metadataStatus);
        } finally {
          fastMetadataUploadsInFlight.remove(event.eventId);
        }
        unawaited(processEventUploadQueue());
        return;
      }

      await eventUploadQueue.enqueueEvent(event.toJson());
      metadataQueueStopwatch.stop();
      if (postInferenceLatencyTracingEnabled) {
        trace['metadata_enqueue_finished_at'] = DateTime.now()
            .toUtc()
            .millisecondsSinceEpoch;
      }
      unawaited(processEventUploadQueue());
    } catch (error) {
      await eventUploadQueue.recordFailure(
        event.eventId,
        "cloud_pipeline_failed",
      );
      if (!mounted) return;
      if (latestCloudEventId != null && latestCloudEventId != event.eventId) {
        return;
      }
      setState(() {
        lastUploadStatus = "cloud_pipeline_failed";
        status = "Saved locally, cloud pipeline failed";
      });
    }
  }

  Map<String, dynamic> buildNodeControlStatusPayload() {
    return {
      "recording": isListening,
      "detection_enabled": detectionEnabled,
      "streaming": liveAudioStreamService.isStreaming,
      "gps_available": gpsOnline,
      "network_type": "mobile_or_wifi",
      "app_version": "flutter-node-v4-realtime-detection-v1",
      "battery_percent": null,
      "upload_mode": uploadModeApiValue,
      "ai_status": aiStatusApiValue,
      "backend_status": backendStatusApiValue,
      "backend_http_status": backendStatusApiValue,
      "node_websocket_status": nodeWebSocketStatus,
      "app_status": appStatusApiValue,
      "last_ai_label": lastAiLabel,
      "last_upload_status": lastUploadStatus,
      "metadata_upload_status": lastUploadStatus,
      "audio_upload_status": lastAudioUploadStatus,
      "gps_upload_status": lastLocationUploadStatus,
      "last_location_upload_at": lastLocationUploadTime,
      "latitude": currentLatitude,
      "longitude": currentLongitude,
      "gps_speed_mps": currentGpsSpeedMps,
      "gps_heading_deg": currentGpsHeadingDeg,
      "gps_accuracy_m": currentGpsAccuracyM,
      "time_sync_offset_ms": effectiveTimeSyncOffsetMs,
      "time_sync_rtt_ms": effectiveTimeSyncRttMs,
      "time_sync_quality": effectiveTimeSyncQuality,
      "time_sync_at": effectiveLastTimeSyncAt,
    };
  }

  Future<void> startNodeControlWebSocket() async {
    if (!appConfig.commandWebSocketEnabled) {
      if (mounted) {
        setState(() {
          nodeWebSocketStatus = "disabled";
          remoteCommandStatus = "Command WebSocket disabled by config";
        });
      }
      return;
    }
    if (!isBackendRuntimeConfigured) {
      if (mounted) {
        setState(() {
          nodeWebSocketStatus = "configuration_error";
          remoteCommandStatus = "Config invalid: $runtimeConfigErrorText";
        });
      }
      return;
    }
    nodeConnectionService.configure(
      backendBaseUrl: backendBaseUrl,
      deviceId: deviceId,
    );
    await nodeConnectionService.start();
  }

  Future<void> reconnectNodeControlWebSocket() async {
    if (!appConfig.commandWebSocketEnabled || !isBackendRuntimeConfigured) {
      return;
    }
    await nodeConnectionService.reconnect(
      backendBaseUrl: backendBaseUrl,
      deviceId: deviceId,
    );
  }

  Future<NodeCommandExecutionResult> handleNodeControlCommand(
    NodeCommand command,
  ) async {
    try {
      switch (command.commandType) {
        case "START_DETECTION":
        case "START_RECORDING":
          if (!isListening) {
            await startListening();
          } else {
            await platform.invokeMethod("setDetectionEnabled", true);
            if (!detectionEnabled) {
              nodeConnectionService.detectionState.startSession();
            }
            if (mounted) {
              setState(() {
                detectionEnabled = true;
                status = "Listening...";
              });
            }
          }
          return const NodeCommandExecutionResult(
            success: true,
            message: "listening started",
          );
        case "STOP_DETECTION":
        case "STOP_RECORDING":
          if (!isListening || liveAudioStreamService.isStreaming) {
            nodeConnectionService.stopDetection();
          }
          if (liveAudioStreamService.isStreaming && isListening) {
            await platform.invokeMethod("setDetectionEnabled", false);
            if (mounted) {
              setState(() {
                detectionEnabled = false;
                status = "Detection stopped, live audio continues";
              });
            }
          } else if (isListening) {
            await stopListening();
          }
          return const NodeCommandExecutionResult(
            success: true,
            message: "detection stopped",
          );
        case "UPDATE_CONFIG":
          final requestedMode = command.args["upload_mode"]?.toString();
          if (requestedMode == uploadModeCollectAll ||
              requestedMode == "collection" ||
              requestedMode == "collect_all") {
            await applyRemoteUploadMode(uploadModeCollectAll);
            return const NodeCommandExecutionResult(
              success: true,
              message: "collection mode applied",
            );
          }
          if (requestedMode == uploadModeDetectionOnly ||
              requestedMode == "detection" ||
              requestedMode == "detection_only") {
            await applyRemoteUploadMode(uploadModeDetectionOnly);
            return const NodeCommandExecutionResult(
              success: true,
              message: "detection mode applied",
            );
          }
          return const NodeCommandExecutionResult(
            success: false,
            message: "unsupported config payload",
          );
        case "REQUEST_STATUS":
          await nodeConnectionService.sendStatusUpdate();
          return const NodeCommandExecutionResult(
            success: true,
            message: "status sent",
          );
        case "SYNC_TIME":
          await syncTimeWithBackend();
          return const NodeCommandExecutionResult(
            success: true,
            message: "time sync requested",
          );
        case "START_LIVE_AUDIO":
          return startLiveAudioFromCommand(command.args);
        case "STOP_LIVE_AUDIO":
          return stopLiveAudioFromCommand();
        default:
          return NodeCommandExecutionResult(
            success: false,
            message: "unsupported command: ${command.commandType}",
          );
      }
    } catch (error) {
      return NodeCommandExecutionResult(
        success: false,
        message: error.toString(),
      );
    }
  }

  Future<NodeCommandExecutionResult> startLiveAudioFromCommand(
    Map<String, dynamic> args,
  ) async {
    final streamId = args["stream_id"]?.toString() ?? "";
    final streamToken = args["stream_token"]?.toString() ?? "";
    if (streamId.isEmpty || streamToken.isEmpty) {
      return const NodeCommandExecutionResult(
        success: false,
        message: "missing live audio stream session",
      );
    }

    try {
      if (!appConfig.liveAudioEnabled) {
        return const NodeCommandExecutionResult(
          success: false,
          message: "live audio disabled by config",
        );
      }
      final wasListening = isListening;
      if (!isListening) {
        await startListening();
      }
      await liveAudioStreamService.start(
        backendBaseUrl: backendBaseUrl,
        deviceId: deviceId,
        uploadToken: uploadToken,
        streamId: streamId,
        streamToken: streamToken,
      );
      await platform.invokeMethod("startLiveAudio");
      if (!wasListening) {
        nodeConnectionService.stopDetection();
        await platform.invokeMethod("setDetectionEnabled", false);
      }
      if (mounted) {
        setState(() {
          liveAudioStatus = "Live audio streaming";
          if (!wasListening) {
            detectionEnabled = false;
            status = "Live audio only";
          }
        });
      }
      unawaited(nodeConnectionService.sendStatusUpdate());
      return const NodeCommandExecutionResult(
        success: true,
        message: "live audio started",
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          liveAudioStatus = "Live audio failed: $error";
        });
      }
      return NodeCommandExecutionResult(
        success: false,
        message: "live audio failed: $error",
      );
    }
  }

  Future<NodeCommandExecutionResult> stopLiveAudioFromCommand() async {
    try {
      await platform.invokeMethod("stopLiveAudio");
      await liveAudioStreamService.stop();
      if (isListening && !detectionEnabled) {
        await stopListening();
      }
      if (mounted) {
        setState(() {
          liveAudioStatus = "Live audio stopped";
        });
      }
      unawaited(nodeConnectionService.sendStatusUpdate());
      return const NodeCommandExecutionResult(
        success: true,
        message: "live audio stopped",
      );
    } catch (error) {
      return NodeCommandExecutionResult(
        success: false,
        message: "stop live audio failed: $error",
      );
    }
  }

  String formatDateTime(DateTime value) {
    final local = value.toLocal();
    return "${local.year.toString().padLeft(4, '0')}-"
        "${local.month.toString().padLeft(2, '0')}-"
        "${local.day.toString().padLeft(2, '0')} "
        "${local.hour.toString().padLeft(2, '0')}:"
        "${local.minute.toString().padLeft(2, '0')}:"
        "${local.second.toString().padLeft(2, '0')}";
  }

  String formatAiDouble(double? value) {
    if (value == null) return "N/A";
    return value.toStringAsFixed(6);
  }

  Future<void> applyImmersiveMode() async {
    if (!immersiveModeEnabled) return;

    try {
      await SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
      if (!mounted) return;

      setState(() {
        immersiveModeStatus = "啟用";
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        immersiveModeStatus = "啟用失敗";
        kioskError = "immersive: $error";
      });
    }
  }

  Future<void> attemptEnterKioskMode() async {
    if (!kioskModeEnabled) {
      if (!mounted) return;
      setState(() {
        kioskStatus = "未啟用";
      });
      return;
    }

    try {
      final available =
          await platform.invokeMethod<bool>("isKioskModeAvailable") ?? false;
      final result = await platform.invokeMethod<dynamic>("enterKioskMode");

      var entered = false;
      var state = 0;
      if (result is Map) {
        entered = result["success"] == true;
        final stateValue = result["state"];
        if (stateValue is num) {
          state = stateValue.toInt();
        }
      } else if (result is bool) {
        entered = result;
      }

      if (!mounted) return;
      setState(() {
        if (available || (entered && state != 0)) {
          kioskStatus = "已啟用";
        } else if (entered) {
          kioskStatus = "需授權";
        } else {
          kioskStatus = "不支援";
        }
        kioskError = available ? "N/A" : "需要 Device Owner 或系統白名單";
      });
    } on PlatformException catch (error) {
      if (!mounted) return;
      setState(() {
        kioskStatus = "需授權";
        kioskError = error.message ?? error.code;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        kioskStatus = "需授權";
        kioskError = error.toString();
      });
    }
  }

  Future<void> configureDedicatedNodeRuntime() async {
    if (mounted) {
      setState(() {
        keepScreenOnStatus = keepScreenOnEnabled ? "啟用" : "未啟用";
        bootReceiverStatus = autoLaunchOnBootEnabled ? "已設定" : "未啟用";
      });
    }

    if (foregroundNodeServiceEnabled) {
      try {
        await platform.invokeMethod("startForegroundNodeService");
      } catch (_) {
        // Foreground service is a stability aid; node runtime can still continue.
      }
    }

    await applyImmersiveMode();
    await attemptEnterKioskMode();
  }

  Future<void> initializeDedicatedNode() async {
    await configureDedicatedNodeRuntime();
    await loadUploadModeFromLocal();
    await loadDeviceIdFromLocal();
    await loadAiModelPreferenceFromLocal();
    await loadAiModel();

    if (!mounted) return;

    if (!isBackendRuntimeConfigured) {
      setState(() {
        backendStatus = "Configuration error";
        status = "Configuration error: $runtimeConfigErrorText";
        remoteCommandStatus = "Config invalid: $runtimeConfigErrorText";
        lastUploadStatus = "Config invalid";
        lastAudioUploadStatus = "Config invalid";
        lastLocationUploadStatus = "Config invalid";
        lastTimeSyncStatus = "Config invalid";
      });
      await autoStartListeningOnce();
      return;
    }

    if (observationShadowEnabled) {
      await observationRetryDispatcher.initialize();
      observationRetryDispatcher.wake(forceNetworkProbe: true);
    }

    unawaited(startNodeControlWebSocket());
    unawaited(testBackendConnection());
    unawaited(syncTimeWithBackend());
    startTimeSyncTimer();
    startEventUploadRetryTimer();
    unawaited(processEventUploadQueue());
    unawaited(uploadCurrentLocation());
    startLocationUploadTimer();
    unawaited(pollRemoteCommand());
    startCommandPollingTimer();
    await autoStartListeningOnce();
  }

  Future<void> autoStartListeningOnce() async {
    if (!autoStartListeningOnLaunch) {
      if (!mounted) return;
      setState(() {
        autoStartStatus = "未啟用";
        lastAutoStartResult = "APP 啟動後等待本機或遠端開始";
      });
      return;
    }

    if (autoStartAttempted) return;

    autoStartAttempted = true;
    if (!mounted) return;

    setState(() {
      autoStartStatus = "啟動中";
      lastAutoStartResult = "初始化完成，自動開始偵測";
    });

    if (isListening) {
      setState(() {
        autoStartStatus = "已啟用";
        lastAutoStartResult = "已在監聽中";
      });
      return;
    }

    await startListening();
    await Future<void>.delayed(const Duration(milliseconds: 300));

    if (!mounted) return;
    setState(() {
      autoStartStatus = isListening ? "已啟用" : "啟動失敗";
      lastAutoStartResult = isListening ? "已自動開始偵測" : "自動開始偵測失敗";
      if (!isListening) {
        status = "自動開始偵測失敗";
      }
    });
  }

  Future<void> loadAiModel() async {
    try {
      await aiClassifier.load(modelId: selectedAiModelId);
      if (!mounted) return;

      setState(() {
        aiModelStatus = "AI model: loaded";
        selectedAiModelId = aiClassifier.activeModelId;
      });
    } catch (error) {
      // ignore: avoid_print
      print("AI model load failed: $error");
      if (!mounted) return;

      setState(() {
        aiModelStatus = "AI model: failed";
      });
    }
  }

  Future<AiInferenceResult> runAiInference(String wavPath) async {
    if (!aiClassifier.isLoaded) {
      final result = AiInferenceResult.failure(
        status: "model_not_loaded",
        inferenceTimeMs: 0,
      );
      updateAiInferenceUi(result);
      return result;
    }

    if (mounted) {
      setState(() {
        aiInferenceStatus = "AI inference: running";
      });
    }

    final result = await aiClassifier.runOnWav(wavPath);
    updateAiInferenceUi(result);

    // ignore: avoid_print
    print("AI label: ${result.label}");
    // ignore: avoid_print
    print("AI probability_aircraft: ${result.aircraftProbability}");
    // ignore: avoid_print
    print("AI confidence: ${result.confidence}");
    // ignore: avoid_print
    print("AI inference status: ${result.status}");
    // ignore: avoid_print
    print("AI inference time ms: ${result.inferenceTimeMs}");

    return result;
  }

  void updateAiInferenceUi(AiInferenceResult result) {
    if (!mounted) return;

    setState(() {
      aiInferenceStatus = result.success
          ? "AI inference: success"
          : "AI inference: ${result.status}";
      lastAiLabel = eventLabelForAiResult(result);
      lastAircraftProbability = formatAiDouble(result.aircraftProbability);
      lastAiConfidence = formatAiDouble(result.confidence);
      lastAiInferenceTime = "${result.inferenceTimeMs} ms";
    });
  }

  String _latencyPart(String key, num? value, {int fractionDigits = 1}) {
    if (value == null || !value.isFinite) return "";
    return "$key=${value.toStringAsFixed(fractionDigits)}";
  }

  String buildLatencyDiagnostics({
    required Map<String, dynamic> nativeData,
    required double flutterReceivedAtMs,
    required double aiStartedAtMs,
    required double aiDurationMs,
    required double? eventEndTimeMs,
  }) {
    final nativeWindowReadyMs = nullableDouble(
      nativeData["native_window_ready_time_ms"],
    );
    final nativeEmitMs = nullableDouble(
      nativeData["native_flutter_emit_time_ms"],
    );
    final nativeQueueDelayMs = nullableDouble(
      nativeData["native_queue_delay_ms"],
    );
    final nativeSaveDurationMs = nullableDouble(
      nativeData["native_save_duration_ms"],
    );
    final nativeEmitDelayMs = nullableDouble(
      nativeData["native_emit_delay_ms"],
    );
    final windowHopMs = nullableDouble(nativeData["window_hop_ms"]);

    final parts = [
      _latencyPart("window_hop_ms", windowHopMs, fractionDigits: 0),
      _latencyPart("native_queue_delay_ms", nativeQueueDelayMs),
      _latencyPart("native_save_duration_ms", nativeSaveDurationMs),
      _latencyPart("native_emit_delay_ms", nativeEmitDelayMs),
      _latencyPart(
        "native_to_flutter_ms",
        nativeEmitMs == null ? null : flutterReceivedAtMs - nativeEmitMs,
      ),
      _latencyPart(
        "window_ready_to_flutter_ms",
        nativeWindowReadyMs == null
            ? null
            : flutterReceivedAtMs - nativeWindowReadyMs,
      ),
      _latencyPart(
        "flutter_queue_wait_ms",
        nativeEmitMs == null ? null : aiStartedAtMs - nativeEmitMs,
      ),
      _latencyPart("ai_monotonic_ms", aiDurationMs),
      _latencyPart(
        "event_end_to_ai_start_ms",
        eventEndTimeMs == null ? null : aiStartedAtMs - eventEndTimeMs,
      ),
    ].where((part) => part.isNotEmpty).toList();

    final text = parts.join("; ");
    // ignore: avoid_print
    print("[LATENCY] $text");
    return text;
  }

  String buildEventNote(AudioEvent event) {
    final parts = [
      "avg_rms=${event.avgRms}",
      "avg_db=${event.avgDb}",
      "peak_db=${event.peakDb}",
      "estimated_avg_db=${event.estimatedAvgDb}",
      "estimated_peak_db=${event.estimatedPeakDb}",
      "upload_mode=${event.uploadMode}",
    ];

    if (event.aircraftProbability != null && event.aiConfidence != null) {
      parts.add(
        "probability_aircraft=${event.aircraftProbability!.toStringAsFixed(6)}",
      );
      parts.add("confidence=${event.aiConfidence!.toStringAsFixed(6)}");
      if (!isTargetSoundLabel(event.aiLabel)) {
        parts.add("debug_non_target=true");
      }
      if (event.aiInferenceTimeMs != null) {
        parts.add("ai_inference_time_ms=${event.aiInferenceTimeMs}");
      }
    } else {
      parts.add("ai_inference_failed=${event.aiInferenceStatus}");
    }

    if (event.timeSyncOffsetMs != null) {
      parts.add(
        "time_sync_offset_ms=${event.timeSyncOffsetMs!.toStringAsFixed(1)}",
      );
    }
    if (event.timeSyncRttMs != null) {
      parts.add("time_sync_rtt_ms=${event.timeSyncRttMs!.toStringAsFixed(1)}");
    }
    if (event.rmsPeakOffsetMs != null) {
      parts.add(
        "rms_peak_offset_ms=${event.rmsPeakOffsetMs!.toStringAsFixed(1)}",
      );
    }
    if (event.timingMetadata != null) {
      final timing = event.timingMetadata!;
      parts.add("timing_source=${timing.timingSource}");
      parts.add("event_start_sample=${timing.eventStartSample}");
      parts.add("rms_peak_sample=${timing.rmsPeakSample}");
      parts.add("sample_rate_hz=${timing.sampleRateHz}");
    }
    if (event.audioEncodingStatus != null) {
      parts.add("audio_encoding_status=${event.audioEncodingStatus}");
    }
    if (event.audioFormat != null) {
      parts.add("audio_format=${event.audioFormat}");
    }
    if (event.tdoaClipSource != null) {
      parts.add("tdoa_clip_source=${event.tdoaClipSource}");
    }
    if (event.latencyDiagnostics != null &&
        event.latencyDiagnostics!.trim().isNotEmpty) {
      parts.add("latency=${event.latencyDiagnostics}");
    }

    return parts.join(", ");
  }

  bool isTargetSoundLabel(String label) {
    return isOperationalTargetLabel(label);
  }

  Future<void> vibrateForTargetDetected() async {
    final hasVibrator = await Vibration.hasVibrator();
    if (hasVibrator) {
      await Vibration.vibrate(duration: 180);
    }
  }

  String eventLabelForAiResult(AiInferenceResult result) {
    if (!result.success) return "ai_failed";
    if (result.label == "aircraft" || result.label == "drone") {
      return result.label;
    }
    if (result.label == "other") return "other";
    return "non_aircraft";
  }

  Future<ObservationUploadResult> uploadQueuedObservation(
    Map<String, dynamic> payload,
  ) async {
    final url = runtimeConfig.observationShadowUrl;
    if (!observationShadowEnabled ||
        url.isEmpty ||
        !isBackendRuntimeConfigured) {
      return const ObservationUploadResult(
        status: ObservationUploadStatus.disabled,
        payloadBytes: 0,
        estimatedRequestBytes: 0,
        httpDurationMs: 0,
        error: 'observation_shadow_disabled_or_unconfigured',
      );
    }
    return observationShadowClient.uploadJsonWithTelemetry(
      uri: Uri.parse(url),
      uploadToken: uploadToken,
      payload: payload,
    );
  }

  Future<void> enqueueTargetObservationShadow(
    ObservationShadowPayload observation,
  ) async {
    try {
      final result = await observationRetryDispatcher.enqueuePayload(
        observation.toJson(),
      );
      if (!result.retained) {
        // ignore: avoid_print
        print(
          '[OBSERVATION_QUEUE] observation_id=${observation.observationId} '
          'status=overflow_not_retained overflow_count=${result.overflowCount}',
        );
      }
    } catch (error) {
      // A persistence failure is explicit telemetry. HTTP is never attempted
      // because durable-before-send is the reliability boundary.
      // ignore: avoid_print
      print(
        '[OBSERVATION_QUEUE] observation_id=${observation.observationId} '
        'status=persist_failed error=${error.runtimeType}',
      );
    }
  }

  void handleObservationQueueAttempt(ObservationQueueAttemptEvent event) {
    final observation = event.record.payload;
    final result = event.result;
    observationShadowMetrics.uploadAttemptCount += 1;
    observationShadowMetrics.payloadBytes += result.payloadBytes;
    observationShadowMetrics.estimatedRequestBytes +=
        result.estimatedRequestBytes;
    if (result.status == ObservationUploadStatus.uploaded) {
      observationShadowMetrics.observationUploadedCount += 1;
      if (event.record.processSessionId == postInferenceMonotonicSessionId) {
        observationShadowMetrics.currentProcessObservationUploadedCount += 1;
      } else {
        observationShadowMetrics.recoveredObservationUploadedCount += 1;
      }
    } else if (result.status == ObservationUploadStatus.failed) {
      observationShadowMetrics.observationUploadFailedCount += 1;
    }
    // ignore: avoid_print
    print(
      '[OBSERVATION_SHADOW] observation_id=${event.record.observationId} '
      'process_session_id=${event.record.processSessionId} '
      'sequence=${event.record.sequence} status=${result.status.name} '
      'attempt_count=${event.record.attemptCount} retry=${event.isRetry} '
      'payload_bytes=${result.payloadBytes} '
      'estimated_request_bytes=${result.estimatedRequestBytes} '
      'http_duration_ms=${result.httpDurationMs.toStringAsFixed(1)} '
      'http_status=${result.statusCode} '
      'error=${result.error} '
      'metrics=${jsonEncode(<String, dynamic>{...observationShadowMetrics.toJson(), ...event.queue.toJson()})}',
    );
    // Machine-readable field sample. Monotonic values remain scoped to this
    // App process. Bounded chunks prevent Android logcat line truncation.
    final fieldSample = <String, dynamic>{
      'observation_id': event.record.observationId,
      'device_id': event.record.deviceId,
      'process_session_id': event.record.processSessionId,
      'sequence': event.record.sequence,
      'observed_at': event.record.observedAt,
      'event_time_ms': event.record.eventTimeMs,
      'status': result.status.name,
      'attempt_count': event.record.attemptCount,
      'retry': event.isRetry,
      'payload_bytes': result.payloadBytes,
      'estimated_request_bytes': result.estimatedRequestBytes,
      'http_duration_ms': result.httpDurationMs,
      'http_status': result.statusCode,
      'error': result.error,
      'classification': observation['classification'],
      'time_sync': observation['time_sync'],
      'queue': event.queue.toJson(),
      'reconciliation': <String, dynamic>{
        ...observationShadowMetrics.toJson(),
        ...event.queue.toJson(),
      },
    };
    for (final line in encodeObservationShadowFieldLogLines(fieldSample)) {
      // ignore: avoid_print
      print(line);
    }
    if (mounted) {
      setState(() {
        latestObservationQueueSnapshot = event.queue;
      });
    } else {
      latestObservationQueueSnapshot = event.queue;
    }
    logObservationShadowMetrics('upload_${result.status.name}');
  }

  void handleObservationQueueMetrics(
    String reason,
    ObservationQueueSnapshot snapshot,
  ) {
    if (mounted) {
      setState(() {
        latestObservationQueueSnapshot = snapshot;
      });
    } else {
      latestObservationQueueSnapshot = snapshot;
    }
    logObservationShadowMetrics('queue_$reason');
  }

  void logObservationShadowMetrics(String reason) {
    if (!observationShadowEnabled) return;
    // ignore: avoid_print
    print(
      '[OBSERVATION_SHADOW_METRICS] '
      '${jsonEncode(<String, dynamic>{'reason': reason, ...observationShadowMetrics.toJson(), ...?latestObservationQueueSnapshot?.toJson()})}',
    );
  }

  String audioUploadLabelForEvent(AudioEvent event) {
    if (isTargetSoundLabel(event.aiLabel)) {
      return event.aiLabel;
    }
    if (event.aiLabel == "ai_failed" || event.aiInferenceStatus != "success") {
      return "ai_failed";
    }
    return event.aiLabel == "other" ? "other" : "non_aircraft";
  }

  String audioUploadCategoryForEvent(AudioEvent event) {
    return isTargetSoundLabel(event.aiLabel) ? "drone" : "other";
  }

  Future<void> uploadAudioForEventInBackground(AudioEvent event) async {
    if (event.eventId.isEmpty || !audioUploadInFlightIds.add(event.eventId)) {
      return;
    }
    try {
      await _uploadAudioForEventInBackground(event);
    } finally {
      audioUploadInFlightIds.remove(event.eventId);
    }
  }

  Future<void> _uploadAudioForEventInBackground(AudioEvent event) async {
    final wavFilePath = event.path;
    // ignore: avoid_print
    print('background wav file path: $wavFilePath');

    final wavFile = File(wavFilePath);
    final wavExists =
        wavFilePath.toLowerCase().endsWith(".wav") && await wavFile.exists();

    if (!wavExists) {
      await eventUploadQueue.markPermanentFailure(
        event.eventId,
        "wav_file_not_found",
      );
      if (!mounted) return;
      if (latestCloudEventId != null && latestCloudEventId != event.eventId) {
        return;
      }

      setState(() {
        lastAudioUploadStatus = "WAV file not found, metadata saved";
      });
      return;
    }

    updateAudioUploadUi("Preparing smart audio...", eventId: event.eventId);

    SmartAudioResult smartAudio;
    try {
      smartAudio = await smartAudioUpload.prepare(
        wavPath: wavFilePath,
        eventId: event.eventId,
      );
    } catch (error) {
      // ignore: avoid_print
      print('[AUDIO_PIPELINE] smart_audio_prepare_failed=$error');
      await eventUploadQueue.recordFailure(event.eventId, "mp3_encode_failed");
      updateAudioUploadUi(
        "MP3 conversion failed, metadata saved",
        eventId: event.eventId,
      );
      return;
    }

    final primaryUpload = await uploadPrimaryAudioFile(
      eventId: event.eventId,
      deviceId: event.deviceId,
      filePath: smartAudio.primaryAudio.path,
      label: audioUploadLabelForEvent(event),
      category: audioUploadCategoryForEvent(event),
      audioFormat: smartAudio.primaryAudio.format,
    );

    if (!mounted) return;

    if (primaryUpload == null) {
      await eventUploadQueue.recordFailure(
        event.eventId,
        "primary_audio_upload_failed",
      );
      if (latestCloudEventId == null || latestCloudEventId == event.eventId) {
        setState(() {
          lastAudioUploadStatus = "Audio upload failed, metadata saved";
        });
      }
      // Keep generated files for manual retry/debug when primary upload fails.
      return;
    }

    final latestIndex = events.indexWhere(
      (item) => item.eventId == event.eventId,
    );
    final latestEvent = latestIndex == -1 ? event : events[latestIndex];
    final updatedEvent = latestEvent.copyWith(
      cloudAudioPath: primaryUpload.audioPath,
      audioFormat: primaryUpload.audioFormat ?? smartAudio.primaryAudio.format,
      audioSizeBytes:
          primaryUpload.sizeBytes ?? smartAudio.primaryAudio.sizeBytes,
      sourcePcmSizeBytes: smartAudio.sourcePcmSizeBytes,
      audioEncodingStatus: smartAudio.primaryAudio.encodingStatus,
      clearTdoaClip: true,
    );

    await updateEventAudioMetadata(updatedEvent);
    final metadataRefreshStatus = await uploadEventToBackend(updatedEvent);

    final saving = smartAudio.savingPercent;
    // ignore: avoid_print
    print(
      '[AUDIO_PIPELINE] primaryFormat=${updatedEvent.audioFormat} '
      'sourcePcmBytes=${updatedEvent.sourcePcmSizeBytes} '
      'primaryBytes=${updatedEvent.audioSizeBytes} '
      'encodingMs=${smartAudio.primaryAudio.encodingMs} '
      'savingPercent=${saving == null ? 'N/A' : saving.toStringAsFixed(1)} '
      'metadataRefresh=$metadataRefreshStatus',
    );

    await smartAudioUpload.cleanupUploadedTemporaryFiles(
      smartAudio.temporaryPaths,
      originalWavPath: wavFilePath,
    );

    if (!mounted) return;
    if (metadataRefreshStatus == "uploaded") {
      await eventUploadQueue.markCompleted(event.eventId);
    } else {
      await eventUploadQueue.recordFailure(
        event.eventId,
        "metadata_refresh_$metadataRefreshStatus",
      );
    }
    if (latestCloudEventId == null || latestCloudEventId == event.eventId) {
      setState(() {
        lastAudioUploadStatus = "Metadata + MP3 uploaded";
        lastCloudAudioPath = primaryUpload.audioPath;
      });
    }
  }

  void updateLocationUploadStatus(
    String uploadStatus, {
    bool refreshTime = false,
  }) {
    if (!mounted) return;

    setState(() {
      lastLocationUploadStatus = uploadStatus;
      if (refreshTime) {
        lastLocationUploadTime = formatDateTime(DateTime.now());
      }
    });
  }

  Future<Position?> getCurrentLocationForUpload() async {
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        updateLocationUploadStatus("GPS is disabled", refreshTime: true);
        return null;
      }

      LocationPermission permission = await Geolocator.checkPermission();

      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }

      if (permission == LocationPermission.denied) {
        updateLocationUploadStatus("GPS permission denied", refreshTime: true);
        return null;
      }

      if (permission == LocationPermission.deniedForever) {
        updateLocationUploadStatus(
          "GPS permission permanently denied",
          refreshTime: true,
        );
        return null;
      }

      return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );
    } catch (error) {
      updateLocationUploadStatus("GPS error: $error", refreshTime: true);
      return null;
    }
  }

  Future<void> syncTimeWithBackend() async {
    if (!isBackendRuntimeConfigured) {
      if (mounted) {
        setState(() {
          lastTimeSyncStatus = "time sync skipped: config invalid";
        });
      }
      return;
    }

    try {
      final uri = Uri.parse(timeSyncUrl);
      final samples = <TimeSyncSample>[];

      for (var index = 0; index < 3; index += 1) {
        final clientSendMs = DateTime.now().millisecondsSinceEpoch;
        final response = await http
            .get(uri)
            .timeout(const Duration(seconds: 5));
        final clientReceiveMs = DateTime.now().millisecondsSinceEpoch;

        if (response.statusCode != 200) {
          throw HttpException("time sync failed: ${response.statusCode}");
        }

        final body = jsonDecode(response.body);
        if (body is! Map<String, dynamic>) {
          throw const FormatException("invalid time sync response");
        }

        final serverTimeMs = nullableDouble(body["server_time_ms"]);
        if (serverTimeMs == null) {
          throw const FormatException("missing server_time_ms");
        }

        samples.add(
          TimeSyncSample(
            clientSendMs: clientSendMs,
            serverTimeMs: serverTimeMs.round(),
            clientReceiveMs: clientReceiveMs,
          ),
        );

        if (index < 2) {
          await Future<void>.delayed(const Duration(milliseconds: 120));
        }
      }

      final bestSample = bestTimeSyncSample(samples);
      if (bestSample == null) {
        throw const FormatException("no valid time sync sample");
      }

      final metadata = bestSample.toMetadata();
      // ignore: avoid_print
      print(
        '[TIME_SYNC] attempts=${samples.length} '
        'selectedRttMs=${metadata.rttMs.toStringAsFixed(1)} '
        'offsetMs=${metadata.offsetMs.toStringAsFixed(1)} '
        'quality=${metadata.quality}',
      );

      if (mounted) {
        setState(() {
          timeSyncMetadata = metadata;
          timeSyncOffsetMs = metadata.offsetMs;
          timeSyncRttMs = metadata.rttMs;
          lastTimeSyncStatus =
              "time sync ${metadata.quality} (${metadata.rttMs.toStringAsFixed(1)} ms)";
          lastTimeSyncAt = formatDateTime(DateTime.now());
        });
      }
    } on TimeoutException {
      if (mounted) {
        setState(() {
          lastTimeSyncStatus = "time sync failed: timeout";
          lastTimeSyncAt = formatDateTime(DateTime.now());
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          lastTimeSyncStatus = "time sync failed: $error";
          lastTimeSyncAt = formatDateTime(DateTime.now());
        });
      }
    }
  }

  Future<void> uploadCurrentLocation({String? overrideDeviceId}) async {
    if (!isBackendRuntimeConfigured) {
      updateLocationUploadStatus("Location skipped: config invalid");
      return;
    }
    final currentUploadDeviceId = (overrideDeviceId ?? deviceId).trim();
    if (currentUploadDeviceId.isEmpty) {
      updateLocationUploadStatus("Location skipped: device_id empty");
      return;
    }
    if (isUploadingLocation) {
      final requestedDeviceId = overrideDeviceId?.trim();
      if (requestedDeviceId != null && requestedDeviceId.isNotEmpty) {
        pendingLocationUploadDeviceId = requestedDeviceId;
      }
      return;
    }
    isUploadingLocation = true;

    try {
      final position = await getCurrentLocationForUpload();
      if (position == null) return;

      if (!mounted) return;

      setState(() {
        currentLatitude = position.latitude;
        currentLongitude = position.longitude;
        currentGpsSpeedMps = position.speed.isFinite ? position.speed : null;
        currentGpsHeadingDeg = position.heading.isFinite
            ? position.heading
            : null;
        currentGpsAccuracyM = position.accuracy.isFinite
            ? position.accuracy
            : null;
        lastLocationUploadStatus = "Uploading location...";
      });

      // ignore: avoid_print
      print('Location update URL: $locationUpdateUrl');
      // ignore: avoid_print
      print('Location update device_id: $currentUploadDeviceId');
      final response = await http
          .post(
            Uri.parse(locationUpdateUrl),
            headers: {"Content-Type": "application/json"},
            body: jsonEncode({
              "device_id": currentUploadDeviceId,
              "latitude": position.latitude,
              "longitude": position.longitude,
              "gps_speed_mps": position.speed.isFinite ? position.speed : null,
              "gps_heading_deg": position.heading.isFinite
                  ? position.heading
                  : null,
              "gps_accuracy_m": position.accuracy.isFinite
                  ? position.accuracy
                  : null,
              "is_listening": isListening,
              "upload_mode": uploadModeApiValue,
              "battery": null,
              "ai_status": aiStatusApiValue,
              "backend_status": "connected",
              "backend_http_status": backendStatusApiValue,
              "node_websocket_status": nodeWebSocketStatus,
              "app_status": appStatusApiValue,
              "last_ai_label": lastAiLabel == "N/A" ? null : lastAiLabel,
              "last_upload_status": lastUploadStatus,
              "metadata_upload_status": lastUploadStatus,
              "audio_upload_status": lastAudioUploadStatus,
              "gps_upload_status": lastLocationUploadStatus,
              "last_location_upload_at": DateTime.now()
                  .toUtc()
                  .toIso8601String(),
              "time_sync_offset_ms": effectiveTimeSyncOffsetMs,
              "time_sync_rtt_ms": effectiveTimeSyncRttMs,
              "time_sync_quality": effectiveTimeSyncQuality,
              "time_sync_at": effectiveLastTimeSyncAt,
              "last_time_sync_at": effectiveLastTimeSyncAt,
            }),
          )
          .timeout(const Duration(seconds: 15));

      // ignore: avoid_print
      print('location update status code: ${response.statusCode}');
      // ignore: avoid_print
      print('location update response body: ${response.body}');

      if (mounted) {
        setState(() {
          backendStatus = response.statusCode == 200
              ? "Connected"
              : "Error ${response.statusCode}";
        });
      }

      updateLocationUploadStatus(
        response.statusCode == 200
            ? "Location uploaded: ${response.statusCode} ($currentUploadDeviceId)"
            : "Location upload failed: ${response.statusCode}",
        refreshTime: true,
      );
    } on TimeoutException {
      if (mounted) {
        setState(() {
          backendStatus = "Not reached";
        });
      }
      updateLocationUploadStatus("Location upload timeout", refreshTime: true);
    } on SocketException {
      if (mounted) {
        setState(() {
          backendStatus = "Not reached";
        });
      }
      updateLocationUploadStatus("Location network error", refreshTime: true);
    } catch (error) {
      if (mounted) {
        setState(() {
          backendStatus = "Not reached";
        });
      }
      updateLocationUploadStatus(
        "Location upload error: $error",
        refreshTime: true,
      );
    } finally {
      isUploadingLocation = false;
      final queuedDeviceId = pendingLocationUploadDeviceId;
      pendingLocationUploadDeviceId = null;
      if (queuedDeviceId != null && queuedDeviceId.isNotEmpty && mounted) {
        unawaited(uploadCurrentLocation(overrideDeviceId: queuedDeviceId));
      }
    }
  }

  Future<void> pollRemoteCommand() async {
    if (!appConfig.restFallbackEnabled) {
      return;
    }
    if (isNodeWebSocketConnected) {
      return;
    }

    if (isPollingCommand ||
        isHandlingRemoteCommand ||
        !isBackendRuntimeConfigured) {
      return;
    }

    isPollingCommand = true;

    try {
      final uri = Uri.parse(commandPollUrl);
      // ignore: avoid_print
      print('Remote command URL: $uri');

      final response = await http.get(uri).timeout(const Duration(seconds: 10));

      if (response.statusCode != 200) {
        if (mounted) {
          setState(() {
            backendStatus = "Error ${response.statusCode}";
            remoteCommandStatus = "Command poll failed: ${response.statusCode}";
          });
        }
        return;
      }

      final body = jsonDecode(response.body);
      if (body is! Map<String, dynamic> || body["has_command"] != true) {
        if (mounted) {
          setState(() {
            backendStatus = "Connected";
            remoteCommandStatus = "No pending command";
          });
        }
        return;
      }

      final commandIdValue = body["command_id"];
      final commandId = commandIdValue is num ? commandIdValue.toInt() : null;
      final command = body["command"]?.toString() ?? "";
      final commandValue = decodeCommandValue(body["value"]);

      if (commandId == null || command.isEmpty) {
        if (mounted) {
          setState(() {
            remoteCommandStatus = "Invalid command payload";
          });
        }
        return;
      }

      await handleRemoteCommand(
        commandId: commandId,
        command: command,
        value: commandValue,
      );
    } on TimeoutException {
      if (mounted) {
        setState(() {
          if (!hasSuccessfulLocationUpload) {
            backendStatus = "Not reached";
          }
          remoteCommandStatus = "Command poll timeout";
        });
      }
    } on SocketException {
      if (mounted) {
        setState(() {
          if (!hasSuccessfulLocationUpload) {
            backendStatus = "Not reached";
          }
          remoteCommandStatus = "Command network error";
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          if (!hasSuccessfulLocationUpload) {
            backendStatus = "Not reached";
          }
          remoteCommandStatus = "Command poll error: $error";
        });
      }
    } finally {
      isPollingCommand = false;
    }
  }

  Map<String, dynamic>? decodeCommandValue(dynamic value) {
    if (value == null) return null;
    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }
    if (value is String && value.trim().isNotEmpty) {
      try {
        final decoded = jsonDecode(value);
        if (decoded is Map) {
          return Map<String, dynamic>.from(decoded);
        }
      } catch (_) {
        return {"value": value};
      }
    }
    return {"value": value};
  }

  Future<void> handleRemoteCommand({
    required int commandId,
    required String command,
    Map<String, dynamic>? value,
  }) async {
    isHandlingRemoteCommand = true;
    var ackStatus = "done";
    var message = "";

    if (mounted) {
      setState(() {
        remoteCommandStatus = "Executing command #$commandId";
        lastRemoteCommand = command;
      });
    }

    try {
      switch (command) {
        case "start_listening":
          if (isListening) {
            message = "already listening";
          } else {
            await startListening();
            message = "listening started";
          }
          break;
        case "stop_listening":
          if (!isListening) {
            message = "already stopped";
          } else {
            await stopListening();
            message = "listening stopped";
          }
          break;
        case "set_detection_mode":
          await applyRemoteUploadMode(uploadModeDetectionOnly);
          message = "Mode changed to Detection";
          break;
        case "set_collection_mode":
          await applyRemoteUploadMode(uploadModeCollectAll);
          message = "Mode changed to Collection";
          break;
        case "start_live_audio":
          final result = await startLiveAudioFromCommand(value ?? {});
          ackStatus = result.success ? "done" : "failed";
          message = result.message;
          break;
        case "stop_live_audio":
          final result = await stopLiveAudioFromCommand();
          ackStatus = result.success ? "done" : "failed";
          message = result.message;
          break;
        default:
          ackStatus = "failed";
          message = "unsupported command: $command";
      }
    } catch (error) {
      ackStatus = "failed";
      message = error.toString();
    }

    await acknowledgeRemoteCommand(
      commandId: commandId,
      ackStatus: ackStatus,
      message: message,
    );

    if (mounted) {
      setState(() {
        remoteCommandStatus = "Command #$commandId acknowledged";
        lastRemoteCommandResult = "$ackStatus: $message";
      });
    }

    isHandlingRemoteCommand = false;
  }

  Future<void> acknowledgeRemoteCommand({
    required int commandId,
    required String ackStatus,
    required String message,
  }) async {
    try {
      final response = await http
          .post(
            Uri.parse(commandAckUrl),
            headers: {"Content-Type": "application/json"},
            body: jsonEncode({
              "command_id": commandId,
              "device_id": deviceId,
              "status": ackStatus,
              "message": message,
            }),
          )
          .timeout(const Duration(seconds: 10));

      // ignore: avoid_print
      print('command ack status code: ${response.statusCode}');
      // ignore: avoid_print
      print('command ack response body: ${response.body}');

      if (response.statusCode != 200 && mounted) {
        setState(() {
          remoteCommandStatus = "Command ack failed: ${response.statusCode}";
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          remoteCommandStatus = "Command ack error: $error";
        });
      }
    }
  }

  Future<Position?> getCurrentLocation() async {
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) return null;

      LocationPermission permission = await Geolocator.checkPermission();

      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }

      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }

      return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> testBackendConnection() async {
    try {
      if (!isBackendRuntimeConfigured) {
        setState(() {
          backendStatus = "Configuration error";
          status = "Configuration error: $runtimeConfigErrorText";
        });
        return;
      }

      setState(() {
        backendStatus = "Testing...";
        status = "Testing backend...";
      });

      final response = await http
          .get(Uri.parse(backendBaseUrl))
          .timeout(const Duration(seconds: 30));

      if (response.statusCode == 200) {
        setState(() {
          backendStatus = "Connected";
          status = "Backend connected";
        });
      } else {
        setState(() {
          backendStatus = "Error ${response.statusCode}";
          status = "Backend error: ${response.statusCode}";
        });
      }
    } catch (_) {
      setState(() {
        backendStatus = "Not reached";
        status = "Backend not reached";
      });
    }
  }

  Future<String> uploadEventToBackend(AudioEvent event) async {
    try {
      if (!isBackendRuntimeConfigured) {
        return "config_invalid";
      }

      // ignore: avoid_print
      print('event_id: ${event.eventId}');
      // ignore: avoid_print
      print('metadata upload URL: $backendUrl');

      final uploadStartedAtMs = DateTime.now().toUtc().millisecondsSinceEpoch;
      final sameMonotonicSession =
          event.latencyTrace['monotonic_session_id'] ==
          postInferenceMonotonicSessionId;
      if (postInferenceLatencyTracingEnabled) {
        event.latencyTrace['http_request_started_at'] = uploadStartedAtMs;
        if (sameMonotonicSession) {
          event.latencyTrace['http_request_started_at_monotonic'] =
              postInferenceMonotonicClock.elapsedMicroseconds / 1000.0;
        }
      }
      final httpStopwatch = Stopwatch()..start();
      final metadataPayload = <String, dynamic>{
        "event_id": event.eventId,
        "trace_id": event.traceId,
        "latency_trace": event.latencyTrace,
        "device_id": event.deviceId,
        "timestamp": event.time,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "duration_s": double.tryParse(event.duration.replaceAll(" s", "")),
        "rms_peak": event.peakRms,
        "avg_db": event.avgDb,
        "peak_db": event.peakDb,
        "estimated_avg_db": event.estimatedAvgDb,
        "estimated_peak_db": event.estimatedPeakDb,
        "gps_speed_mps": event.gpsSpeedMps,
        "gps_heading_deg": event.gpsHeadingDeg,
        "gps_accuracy_m": event.gpsAccuracyM,
        "label": event.aiLabel,
        if (classificationV1Enabled && event.classification != null)
          "classification": event.classification!.toJson(),
        "audio_file_name": event.path.split('/').last,
        "local_audio_path": event.path,
        "audio_path": event.cloudAudioPath,
        "audio_format": event.audioFormat,
        "audio_size_bytes": event.audioSizeBytes,
        "source_pcm_size_bytes": event.sourcePcmSizeBytes,
        "audio_encoding_status": event.audioEncodingStatus,
        "tdoa_clip_path": event.tdoaClipPath,
        "tdoa_clip_format": event.tdoaClipFormat,
        "tdoa_clip_size_bytes": event.tdoaClipSizeBytes,
        "tdoa_clip_start_sample": event.tdoaClipStartSample,
        "tdoa_clip_end_sample": event.tdoaClipEndSample,
        "tdoa_clip_peak_sample": event.tdoaClipPeakSample,
        "tdoa_clip_duration_ms": event.tdoaClipDurationMs,
        "tdoa_clip_source": event.tdoaClipSource,
        "note": buildEventNote(event),
        "device_event_time_ms": event.deviceEventTimeMs,
        "event_start_time_ms": event.eventStartTimeMs,
        "event_end_time_ms": event.eventEndTimeMs,
        "rms_peak_offset_ms": event.rmsPeakOffsetMs,
        "sample_rate": event.sampleRate,
        "audio_duration_ms": event.audioDurationMs,
        "time_sync_version": event.timeSyncVersion,
        "time_sync_offset_ms": event.timeSyncOffsetMs,
        "time_sync_rtt_ms": event.timeSyncRttMs,
        "time_sync_quality": event.timeSyncQuality,
        "time_sync_synced_at_ms": event.timeSyncSyncedAtMs,
        "time_sync_age_ms": event.timeSyncAgeMs,
        if (event.timingMetadata != null) ...event.timingMetadata!.toJson(),
      };
      final response = persistentMetadataHttpClientEnabled
          ? await metadataUploadClient.postEvent(
              uri: Uri.parse(backendUrl),
              uploadToken: uploadToken,
              payload: metadataPayload,
            )
          : await http
                .post(
                  Uri.parse(backendUrl),
                  headers: <String, String>{
                    'Content-Type': 'application/json',
                    'x-upload-token': uploadToken,
                  },
                  body: jsonEncode(metadataPayload),
                )
                .timeout(const Duration(seconds: 75));
      httpStopwatch.stop();
      final uploadFinishedAtMs = DateTime.now().toUtc().millisecondsSinceEpoch;
      if (postInferenceLatencyTracingEnabled) {
        event.latencyTrace['http_response_received_at'] = uploadFinishedAtMs;
        if (sameMonotonicSession) {
          event.latencyTrace['http_response_received_at_monotonic'] =
              postInferenceMonotonicClock.elapsedMicroseconds / 1000.0;
        }
      }

      // ignore: avoid_print
      print('metadata upload status code: ${response.statusCode}');
      // ignore: avoid_print
      print('metadata upload response body: ${response.body}');
      // ignore: avoid_print
      print(
        '[LATENCY] metadata_upload_ms=${uploadFinishedAtMs - uploadStartedAtMs} '
        'event_id=${event.eventId} status=${response.statusCode}',
      );
      if (postInferenceLatencyTracingEnabled) {
        final serverTiming = parseServerTimingDurations(
          response.headers['server-timing'],
        );
        final serverDbMs = serverTiming['db'];
        final serverIngestMs = serverTiming['ingest'];
        final latencySample = <String, dynamic>{
          'metric': 'post_inference_latency_app',
          'event_id': event.eventId,
          'trace_id': event.traceId,
          'monotonic_session_id': event.latencyTrace['monotonic_session_id'],
          'monotonic_trace_valid': sameMonotonicSession,
          'ai_finished_at_monotonic':
              event.latencyTrace['ai_finished_at_monotonic'],
          'metadata_fast_path_called_at_monotonic':
              event.latencyTrace['metadata_fast_path_called_at_monotonic'],
          'http_request_started_at_monotonic':
              event.latencyTrace['http_request_started_at_monotonic'],
          'http_response_received_at_monotonic':
              event.latencyTrace['http_response_received_at_monotonic'],
          'ai_finish_to_http_start_ms': monotonicDurationMs(
            event.latencyTrace,
            'ai_finished_at_monotonic',
            'http_request_started_at_monotonic',
          ),
          'http_rtt_ms': monotonicDurationMs(
            event.latencyTrace,
            'http_request_started_at_monotonic',
            'http_response_received_at_monotonic',
          ),
          'server_db_ms': serverDbMs,
          'server_ingest_ms': serverIngestMs,
          'server_non_db_ms': serverDbMs != null && serverIngestMs != null
              ? max(0.0, serverIngestMs - serverDbMs)
              : null,
          'http_status': response.statusCode,
        };
        // ignore: avoid_print
        print(
          '[POST_INFERENCE_LATENCY] event_id=${event.eventId} '
          'trace_id=${event.traceId} ai_to_http_ms='
          '${uploadStartedAtMs - (nullableInt(event.latencyTrace['ai_finished_at']) ?? uploadStartedAtMs)} '
          'http_rtt_ms=${httpStopwatch.elapsedMicroseconds / 1000.0} '
          'server_timing="${response.headers['server-timing'] ?? ''}"',
        );
        // One JSON object per real AI result. Collect with adb logcat; no
        // cross-device monotonic subtraction is valid.
        // ignore: avoid_print
        print('[POST_INFERENCE_LATENCY_JSON] ${jsonEncode(latencySample)}');
      }

      if (response.statusCode == 200) {
        return "uploaded";
      } else {
        return "upload_failed_${response.statusCode}";
      }
    } on TimeoutException catch (error) {
      // ignore: avoid_print
      print('metadata upload timeout: $error');
      return "backend_not_reached_timeout";
    } on SocketException catch (error) {
      // ignore: avoid_print
      print('metadata upload network error: $error');
      return "backend_not_reached_network";
    } on FormatException catch (error) {
      // ignore: avoid_print
      print('metadata upload URL format error: $error');
      return "backend_not_reached_bad_url";
    } catch (error) {
      // ignore: avoid_print
      print('metadata upload error: $error');
      return "backend_not_reached_${error.runtimeType}";
    }
  }

  String audioUploadErrorMessage(int statusCode) {
    switch (statusCode) {
      case 400:
        return "400: unsupported audio file";
      case 401:
        return "401: upload token is wrong";
      case 500:
        return "500: backend or GCS error";
      default:
        return "Upload failed: HTTP $statusCode";
    }
  }

  void updateAudioUploadUi(
    String uploadStatus, {
    String? audioPath,
    String? eventId,
  }) {
    if (!mounted) return;
    if (eventId != null &&
        latestCloudEventId != null &&
        eventId != latestCloudEventId) {
      return;
    }

    setState(() {
      lastAudioUploadStatus = uploadStatus;
      if (audioPath != null && audioPath.isNotEmpty) {
        lastCloudAudioPath = audioPath;
      }
      status = uploadStatus;
    });
  }

  String? audioFormatFromPath(String filePath) {
    final lower = filePath.toLowerCase();
    if (lower.endsWith(".mp3")) return "mp3";
    if (lower.endsWith(".wav")) return "wav";
    return null;
  }

  Future<AudioUploadResponseInfo?> uploadPrimaryAudioFile({
    required String eventId,
    required String deviceId,
    required String filePath,
    required String label,
    required String category,
    String? audioFormat,
  }) async {
    try {
      if (!isBackendRuntimeConfigured) {
        updateAudioUploadUi("Config invalid", eventId: eventId);
        return null;
      }
      final audioFile = File(filePath);
      final detectedFormat = audioFormat ?? audioFormatFromPath(filePath);

      if (detectedFormat != "mp3") {
        updateAudioUploadUi("400: audio upload must be MP3", eventId: eventId);
        return null;
      }
      final uploadFormat = detectedFormat!;

      if (!await audioFile.exists()) {
        updateAudioUploadUi("Audio file not found", eventId: eventId);
        return null;
      }

      updateAudioUploadUi(
        "Uploading ${uploadFormat.toUpperCase()}...",
        eventId: eventId,
      );

      final uri = Uri.parse(audioUploadUrl);
      // ignore: avoid_print
      print('Upload audio URL: $uri');
      // ignore: avoid_print
      print(
        'Upload audio label/category/format: $label / $category / $detectedFormat',
      );

      final request = http.MultipartRequest("POST", uri);

      request.headers["x-upload-token"] = uploadToken;
      request.fields["event_id"] = eventId;
      request.fields["device_id"] = deviceId;
      request.fields["label"] = label;
      request.fields["category"] = category;
      request.fields["audio_format"] = uploadFormat;
      request.files.add(
        await http.MultipartFile.fromPath(
          "file",
          filePath,
          filename: audioFile.uri.pathSegments.isNotEmpty
              ? audioFile.uri.pathSegments.last
              : "audio.wav",
        ),
      );

      final uploadStartedAtMs = DateTime.now().millisecondsSinceEpoch;
      final streamedResponse = await request.send().timeout(
        const Duration(seconds: 60),
      );
      final response = await http.Response.fromStream(streamedResponse);
      final uploadFinishedAtMs = DateTime.now().millisecondsSinceEpoch;

      // ignore: avoid_print
      print('audio upload status code: ${response.statusCode}');
      // ignore: avoid_print
      print('audio upload response body: ${response.body}');
      // ignore: avoid_print
      print(
        '[LATENCY] audio_upload_ms=${uploadFinishedAtMs - uploadStartedAtMs} '
        'event_id=$eventId status=${response.statusCode}',
      );

      String? audioPath;
      String? responseFormat;
      int? responseSizeBytes;
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) {
          audioPath = decoded["audio_path"]?.toString();
          responseFormat = decoded["audio_format"]?.toString();
          final sizeValue =
              decoded["size_bytes"] ?? decoded["audio_size_bytes"];
          if (sizeValue is num) {
            responseSizeBytes = sizeValue.toInt();
          } else if (sizeValue != null) {
            responseSizeBytes = int.tryParse(sizeValue.toString());
          }
        }
      } catch (_) {
        audioPath = null;
      }

      if (response.statusCode == 200) {
        // ignore: avoid_print
        print('audio upload audio_path: ${audioPath ?? 'N/A'}');
        updateAudioUploadUi(
          "Audio uploaded: ${response.statusCode}",
          audioPath: audioPath,
          eventId: eventId,
        );
        if (audioPath == null || audioPath.isEmpty) return null;
        return AudioUploadResponseInfo(
          audioPath: audioPath,
          audioFormat: responseFormat ?? uploadFormat,
          sizeBytes: responseSizeBytes,
        );
      }

      updateAudioUploadUi(
        audioUploadErrorMessage(response.statusCode),
        eventId: eventId,
      );
      return null;
    } on TimeoutException {
      updateAudioUploadUi("Network error: upload timeout", eventId: eventId);
      return null;
    } on SocketException {
      updateAudioUploadUi("Network error: cannot connect", eventId: eventId);
      return null;
    } catch (error) {
      updateAudioUploadUi("Network error: $error", eventId: eventId);
      return null;
    }
  }

  Future<String?> uploadAudioFile({
    required String eventId,
    required String deviceId,
    required String filePath,
    required String label,
    required String category,
    String? audioFormat,
  }) async {
    final result = await uploadPrimaryAudioFile(
      eventId: eventId,
      deviceId: deviceId,
      filePath: filePath,
      label: label,
      category: category,
      audioFormat: audioFormat,
    );
    return result?.audioPath;
  }

  Future<AudioUploadResponseInfo?> uploadTdoaClipFile({
    required String eventId,
    required String deviceId,
    required String filePath,
    required String label,
    required String category,
  }) async {
    try {
      if (!isBackendRuntimeConfigured) {
        updateAudioUploadUi("Config invalid", eventId: eventId);
        return null;
      }
      final audioFile = File(filePath);

      if (!filePath.toLowerCase().endsWith(".wav")) {
        updateAudioUploadUi("400: TDOA clip must be WAV", eventId: eventId);
        return null;
      }

      if (!await audioFile.exists()) {
        updateAudioUploadUi("TDOA clip file not found", eventId: eventId);
        return null;
      }

      final uri = Uri.parse(tdoaClipUploadUrl);
      // ignore: avoid_print
      print('Upload TDOA clip URL: $uri');

      final request = http.MultipartRequest("POST", uri);
      request.headers["x-upload-token"] = uploadToken;
      request.fields["event_id"] = eventId;
      request.fields["device_id"] = deviceId;
      request.fields["label"] = label;
      request.fields["category"] = category;
      request.files.add(
        await http.MultipartFile.fromPath(
          "file",
          filePath,
          filename: audioFile.uri.pathSegments.isNotEmpty
              ? audioFile.uri.pathSegments.last
              : "tdoa_clip.wav",
        ),
      );

      final streamedResponse = await request.send().timeout(
        const Duration(seconds: 60),
      );
      final response = await http.Response.fromStream(streamedResponse);

      // ignore: avoid_print
      print('tdoa clip upload status code: ${response.statusCode}');
      // ignore: avoid_print
      print('tdoa clip upload response body: ${response.body}');

      String? clipPath;
      int? clipSizeBytes;
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) {
          clipPath = decoded["tdoa_clip_path"]?.toString();
          final sizeValue =
              decoded["tdoa_clip_size_bytes"] ?? decoded["size_bytes"];
          if (sizeValue is num) {
            clipSizeBytes = sizeValue.toInt();
          } else if (sizeValue != null) {
            clipSizeBytes = int.tryParse(sizeValue.toString());
          }
        }
      } catch (_) {
        clipPath = null;
      }

      if (response.statusCode == 200 &&
          clipPath != null &&
          clipPath.isNotEmpty) {
        return AudioUploadResponseInfo(
          audioPath: clipPath,
          audioFormat: "wav",
          sizeBytes: clipSizeBytes,
        );
      }

      updateAudioUploadUi(
        audioUploadErrorMessage(response.statusCode),
        eventId: eventId,
      );
      return null;
    } on TimeoutException {
      updateAudioUploadUi(
        "Network error: clip upload timeout",
        eventId: eventId,
      );
      return null;
    } on SocketException {
      updateAudioUploadUi("Network error: cannot connect", eventId: eventId);
      return null;
    } catch (error) {
      updateAudioUploadUi("Network error: $error", eventId: eventId);
      return null;
    }
  }

  Future<void> testUploadLatestWav() async {
    AudioEvent? targetEvent;

    for (final event in events) {
      final file = File(event.path);
      if (event.path.toLowerCase().endsWith(".wav") && await file.exists()) {
        targetEvent = event;
        break;
      }
    }

    if (targetEvent == null) {
      updateAudioUploadUi("No local WAV event to upload");
      return;
    }

    updateAudioUploadUi(
      "Preparing MP3 test upload...",
      eventId: targetEvent.eventId,
    );
    await uploadAudioForEventInBackground(targetEvent);
  }

  Future<void> updateEventUploadStatus(
    String eventId,
    String uploadStatus,
  ) async {
    final index = events.indexWhere((event) => event.eventId == eventId);
    if (!mounted) return;
    final updatesSummary =
        latestCloudEventId == null || latestCloudEventId == eventId;

    setState(() {
      if (index != -1) {
        events[index] = events[index].copyWith(uploadStatus: uploadStatus);
      }
      if (!updatesSummary) return;
      lastUploadStatus = uploadStatus;
      if (uploadStatus == "uploaded") {
        status = "Saved + uploaded";
      } else if (uploadStatus == "uploaded_collection_other" ||
          uploadStatus == "uploaded_collection_failed") {
        status = "Collection event uploaded";
      } else if (uploadStatus == "local_only_non_target") {
        status = "Non-target sound, saved locally only";
      } else if (uploadStatus == "local_only_ai_failed") {
        status = "AI failed, saved locally only";
      } else {
        status = "Saved but $uploadStatus";
      }
    });

    if (index != -1) {
      await saveEventsToLocal();
    }
  }

  Future<void> updateEventCloudAudioPath(
    String eventId,
    String cloudAudioPath,
  ) async {
    final index = events.indexWhere((event) => event.eventId == eventId);
    if (index == -1) return;

    final updated = events[index].copyWith(cloudAudioPath: cloudAudioPath);

    setState(() {
      events[index] = updated;
      if (latestCloudEventId == null || latestCloudEventId == eventId) {
        lastCloudAudioPath = cloudAudioPath;
      }
    });

    await saveEventsToLocal();
  }

  Future<void> updateEventAudioMetadata(AudioEvent updatedEvent) async {
    final index = events.indexWhere(
      (event) => event.eventId == updatedEvent.eventId,
    );
    if (index == -1) return;

    setState(() {
      events[index] = updatedEvent;
      if (updatedEvent.cloudAudioPath != null) {
        lastCloudAudioPath = updatedEvent.cloudAudioPath!;
      }
    });

    await saveEventsToLocal();
  }

  Future<void> deleteTransientAudioFile(String path) async {
    if (!path.toLowerCase().endsWith(".wav")) return;
    try {
      final file = File(path);
      if (await file.exists()) {
        await file.delete();
      }
    } catch (_) {
      // Best effort cleanup. A failed delete must not affect listening.
    }
  }

  bool get acceptsSavedAudioWindows => isListening && detectionEnabled;

  Future<void> discardPendingSavedAudioWindow(String reason) async {
    final pending = latestPendingAudioWindow;
    latestPendingAudioWindow = null;
    skippedAudioWindowCount = 0;

    final pendingPath = pending?["path"]?.toString();
    if (pendingPath != null && pendingPath.isNotEmpty) {
      await deleteTransientAudioFile(pendingPath);
    }

    if (!mounted) return;
    setState(() {
      aiInferenceStatus = reason;
    });
  }

  void enqueueSavedAudioEvent(Map<String, dynamic> data) {
    final path = data["path"]?.toString();

    if (!acceptsSavedAudioWindows) {
      if (path != null && path.isNotEmpty) {
        unawaited(deleteTransientAudioFile(path));
      }
      if (mounted) {
        setState(() {
          aiInferenceStatus = "Dropped pending window after stop";
        });
      }
      return;
    }

    if (isProcessingSavedAudioWindow) {
      final oldPendingPath = latestPendingAudioWindow?["path"]?.toString();
      if (oldPendingPath != null && oldPendingPath != path) {
        unawaited(deleteTransientAudioFile(oldPendingPath));
      }
      latestPendingAudioWindow = data;
      skippedAudioWindowCount += 1;
      if (mounted) {
        setState(() {
          aiInferenceStatus =
              "AI queue: keeping latest window ($skippedAudioWindowCount skipped)";
        });
      }
      return;
    }

    unawaited(processSavedAudioWindowQueue(data));
  }

  Future<void> processSavedAudioWindowQueue(Map<String, dynamic> first) async {
    if (isProcessingSavedAudioWindow) {
      latestPendingAudioWindow = first;
      return;
    }

    isProcessingSavedAudioWindow = true;
    var current = first;

    try {
      while (true) {
        if (!acceptsSavedAudioWindows) {
          await deleteTransientAudioFile(current["path"]?.toString() ?? "");
          break;
        }
        await handleSavedAudioEvent(current);
        final next = latestPendingAudioWindow;
        latestPendingAudioWindow = null;
        if (next == null) break;
        current = next;
      }
    } catch (error) {
      // ignore: avoid_print
      print('saved audio queue error: $error');
      if (mounted) {
        setState(() {
          aiInferenceStatus = "AI queue error";
        });
      }
    } finally {
      isProcessingSavedAudioWindow = false;
      final latePending = latestPendingAudioWindow;
      if (latePending != null) {
        latestPendingAudioWindow = null;
        enqueueSavedAudioEvent(latePending);
      }
    }
  }

  Future<void> handleSavedAudioEvent(Map<String, dynamic> data) async {
    final detectionSession = nodeConnectionService.detectionState.session;
    final flutterReceivedAtMs = DateTime.now().millisecondsSinceEpoch
        .toDouble();
    final path = data["path"]?.toString() ?? "unknown path";
    final time = data["time"]?.toString() ?? "unknown time";
    final durationValue = data["duration"];
    final eventDeviceId = deviceId;
    final eventUploadMode = uploadMode;
    final nativePeakRms = nullableDouble(data["rms_peak"]);
    final nativeAvgRms = nullableDouble(data["rms_avg"]);
    final eventPeakRms = nativePeakRms ?? currentEventPeakRms;
    final eventRmsSum = currentEventRmsSum;
    final eventRmsCount = currentEventRmsCount;
    final eventStartSnapshotMs = currentEventStartTimeMs;
    final eventPeakSnapshotMs = currentEventPeakTimeMs;

    double durationSeconds = 0.0;
    if (durationValue is num) {
      durationSeconds = durationValue.toDouble();
    }

    final timingMetadata = EventTimingMetadata.fromJsonOrNull(data);
    final nowAtSaveMs = DateTime.now().millisecondsSinceEpoch.toDouble();
    final eventStartTimeMs =
        timingMetadata?.deviceEventTimeMs.toDouble() ??
        nullableDouble(data["event_start_time_ms"]) ??
        eventStartSnapshotMs ??
        (nowAtSaveMs - (durationSeconds * 1000.0));
    final eventEndTimeMs =
        timingMetadata?.eventEndTimeMs.toDouble() ??
        nullableDouble(data["event_end_time_ms"]) ??
        nowAtSaveMs;
    final rmsPeakOffsetMs =
        timingMetadata?.rmsPeakOffsetMs ??
        nullableDouble(data["rms_peak_offset_ms"]) ??
        (eventPeakSnapshotMs == null
            ? null
            : max(0.0, eventPeakSnapshotMs - eventStartTimeMs));
    final deviceEventTimeMs =
        timingMetadata?.deviceEventTimeMs.toDouble() ??
        nullableDouble(data["device_event_time_ms"]) ??
        (rmsPeakOffsetMs == null
            ? eventStartTimeMs
            : eventStartTimeMs + rmsPeakOffsetMs);
    final sampleRate =
        timingMetadata?.sampleRateHz ??
        nullableInt(data["sample_rate"]) ??
        16000;
    final audioDurationMs =
        timingMetadata?.audioDurationMs.toDouble() ??
        nullableDouble(data["audio_duration_ms"]) ??
        (durationSeconds * 1000.0);
    final eventTimeSyncMetadata = timeSyncMetadata;
    final eventTimeSyncAgeMs = eventTimeSyncMetadata?.ageMsAt(
      DateTime.now().toUtc(),
    );
    final eventTimeSyncQuality = eventTimeSyncMetadata == null
        ? null
        : eventTimeSyncMetadata.isFresh
        ? eventTimeSyncMetadata.quality
        : "stale";

    if (timingMetadata != null) {
      // ignore: avoid_print
      print(
        '[TIMING] source=${timingMetadata.timingSource} '
        'captureStartMs=${timingMetadata.captureStartTimeMs} '
        'eventStartSample=${timingMetadata.eventStartSample} '
        'peakSample=${timingMetadata.rmsPeakSample} '
        'sampleRate=${timingMetadata.sampleRateHz} '
        'deviceEventTimeMs=${timingMetadata.deviceEventTimeMs}',
      );
    }

    final cachedLatitude = currentLatitude;
    final cachedLongitude = currentLongitude;
    final cachedGpsSpeedMps = currentGpsSpeedMps;
    final cachedGpsHeadingDeg = currentGpsHeadingDeg;
    final cachedGpsAccuracyM = currentGpsAccuracyM;
    final hasCachedLocation = cachedLatitude != null && cachedLongitude != null;
    if (!hasCachedLocation) {
      unawaited(uploadCurrentLocation());
    }

    final avgRms =
        nativeAvgRms ??
        (eventRmsCount == 0 ? 0.0 : eventRmsSum / eventRmsCount);
    final peakDbfs = rmsToDbfs(eventPeakRms);
    final avgDbfs = rmsToDbfs(avgRms);
    final estimatedPeakDb = dbfsToEstimatedDb(peakDbfs);
    final estimatedAvgDb = dbfsToEstimatedDb(avgDbfs);

    if (estimatedPeakDb < candidateMinEstimatedPeakDb) {
      await deleteTransientAudioFile(path);
      if (mounted) {
        setState(() {
          status =
              "Below sound threshold (${estimatedPeakDb.toStringAsFixed(1)} dB)";
          aiInferenceStatus = "AI skipped: below sound threshold";
        });
      }
      return;
    }

    if (!acceptsSavedAudioWindows) {
      await deleteTransientAudioFile(path);
      if (mounted) {
        setState(() {
          status = "Stopped, pending sound discarded";
          aiInferenceStatus = "Dropped pending window after stop";
        });
      }
      return;
    }

    if (mounted) {
      setState(() {
        status = "Running AI inference...";
        currentEventPeakRms = 0.0;
        currentEventRmsSum = 0.0;
        currentEventRmsCount = 0;
        currentEventStartTimeMs = null;
        currentEventPeakTimeMs = null;
      });
    }

    final aiStopwatch = Stopwatch()..start();
    final aiStartedAtMs = DateTime.now().millisecondsSinceEpoch.toDouble();
    final aiResult = await runAiInference(path);
    aiStopwatch.stop();
    final aiFinishedAtMs = DateTime.now().millisecondsSinceEpoch.toDouble();
    // Realtime state is independent of admission, persistence and audio upload.
    // A stopped/restarted microphone session must not publish an old result.
    if (aiResult.success && acceptsSavedAudioWindows && mounted) {
      nodeConnectionService.sendDetectionState(
        session: detectionSession,
        active: isTargetSoundLabel(eventLabelForAiResult(aiResult)),
        observedAtMs: aiFinishedAtMs.round(),
        label: aiResult.classification?.canonicalLabel ?? aiResult.label,
        confidence: aiResult.confidence,
      );
    }
    final aiFinishedAtMonotonicMs =
        postInferenceMonotonicClock.elapsedMicroseconds / 1000.0;
    final latencyDiagnostics = buildLatencyDiagnostics(
      nativeData: data,
      flutterReceivedAtMs: flutterReceivedAtMs,
      aiStartedAtMs: aiStartedAtMs,
      aiDurationMs: aiStopwatch.elapsedMicroseconds / 1000.0,
      eventEndTimeMs: eventEndTimeMs,
    );
    final eventLabel = eventLabelForAiResult(aiResult);
    final target = isTargetSoundLabel(eventLabel);
    final classification = aiResult.classification;
    if (classificationV1Enabled && classification != null) {
      final inferenceId =
          'inf_${eventDeviceId}_${postInferenceMonotonicSessionId}_${deviceEventTimeMs.round()}';
      final fieldSample = <String, dynamic>{
        'inference_id': inferenceId,
        'observation_id': null,
        'event_id': null,
        'trace_id': inferenceId,
        'device_id': eventDeviceId,
        'process_session_id': postInferenceMonotonicSessionId,
        'observed_at': DateTime.fromMillisecondsSinceEpoch(
          deviceEventTimeMs.round(),
          isUtc: true,
        ).toIso8601String(),
        'event_time_ms': deviceEventTimeMs.round(),
        'legacy_label': eventLabel,
        'ai_inference_time_ms': aiResult.inferenceTimeMs,
        'classification': classification.toJson(),
      };
      for (final line in encodeClassificationInferenceFieldLogLines(
        fieldSample,
      )) {
        // ignore: avoid_print
        print(line);
      }
    }

    if (!acceptsSavedAudioWindows) {
      await deleteTransientAudioFile(path);
      if (mounted) {
        setState(() {
          status = "Stopped, pending AI result discarded";
          aiInferenceStatus = "AI result discarded after stop";
        });
      }
      return;
    }

    if (target) {
      observationShadowMetrics.rawAiObservationCount += 1;
      logObservationShadowMetrics('valid_target');
      if (observationShadowEnabled) {
        final identity = observationSequence.next(eventDeviceId);
        final observedAt = DateTime.fromMillisecondsSinceEpoch(
          deviceEventTimeMs.round(),
          isUtc: true,
        ).toIso8601String();
        final observation = ObservationShadowPayload(
          identity: identity,
          deviceId: eventDeviceId,
          observedAt: observedAt,
          eventTimeMs: deviceEventTimeMs.round(),
          label: eventLabel,
          confidence: aiResult.confidence,
          aircraftProbability: aiResult.aircraftProbability,
          rmsPeak: eventPeakRms,
          avgRms: avgRms,
          estimatedPeakDb: estimatedPeakDb,
          estimatedAvgDb: estimatedAvgDb,
          nodePositionSource: hasCachedLocation
              ? 'cached_device_gps'
              : 'unavailable',
          latitude: cachedLatitude,
          longitude: cachedLongitude,
          gpsAccuracyM: cachedGpsAccuracyM,
          timeSync: ObservationTimeSyncSnapshot(
            version: eventTimeSyncMetadata == null
                ? null
                : TimeSyncMetadata.version,
            quality: eventTimeSyncQuality,
            offsetMs: eventTimeSyncMetadata?.offsetMs,
            rttMs: eventTimeSyncMetadata?.rttMs,
            ageMs: eventTimeSyncAgeMs,
            deviceWallClockMs: DateTime.now().millisecondsSinceEpoch,
            deviceMonotonicMs:
                postInferenceMonotonicClock.elapsedMicroseconds / 1000.0,
            monotonicSessionId: postInferenceMonotonicSessionId,
          ),
          modelId: aiClassifier.activeModelId,
          modelName: aiClassifier.activeModelName,
          aiInferenceTimeMs: aiResult.inferenceTimeMs,
          windowDurationMs: audioDurationMs.round(),
          hopDurationMs: nullableDouble(data['window_hop_ms'])?.round() ?? 1500,
          sampleRateHz: sampleRate,
          classification: classificationV1Enabled
              ? aiResult.classification
              : null,
        );
        observationShadowMetrics.observationCreatedCount += 1;
        unawaited(enqueueTargetObservationShadow(observation));
      }
    }

    if (eventUploadMode == uploadModeDetectionOnly && !target) {
      final ignoredStatus = aiResult.success
          ? "Non-target ignored"
          : "AI failed, ignored";

      if (mounted) {
        setState(() {
          status = ignoredStatus;
          lastUploadStatus = ignoredStatus;
          lastAudioUploadStatus = ignoredStatus;
        });
      }

      await deleteTransientAudioFile(path);
      return;
    }

    final occurrenceTimeMs = deviceEventTimeMs.round();
    final admission = eventAdmissionController.evaluate(
      deviceId: eventDeviceId,
      target: target,
      occurredAtMs: occurrenceTimeMs,
    );
    if (!admission.accepted) {
      if (target) {
        observationShadowMetrics.cooldownRejectedCount += 1;
        logObservationShadowMetrics('cooldown_rejected');
      }
      await deleteTransientAudioFile(path);
      if (mounted) {
        final remainingSeconds = max(1, (admission.remainingMs / 1000).ceil());
        setState(() {
          status = target
              ? "Target merged into active event"
              : "Collection window coalesced";
          aiInferenceStatus = target
              ? "Overlapping target suppressed (${remainingSeconds}s cooldown)"
              : "Overlapping collection window suppressed";
        });
      }
      return;
    }

    if (target) {
      observationShadowMetrics.alertAdmittedCount += 1;
      logObservationShadowMetrics('alert_admitted');
      unawaited(vibrateForTargetDetected());
    }

    final eventId =
        "event_${DateTime.now().millisecondsSinceEpoch}_$eventDeviceId";
    final latencyTrace = <String, dynamic>{
      'trace_id': eventId,
      'device_event_time_ms': deviceEventTimeMs.round(),
      if (nullableDouble(data['native_window_ready_time_ms']) != null)
        'native_window_ready_time_ms': nullableDouble(
          data['native_window_ready_time_ms'],
        )!.round(),
      'flutter_received_at': flutterReceivedAtMs.round(),
      'ai_started_at': aiStartedAtMs.round(),
      'ai_finished_at': aiFinishedAtMs.round(),
      'monotonic_session_id': postInferenceMonotonicSessionId,
      'ai_finished_at_monotonic': aiFinishedAtMonotonicMs,
    };

    final event = AudioEvent(
      eventId: eventId,
      deviceId: eventDeviceId,
      time: time,
      duration: "${durationSeconds.toStringAsFixed(1)} s",
      path: path,
      avgRms: avgRms,
      peakRms: eventPeakRms,
      avgDb: avgDbfs,
      peakDb: peakDbfs,
      estimatedAvgDb: estimatedAvgDb,
      estimatedPeakDb: estimatedPeakDb,
      latitude: cachedLatitude,
      longitude: cachedLongitude,
      gpsSpeedMps: cachedGpsSpeedMps,
      gpsHeadingDeg: cachedGpsHeadingDeg,
      gpsAccuracyM: cachedGpsAccuracyM,
      locationStatus: hasCachedLocation ? "cached_location" : "no_location",
      uploadStatus: "pending",
      aiLabel: eventLabel,
      aircraftProbability: aiResult.aircraftProbability,
      aiConfidence: aiResult.confidence,
      aiInferenceStatus: aiResult.status,
      aiInferenceTimeMs: aiResult.inferenceTimeMs,
      classification: aiResult.classification,
      uploadMode: eventUploadMode,
      deviceEventTimeMs: deviceEventTimeMs,
      eventStartTimeMs: eventStartTimeMs,
      eventEndTimeMs: eventEndTimeMs,
      rmsPeakOffsetMs: rmsPeakOffsetMs,
      sampleRate: sampleRate,
      audioDurationMs: audioDurationMs,
      timeSyncVersion: eventTimeSyncMetadata == null
          ? null
          : TimeSyncMetadata.version,
      timeSyncOffsetMs: eventTimeSyncMetadata?.offsetMs,
      timeSyncRttMs: eventTimeSyncMetadata?.rttMs,
      timeSyncQuality: eventTimeSyncQuality,
      timeSyncSyncedAtMs: eventTimeSyncMetadata?.syncedAtMs,
      timeSyncAgeMs: eventTimeSyncAgeMs,
      timingMetadata: timingMetadata,
      latencyDiagnostics: latencyDiagnostics,
      latencyTrace: latencyTrace,
    );

    if (mounted) {
      setState(() {
        status = target ? "Target detected" : "Collection event saved";
        latestCloudEventId = eventId;
        events.insert(0, event);

        if (events.length > 100) {
          events = events.take(100).toList();
        }
      });
    }

    unawaited(saveEventsToLocal());
    unawaited(startEventCloudPipeline(event: event));
  }

  @override
  void initState() {
    super.initState();

    WidgetsBinding.instance.addObserver(this);
    nodeConnectionService = NodeConnectionService(
      statusProvider: buildNodeControlStatusPayload,
      onCommand: handleNodeControlCommand,
      onStateChanged: (snapshot) {
        if (!mounted) return;
        setState(() {
          nodeWebSocketStatus = snapshot.status.name;
          nodeWebSocketConnectionId = snapshot.connectionId ?? "N/A";
          nodeWebSocketReconnectCount = snapshot.reconnectCount;
          if (snapshot.lastError != null) {
            remoteCommandStatus = "Node WS: ${snapshot.lastError}";
          }
        });
        if (snapshot.status == NodeConnectionStatus.connected) {
          stopCommandPollingTimer();
          if (observationShadowEnabled) {
            observationRetryDispatcher.wake(forceNetworkProbe: true);
          }
        } else if (snapshot.status != NodeConnectionStatus.stopped) {
          startCommandPollingTimer();
        }
      },
    );
    unawaited(initializeDedicatedNode());
    loadEventsFromLocal();
    unawaited(refreshEventUploadQueueDepth());

    audioPlayerCompleteSubscription = audioPlayer.onPlayerComplete.listen((_) {
      if (!mounted) return;

      setState(() {
        playingPath = null;
        status = isListening ? "Listening..." : "Idle";
      });
    });

    platform.setMethodCallHandler((call) async {
      if (!mounted) return;

      switch (call.method) {
        case "rms_update":
          final value = call.arguments;
          if (value is num) {
            final rms = value.toDouble();

            currentRms = rms;
            currentSoundLevelNotifier.value = SoundLevelReading(
              rms: rms,
              estimatedDb: dbfsToEstimatedDb(rmsToDbfs(rms)),
            );

            if (status == "Recording..." ||
                status == "Sound detected / Recording...") {
              if (rms > currentEventPeakRms) {
                currentEventPeakRms = rms;
                currentEventPeakTimeMs = DateTime.now().millisecondsSinceEpoch
                    .toDouble();
              }

              currentEventRmsSum += rms;
              currentEventRmsCount += 1;
            }
          }
          break;

        case "live_audio_frame":
          final value = call.arguments;
          if (value is Map) {
            liveAudioStreamService.sendPcmFrame(
              Map<String, dynamic>.from(value),
            );
          }
          break;

        case "event_started":
          final startedData = call.arguments is Map
              ? Map<String, dynamic>.from(call.arguments as Map)
              : <String, dynamic>{};
          final nativeStartMs = nullableDouble(
            startedData["event_start_time_ms"],
          );
          setState(() {
            status = "Recording...";
            currentEventPeakRms = 0.0;
            currentEventRmsSum = 0.0;
            currentEventRmsCount = 0;
            currentEventStartTimeMs =
                nativeStartMs ??
                DateTime.now().millisecondsSinceEpoch.toDouble();
            currentEventPeakTimeMs = null;
          });
          break;

        case "silent":
          if (isListening) {
            setState(() {
              status = "Silent";
            });
          }
          break;

        case "event_saved":
          final data = Map<String, dynamic>.from(call.arguments as Map);
          enqueueSavedAudioEvent(data);
          break;

        case "permission_denied":
          nodeConnectionService.stopDetection();
          currentSoundLevelNotifier.value = const SoundLevelReading(rms: 0);
          setState(() {
            status = "Microphone permission denied";
            isListening = false;
            listeningElapsed.stop();
          });
          stopListeningTimer();
          break;

        case "audio_error":
          nodeConnectionService.stopDetection();
          currentSoundLevelNotifier.value = const SoundLevelReading(rms: 0);
          setState(() {
            status = "Audio error";
            isListening = false;
            listeningElapsed.stop();
          });
          stopListeningTimer();
          break;
      }
    });
  }

  Future<void> startListening() async {
    try {
      await audioPlayer.stop();
      playingPath = null;

      await platform.invokeMethod("startListening");

      currentSoundLevelNotifier.value = const SoundLevelReading(rms: 0);
      nodeConnectionService.detectionState.startSession();
      listeningElapsed.start();

      setState(() {
        isListening = true;
        detectionEnabled = true;
        status = "Listening...";
        currentRms = 0.0;
        currentEventPeakRms = 0.0;
        currentEventRmsSum = 0.0;
        currentEventRmsCount = 0;
        currentEventStartTimeMs = null;
        currentEventPeakTimeMs = null;
      });

      startListeningTimer();
    } catch (_) {
      nodeConnectionService.stopDetection();
      stopListeningTimer();
      currentSoundLevelNotifier.value = const SoundLevelReading(rms: 0);
      setState(() {
        status = "Start failed";
        isListening = false;
        listeningElapsed.stop();
      });
    }
  }

  Future<void> stopListening() async {
    nodeConnectionService.stopDetection();
    try {
      await platform.invokeMethod("stopListening");
    } catch (_) {}

    stopListeningTimer();
    await discardPendingSavedAudioWindow("Stopped, pending sound discarded");
    currentSoundLevelNotifier.value = const SoundLevelReading(rms: 0);

    setState(() {
      isListening = false;
      detectionEnabled = false;
      status = "Stopped";
      listeningElapsed.stop();
      currentEventStartTimeMs = null;
      currentEventPeakTimeMs = null;
    });
  }

  Future<void> playEvent(AudioEvent event) async {
    try {
      final file = File(event.path);

      if (!await file.exists()) {
        setState(() {
          status = "File not found";
        });
        return;
      }

      if (playingPath == event.path) {
        await audioPlayer.stop();

        setState(() {
          playingPath = null;
          status = isListening ? "Listening..." : "Stopped";
        });

        return;
      }

      await audioPlayer.stop();
      await audioPlayer.play(DeviceFileSource(event.path));

      setState(() {
        playingPath = event.path;
        status = "Playing audio...";
      });
    } catch (_) {
      setState(() {
        status = "Play failed";
      });
    }
  }

  Future<void> deleteEvent(AudioEvent event) async {
    try {
      if (playingPath == event.path) {
        await audioPlayer.stop();
        playingPath = null;
      }

      final file = File(event.path);

      if (await file.exists()) {
        await file.delete();
      }

      setState(() {
        events.remove(event);
        status = "Deleted event";
      });

      await saveEventsToLocal();
    } catch (_) {
      setState(() {
        status = "Delete failed";
      });
    }
  }

  Future<void> confirmDelete(AudioEvent event) async {
    final shouldDelete = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text("刪除音檔？"),
          content: const Text("確定要刪除這段錄音嗎？刪除後無法復原。"),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text("取消"),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text("刪除"),
            ),
          ],
        );
      },
    );

    if (shouldDelete == true) {
      await deleteEvent(event);
    }
  }

  Future<void> clearLocalRecords() async {
    final shouldClear = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text("清除本機紀錄？"),
          content: const Text("這只會清除手機 APP 內的本機紀錄，不會刪除後端資料庫。"),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text("取消"),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text("清除"),
            ),
          ],
        );
      },
    );

    if (shouldClear == true) {
      setState(() {
        events.clear();
        status = "Local records cleared";
      });
      await saveEventsToLocal();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(applyImmersiveMode());
      if (observationShadowEnabled) {
        observationRetryDispatcher.wake(forceNetworkProbe: true);
      }
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    nodeConnectionService.stopDetection();
    platform.setMethodCallHandler(null);
    stopListeningTimer();
    stopLocationUploadTimer();
    stopCommandPollingTimer();
    stopTimeSyncTimer();
    stopEventUploadRetryTimer();
    unawaited(liveAudioStreamService.stop());
    unawaited(nodeConnectionService.stop());
    aiClassifier.close();
    metadataUploadClient.close();
    if (observationShadowEnabled) {
      unawaited(observationRetryDispatcher.close());
    }
    observationShadowClient.close();
    currentSoundLevelNotifier.dispose();
    unawaited(audioPlayerCompleteSubscription.cancel());
    audioPlayer.dispose();
    deviceIdController.dispose();
    backendUrlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final eventViews = events.map(eventViewDataFor).toList(growable: false);
    final pendingCount = pendingUploadCount;
    return Scaffold(
      appBar: AppBar(
        title: Text(switch (selectedDestinationIndex) {
          0 => '監控',
          1 => '事件',
          _ => '系統',
        }),
      ),
      body: SafeArea(
        bottom: false,
        child: IndexedStack(
          index: selectedDestinationIndex,
          children: [
            MonitorView(
              deviceId: deviceId,
              statusLabel: mainStatusLabel,
              statusIcon: operationalStatusIcon,
              statusLevel: operationalStatusLevel,
              healthItems: monitorHealthItems(pendingCount),
              isListening: isListening,
              listeningTime: formatListeningTime(listeningElapsed.seconds),
              soundLevel: currentSoundLevelNotifier,
              classificationLabel: lastAiLabel,
              classificationConfidence: double.tryParse(lastAiConfidence),
              aircraftProbability: double.tryParse(lastAircraftProbability),
              latestEvent: eventViews.isEmpty ? null : eventViews.first,
              onOpenSystem: () => selectDestination(2),
              onOpenEvents: () => selectDestination(1),
              onToggleListening: isListening ? stopListening : startListening,
            ),
            EventsView(
              events: eventViews,
              filter: selectedEventFilter,
              playingEventId: playingEventId,
              onFilterChanged: (filter) {
                setState(() {
                  selectedEventFilter = filter;
                });
              },
              onOpen: showEventDetails,
              onPlay: playEventView,
            ),
            SystemView(
              deviceIdController: deviceIdController,
              savedDeviceId: savedDeviceId,
              isListening: isListening,
              dedicatedNodeMode: dedicatedNodeModeEnabled,
              onSaveDeviceId: saveDeviceIdToLocal,
              selectedModelId: selectedAiModelId,
              modelOptions: AiSoundClassifier.supportedModels
                  .map(
                    (option) =>
                        SystemModelOption(id: option.id, name: option.name),
                  )
                  .toList(growable: false),
              onModelChanged: saveAiModelToLocal,
              modelStatus: displayStatusText(aiModelStatus),
              sampleRateHz: AiSoundClassifier.targetSampleRate,
              windowMs: 3000,
              hopMs: 1500,
              uploadMode: uploadMode,
              onUploadModeChanged: saveUploadModeToLocal,
              connectivity: systemConnectivity(pendingCount),
              automation: systemAutomation,
              diagnostics: systemDiagnostics,
              themeMode: widget.themeMode,
              onThemeModeChanged: widget.onThemeModeChanged,
              onUploadLatestWav: testUploadLatestWav,
              onClearLocalRecords: clearLocalRecords,
            ),
          ],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedDestinationIndex,
        onDestinationSelected: selectDestination,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.monitor_heart_outlined),
            selectedIcon: Icon(Icons.monitor_heart),
            label: '監控',
          ),
          NavigationDestination(
            icon: Icon(Icons.notifications_none),
            selectedIcon: Icon(Icons.notifications),
            label: '事件',
          ),
          NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings),
            label: '系統',
          ),
        ],
      ),
    );
  }

  void selectDestination(int index) {
    setState(() {
      selectedDestinationIndex = index;
    });
  }

  int get pendingUploadCount {
    return latestEventUploadQueueDepth +
        (latestObservationQueueSnapshot?.depth ?? 0);
  }

  Future<void> refreshEventUploadQueueDepth() async {
    try {
      final depth = (await eventUploadQueue.load()).length;
      if (!mounted || depth == latestEventUploadQueueDepth) return;
      setState(() {
        latestEventUploadQueueDepth = depth;
      });
    } catch (_) {
      // Presentation-only observer: queue failures remain owned by the pipeline.
    }
  }

  String? get playingEventId {
    final path = playingPath;
    if (path == null) return null;
    for (final event in events) {
      if (event.path == path) return event.eventId;
    }
    return null;
  }

  OperationalStatusLevel get operationalStatusLevel {
    final normalized = status.toLowerCase();
    if (mainStatusLabel == '目標') {
      return OperationalStatusLevel.target;
    }
    if (normalized.contains('error') ||
        normalized.contains('failed') ||
        normalized.contains('denied') ||
        normalized.contains('configuration')) {
      return OperationalStatusLevel.error;
    }
    if (isListening) return OperationalStatusLevel.healthy;
    return OperationalStatusLevel.neutral;
  }

  IconData get operationalStatusIcon {
    return switch (operationalStatusLevel) {
      OperationalStatusLevel.target => Icons.notification_important,
      OperationalStatusLevel.error => Icons.error_outline,
      OperationalStatusLevel.healthy => Icons.hearing,
      OperationalStatusLevel.warning => Icons.warning_amber,
      OperationalStatusLevel.neutral => Icons.pause_circle_outline,
    };
  }

  bool get backendConnected {
    return isNodeWebSocketConnected ||
        backendStatus == 'Connected' ||
        hasSuccessfulLocationUpload;
  }

  OperationalStatusLevel get backendHealthLevel {
    if (backendConnected) return OperationalStatusLevel.healthy;
    if (backendStatus == 'Not tested' || backendStatus == 'Testing...') {
      return OperationalStatusLevel.warning;
    }
    return OperationalStatusLevel.error;
  }

  OperationalStatusLevel get gpsHealthLevel {
    if (gpsOnline) return OperationalStatusLevel.healthy;
    if (isUploadingLocation ||
        lastLocationUploadStatus == 'No location upload yet') {
      return OperationalStatusLevel.warning;
    }
    return OperationalStatusLevel.error;
  }

  OperationalStatusLevel get aiHealthLevel {
    if (aiModelStatus.contains('loaded')) {
      return OperationalStatusLevel.healthy;
    }
    if (aiModelStatus.contains('failed')) {
      return OperationalStatusLevel.error;
    }
    return OperationalStatusLevel.warning;
  }

  List<HealthStatusItem> monitorHealthItems(int queueDepth) {
    return [
      HealthStatusItem(
        label: '後端',
        detail: backendConnected ? '已連線' : displayStatusText(backendStatus),
        icon: backendConnected ? Icons.cloud_done : Icons.cloud_off,
        level: backendHealthLevel,
      ),
      HealthStatusItem(
        label: 'GPS',
        detail: gpsOnline
            ? currentGpsAccuracyM == null
                  ? '定位完成'
                  : '±${currentGpsAccuracyM!.toStringAsFixed(1)} m'
            : gpsBadgeText,
        icon: gpsOnline ? Icons.location_on : Icons.location_off,
        level: gpsHealthLevel,
      ),
      HealthStatusItem(
        label: 'AI',
        detail: aiBadgeText,
        icon: aiHealthLevel == OperationalStatusLevel.error
            ? Icons.memory_outlined
            : Icons.memory,
        level: aiHealthLevel,
      ),
      HealthStatusItem(
        label: '待傳',
        detail: '$queueDepth 筆待傳',
        icon: queueDepth == 0 ? Icons.sync_disabled : Icons.sync,
        level: queueDepth == 0
            ? OperationalStatusLevel.healthy
            : OperationalStatusLevel.warning,
      ),
    ];
  }

  EventViewData eventViewDataFor(AudioEvent event) {
    return EventViewData(
      eventId: event.eventId,
      rawLabel: event.aiLabel,
      isTarget: isTargetSoundLabel(event.aiLabel),
      time: event.time,
      deviceId: event.deviceId,
      confidence: event.aiConfidence,
      aircraftProbability: event.aircraftProbability,
      estimatedPeakDb: event.estimatedPeakDb,
      estimatedAvgDb: event.estimatedAvgDb,
      avgRms: event.avgRms,
      peakRms: event.peakRms,
      latitude: event.latitude,
      longitude: event.longitude,
      gpsAccuracyM: event.gpsAccuracyM,
      locationStatus: event.locationStatus,
      metadataUploadStatus: event.uploadStatus,
      localAudioPath: event.path,
      audioAvailable:
          event.path.trim().isNotEmpty && event.path != 'unknown path',
      cloudAudioPath: event.cloudAudioPath,
      audioFormat: event.audioFormat,
      audioEncodingStatus: event.audioEncodingStatus,
      aiInferenceStatus: event.aiInferenceStatus,
      aiInferenceTimeMs: event.aiInferenceTimeMs,
    );
  }

  AudioEvent? audioEventForView(EventViewData view) {
    for (final event in events) {
      if (event.eventId == view.eventId) return event;
    }
    return null;
  }

  void playEventView(EventViewData view) {
    final event = audioEventForView(view);
    if (event != null) unawaited(playEvent(event));
  }

  void confirmDeleteEventView(EventViewData view) {
    final event = audioEventForView(view);
    if (event != null) unawaited(confirmDelete(event));
  }

  Future<void> showEventDetails(EventViewData view) async {
    final event = audioEventForView(view);
    if (event == null) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: false,
      builder: (sheetContext) {
        return EventDetailSheet(
          event: view,
          isPlaying: playingPath == event.path,
          onPlay: () {
            Navigator.pop(sheetContext);
            unawaited(playEvent(event));
          },
          onDelete: () {
            Navigator.pop(sheetContext);
            unawaited(confirmDelete(event));
          },
        );
      },
    );
  }

  List<SystemStatusData> systemConnectivity(int queueDepth) {
    final timeSynced = isTimeSyncFresh;
    return [
      SystemStatusData(
        label: '後端',
        value: backendConnected ? '已連線' : displayStatusText(backendStatus),
        icon: backendConnected ? Icons.check_circle : Icons.cloud_off,
        level: backendHealthLevel,
      ),
      SystemStatusData(
        label: '節點 WebSocket',
        value: isNodeWebSocketConnected
            ? '已連線'
            : displayStatusText(nodeWebSocketStatus),
        icon: isNodeWebSocketConnected ? Icons.check_circle : Icons.link_off,
        level: isNodeWebSocketConnected
            ? OperationalStatusLevel.healthy
            : OperationalStatusLevel.warning,
      ),
      SystemStatusData(
        label: 'GPS',
        value: gpsOnline
            ? currentGpsAccuracyM == null
                  ? '可用'
                  : '±${currentGpsAccuracyM!.toStringAsFixed(1)} m'
            : gpsBadgeText,
        icon: gpsOnline ? Icons.location_on : Icons.location_off,
        level: gpsHealthLevel,
      ),
      SystemStatusData(
        label: '待傳佇列',
        value: '$queueDepth 筆待傳',
        icon: queueDepth == 0 ? Icons.check_circle : Icons.sync,
        level: queueDepth == 0
            ? OperationalStatusLevel.healthy
            : OperationalStatusLevel.warning,
      ),
      SystemStatusData(
        label: '時間同步',
        value: timeSynced
            ? displayTimeSyncQuality(effectiveTimeSyncQuality)
            : '尚未同步',
        icon: timeSynced ? Icons.schedule : Icons.schedule_outlined,
        level: timeSynced
            ? OperationalStatusLevel.healthy
            : OperationalStatusLevel.warning,
      ),
    ];
  }

  List<SystemInfoData> get systemAutomation => [
    SystemInfoData(label: '自動啟動', value: autoStartStatus),
    SystemInfoData(label: '保持螢幕開啟', value: keepScreenOnStatus),
    SystemInfoData(label: '資訊站模式', value: kioskStatus),
    SystemInfoData(label: '沉浸模式', value: immersiveModeStatus),
    SystemInfoData(
      label: '專用節點',
      value: dedicatedNodeModeEnabled ? '啟用' : '未啟用',
    ),
  ];

  List<SystemInfoData> get systemDiagnostics => [
    SystemInfoData(label: 'GPS 原始位置', value: currentLocationText),
    SystemInfoData(
      label: 'GPS 速度',
      value: currentGpsSpeedMps == null
          ? '無'
          : '${currentGpsSpeedMps!.toStringAsFixed(2)} m/s',
    ),
    SystemInfoData(
      label: 'GPS 方位',
      value: currentGpsHeadingDeg == null
          ? '無'
          : '${currentGpsHeadingDeg!.toStringAsFixed(1)}°',
    ),
    SystemInfoData(
      label: '最近位置上傳',
      value: displayStatusText(lastLocationUploadStatus),
    ),
    SystemInfoData(
      label: '最近位置上傳時間',
      value: displayStatusText(lastLocationUploadTime),
    ),
    SystemInfoData(
      label: '最近事件資料上傳',
      value: displayStatusText(lastUploadStatus),
    ),
    SystemInfoData(
      label: '最近音檔上傳',
      value: displayStatusText(lastAudioUploadStatus),
    ),
    SystemInfoData(
      label: '雲端音檔路徑',
      value: displayStatusText(lastCloudAudioPath),
    ),
    SystemInfoData(
      label: '時間偏移',
      value: timeSyncOffsetMs == null
          ? '無'
          : '${timeSyncOffsetMs!.toStringAsFixed(1)} ms',
    ),
    SystemInfoData(
      label: '時間同步 RTT',
      value: timeSyncRttMs == null
          ? '無'
          : '${timeSyncRttMs!.toStringAsFixed(1)} ms',
    ),
    SystemInfoData(label: '時間同步狀態', value: lastTimeSyncStatus),
    SystemInfoData(
      label: 'AI 推論狀態',
      value: displayStatusText(aiInferenceStatus),
    ),
    SystemInfoData(
      label: 'AI 輸入形狀',
      value: aiClassifier.inputShape.isEmpty
          ? '無'
          : aiClassifier.inputShape.join(' × '),
    ),
    SystemInfoData(
      label: 'AI 輸出形狀',
      value: aiClassifier.outputShape.isEmpty
          ? '無'
          : aiClassifier.outputShape.join(' × '),
    ),
    SystemInfoData(label: 'AI 信心值', value: displayStatusText(lastAiConfidence)),
    SystemInfoData(
      label: 'AI 推論耗時',
      value: displayStatusText(lastAiInferenceTime),
    ),
    SystemInfoData(
      label: 'Observation 待傳佇列',
      value: latestObservationQueueSnapshot == null
          ? (observationShadowEnabled ? '等待狀態資料' : '功能未啟用')
          : '${latestObservationQueueSnapshot!.depth} 筆待傳 / '
                '${latestObservationQueueSnapshot!.bytes} 位元組',
    ),
    SystemInfoData(label: '事件待傳佇列', value: '$latestEventUploadQueueDepth 筆待傳'),
    SystemInfoData(
      label: '遠端指令狀態',
      value: displayStatusText(remoteCommandStatus),
    ),
    SystemInfoData(label: '最近遠端指令', value: displayCommand(lastRemoteCommand)),
    SystemInfoData(
      label: '遠端指令結果',
      value: displayStatusText(lastRemoteCommandResult),
    ),
    SystemInfoData(
      label: '節點 WS 連線 ID',
      value: displayStatusText(nodeWebSocketConnectionId),
    ),
    SystemInfoData(
      label: '節點 WS 重連次數',
      value: nodeWebSocketReconnectCount.toString(),
    ),
    SystemInfoData(label: '即時音訊', value: displayStatusText(liveAudioStatus)),
    SystemInfoData(label: '目前 RMS', value: currentRms.toStringAsFixed(2)),
    SystemInfoData(
      label: '事件平均 RMS',
      value: currentEventAvgRms.toStringAsFixed(2),
    ),
    SystemInfoData(
      label: '事件峰值 RMS',
      value: currentEventPeakRms.toStringAsFixed(2),
    ),
    SystemInfoData(label: '預錄緩衝', value: '2 s'),
    SystemInfoData(label: '靜音結束門檻', value: '700 ms'),
    SystemInfoData(label: '最長事件', value: '4 s'),
    SystemInfoData(
      label: 'AI 視窗緩衝',
      value: isProcessingSavedAudioWindow ? '處理中' : '待命',
    ),
    SystemInfoData(label: '略過視窗數', value: skippedAudioWindowCount.toString()),
    SystemInfoData(label: '事件狀態', value: displayStatusText(status)),
    SystemInfoData(label: '本機事件數', value: events.length.toString()),
  ];
}
