class EventTimingMetadata {
  static const int currentVersion = 1;
  static const String pcmSampleIndexSource = 'PCM_SAMPLE_INDEX';

  final int timingVersion;
  final String timingSource;
  final int captureStartTimeMs;
  final int eventStartSample;
  final int eventEndSample;
  final int rmsPeakSample;
  final int sampleRateHz;
  final int channelCount;
  final int audioDurationMs;
  final int deviceEventTimeMs;
  final int eventEndTimeMs;
  final int rmsPeakTimeMs;

  const EventTimingMetadata({
    required this.timingVersion,
    required this.timingSource,
    required this.captureStartTimeMs,
    required this.eventStartSample,
    required this.eventEndSample,
    required this.rmsPeakSample,
    required this.sampleRateHz,
    required this.channelCount,
    required this.audioDurationMs,
    required this.deviceEventTimeMs,
    required this.eventEndTimeMs,
    required this.rmsPeakTimeMs,
  });

  factory EventTimingMetadata.fromSampleIndexes({
    required int captureStartTimeMs,
    required int eventStartSample,
    required int eventEndSample,
    required int rmsPeakSample,
    required int sampleRateHz,
    required int channelCount,
    int? audioDurationMs,
    int timingVersion = currentVersion,
    String timingSource = pcmSampleIndexSource,
  }) {
    final durationMs =
        audioDurationMs ?? sampleOffsetMs(eventEndSample, sampleRateHz);
    return EventTimingMetadata(
      timingVersion: timingVersion,
      timingSource: timingSource,
      captureStartTimeMs: captureStartTimeMs,
      eventStartSample: eventStartSample,
      eventEndSample: eventEndSample,
      rmsPeakSample: rmsPeakSample,
      sampleRateHz: sampleRateHz,
      channelCount: channelCount,
      audioDurationMs: durationMs,
      deviceEventTimeMs:
          captureStartTimeMs + sampleOffsetMs(eventStartSample, sampleRateHz),
      eventEndTimeMs:
          captureStartTimeMs + sampleOffsetMs(eventEndSample, sampleRateHz),
      rmsPeakTimeMs:
          captureStartTimeMs + sampleOffsetMs(rmsPeakSample, sampleRateHz),
    );
  }

  static int sampleOffsetMs(int sampleIndex, int sampleRateHz) {
    if (sampleRateHz <= 0) {
      throw ArgumentError.value(sampleRateHz, 'sampleRateHz', 'must be > 0');
    }
    return (sampleIndex * 1000 / sampleRateHz).round();
  }

  static EventTimingMetadata? fromJsonOrNull(Map<String, dynamic> json) {
    final timingVersion = _toInt(json['timing_version']);
    final timingSource = json['timing_source']?.toString();
    final captureStartTimeMs = _toInt(json['capture_start_time_ms']);
    final eventStartSample = _toInt(json['event_start_sample']);
    final eventEndSample = _toInt(json['event_end_sample']);
    final rmsPeakSample = _toInt(json['rms_peak_sample']);
    final sampleRateHz = _toInt(json['sample_rate_hz']);
    final channelCount = _toInt(json['channel_count']);
    final audioDurationMs = _toInt(json['audio_duration_ms']);
    final deviceEventTimeMs = _toInt(json['device_event_time_ms']);
    final eventEndTimeMs = _toInt(json['event_end_time_ms']);
    final rmsPeakTimeMs = _toInt(json['rms_peak_time_ms']);

    if (timingVersion == null ||
        timingSource == null ||
        captureStartTimeMs == null ||
        eventStartSample == null ||
        eventEndSample == null ||
        rmsPeakSample == null ||
        sampleRateHz == null ||
        channelCount == null ||
        audioDurationMs == null ||
        deviceEventTimeMs == null ||
        eventEndTimeMs == null ||
        rmsPeakTimeMs == null) {
      return null;
    }

    if (timingVersion < 1 ||
        sampleRateHz <= 0 ||
        channelCount <= 0 ||
        audioDurationMs < 0 ||
        eventStartSample < 0 ||
        eventEndSample < eventStartSample ||
        rmsPeakSample < 0 ||
        rmsPeakSample > eventEndSample) {
      return null;
    }

    return EventTimingMetadata(
      timingVersion: timingVersion,
      timingSource: timingSource,
      captureStartTimeMs: captureStartTimeMs,
      eventStartSample: eventStartSample,
      eventEndSample: eventEndSample,
      rmsPeakSample: rmsPeakSample,
      sampleRateHz: sampleRateHz,
      channelCount: channelCount,
      audioDurationMs: audioDurationMs,
      deviceEventTimeMs: deviceEventTimeMs,
      eventEndTimeMs: eventEndTimeMs,
      rmsPeakTimeMs: rmsPeakTimeMs,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'timing_version': timingVersion,
      'timing_source': timingSource,
      'capture_start_time_ms': captureStartTimeMs,
      'event_start_sample': eventStartSample,
      'event_end_sample': eventEndSample,
      'rms_peak_sample': rmsPeakSample,
      'sample_rate_hz': sampleRateHz,
      'channel_count': channelCount,
      'audio_duration_ms': audioDurationMs,
      'device_event_time_ms': deviceEventTimeMs,
      'event_end_time_ms': eventEndTimeMs,
      'rms_peak_time_ms': rmsPeakTimeMs,
    };
  }

  double get rmsPeakOffsetMs =>
      sampleOffsetMs(rmsPeakSample, sampleRateHz).toDouble();

  static int? _toInt(dynamic value) {
    if (value == null) return null;
    if (value is int) return value;
    if (value is num) return value.round();
    return int.tryParse(value.toString());
  }
}
