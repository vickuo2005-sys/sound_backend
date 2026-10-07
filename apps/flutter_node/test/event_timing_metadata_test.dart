import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/event_timing_metadata.dart';

void main() {
  test('converts 16000 Hz sample offsets to milliseconds', () {
    expect(EventTimingMetadata.sampleOffsetMs(16000, 16000), 1000);
    expect(EventTimingMetadata.sampleOffsetMs(8000, 16000), 500);
  });

  test('builds derived event times from sample indexes', () {
    final timing = EventTimingMetadata.fromSampleIndexes(
      captureStartTimeMs: 1000000,
      eventStartSample: 16000,
      eventEndSample: 64000,
      rmsPeakSample: 28000,
      sampleRateHz: 16000,
      channelCount: 1,
    );

    expect(timing.deviceEventTimeMs, 1001000);
    expect(timing.eventEndTimeMs, 1004000);
    expect(timing.rmsPeakTimeMs, 1001750);
    expect(timing.audioDurationMs, 4000);
  });

  test('supports non-default sample rates', () {
    expect(EventTimingMetadata.sampleOffsetMs(4410, 44100), 100);
  });

  test('serializes backend field names exactly', () {
    final timing = EventTimingMetadata.fromSampleIndexes(
      captureStartTimeMs: 1780000000000,
      eventStartSample: 16000,
      eventEndSample: 64000,
      rmsPeakSample: 28000,
      sampleRateHz: 16000,
      channelCount: 1,
      audioDurationMs: 5000,
    );

    expect(timing.toJson(), {
      'timing_version': 1,
      'timing_source': 'PCM_SAMPLE_INDEX',
      'capture_start_time_ms': 1780000000000,
      'event_start_sample': 16000,
      'event_end_sample': 64000,
      'rms_peak_sample': 28000,
      'sample_rate_hz': 16000,
      'channel_count': 1,
      'audio_duration_ms': 5000,
      'device_event_time_ms': 1780000001000,
      'event_end_time_ms': 1780000004000,
      'rms_peak_time_ms': 1780000001750,
    });
  });

  test('rejects invalid timing metadata safely', () {
    final invalid = EventTimingMetadata.fromJsonOrNull({
      'timing_version': 1,
      'timing_source': 'PCM_SAMPLE_INDEX',
      'capture_start_time_ms': 1000000,
      'event_start_sample': 2000,
      'event_end_sample': 1000,
      'rms_peak_sample': 1500,
      'sample_rate_hz': 16000,
      'channel_count': 1,
      'audio_duration_ms': 100,
      'device_event_time_ms': 1000125,
      'event_end_time_ms': 1000063,
      'rms_peak_time_ms': 1000094,
    });

    expect(invalid, isNull);
  });
}
