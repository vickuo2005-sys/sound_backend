import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/post_inference_latency.dart';

void main() {
  test('parses db ingest and db ping Server-Timing durations', () {
    final parsed = parseServerTimingDurations(
      'db;dur=42.15, fixed_location;dur=0.08, ingest;dur=48.90, db_ping;dur=11.2',
    );

    expect(parsed['db'], 42.15);
    expect(parsed['fixed_location'], 0.08);
    expect(parsed['ingest'], 48.90);
    expect(parsed['db_ping'], 11.2);
  });

  test('monotonic duration rejects invalid or reversed clocks', () {
    expect(
      monotonicDurationMs(
        <String, dynamic>{'start': 100.25, 'end': 125.75},
        'start',
        'end',
      ),
      25.5,
    );
    expect(
      monotonicDurationMs(
        <String, dynamic>{'start': 20, 'end': 10},
        'start',
        'end',
      ),
      isNull,
    );
  });
}
