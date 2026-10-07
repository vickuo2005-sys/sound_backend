class EventViewData {
  const EventViewData({
    required this.eventId,
    required this.rawLabel,
    required this.isTarget,
    required this.time,
    required this.deviceId,
    required this.metadataUploadStatus,
    required this.localAudioPath,
    required this.audioAvailable,
    this.confidence,
    this.aircraftProbability,
    this.estimatedPeakDb,
    this.estimatedAvgDb,
    this.avgRms,
    this.peakRms,
    this.latitude,
    this.longitude,
    this.gpsAccuracyM,
    this.locationStatus,
    this.cloudAudioPath,
    this.audioFormat,
    this.audioEncodingStatus,
    this.aiInferenceStatus,
    this.aiInferenceTimeMs,
  });

  final String eventId;
  final String rawLabel;
  final bool isTarget;
  final String time;
  final String deviceId;
  final double? confidence;
  final double? aircraftProbability;
  final double? estimatedPeakDb;
  final double? estimatedAvgDb;
  final double? avgRms;
  final double? peakRms;
  final double? latitude;
  final double? longitude;
  final double? gpsAccuracyM;
  final String? locationStatus;
  final String metadataUploadStatus;
  final String localAudioPath;
  final bool audioAvailable;
  final String? cloudAudioPath;
  final String? audioFormat;
  final String? audioEncodingStatus;
  final String? aiInferenceStatus;
  final int? aiInferenceTimeMs;
}
