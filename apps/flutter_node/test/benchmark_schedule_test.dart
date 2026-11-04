import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/benchmark/schedule.dart';
import 'package:sound_detector_clean/benchmark/stats.dart';

void main() {
  test(
    '300ms reference is measured between 350 and 250 then continues to 100',
    () {
      expect(benchmarkHops, [
        1500,
        1000,
        750,
        500,
        350,
        300,
        250,
        200,
        150,
        100,
      ]);
      expect(benchmarkProtocolVersion, 'benchmark.protocol.v1.2');
    },
  );
  test('warmup needs elapsed time and completed samples', () {
    expect(phaseHasEnoughData('warmup', 3, 30000), false);
    expect(phaseHasEnoughData('warmup', 8, 14999), false);
    expect(phaseHasEnoughData('warmup', 8, 15000), true);
  });
  test('first survey cannot stop from a spike before 30 samples', () {
    expect(shouldStopOverloaded('survey', 10, 3205, 1500), false);
    expect(shouldStopOverloaded('survey', 12, 3205, 1500), false);
    expect(shouldStopOverloaded('survey', 30, 3205, 1500), true);
    expect(shouldStopOverloaded('survey', 30, 3000, 1500), false);
    expect(shouldStopOverloaded('warmup', 30, 9999, 100), false);
  });
  test('confirmation still needs two minutes and sixty samples', () {
    expect(phaseHasEnoughData('survey', 29, 90000), false);
    expect(phaseHasEnoughData('survey', 30, 20000), true);
    expect(phaseHasEnoughData('confirmation', 60, 119999), false);
    expect(phaseHasEnoughData('confirmation', 59, 180000), false);
    expect(phaseHasEnoughData('confirmation', 60, 120000), true);
  });
  test('observed Redmi no-drop runs do not stop descent before 500ms', () {
    expect(hasSubstantialWindowLoss(12, 0), false);
    expect(hasSubstantialWindowLoss(31, 0), false);
    expect(hasSubstantialWindowLoss(30, 7), false);
    expect(hasSubstantialWindowLoss(32, 8), true);
    expect(hasSubstantialWindowLoss(29, 20), false);
  });
}
