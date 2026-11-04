import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/benchmark/stats.dart';

Map<String, dynamic> run({
  int n = 60,
  int hop = 100,
  double pipeline = 30,
  String phase = 'confirmation',
}) => {
  'hop_ms': hop,
  'phase': phase,
  'duration_ms': 120000,
  'generated': n,
  'processed': n,
  'dropped': 0,
  'max_backlog': 2,
  'thermal_max': 0,
  'errors': <String>[],
  'samples': List.generate(
    n,
    (_) => <String, dynamic>{'success': true, 'pipeline_upper_ms': pipeline},
  ),
};

void main() {
  test('nearest rank percentiles and invalid inputs', () {
    expect(summarize([]), isNull);
    expect(summarize(List.generate(100, (i) => i + 1)), {
      'p50': 50.0,
      'p95': 95.0,
      'p99': 99.0,
      'average': 50.5,
      'maximum': 100.0,
    });
    expect(() => summarize([double.nan]), throwsArgumentError);
  });
  test('strict timing and recommendation margins', () {
    expect(evaluateRun(run())['recommended'], true);
    expect(evaluateRun(run(pipeline: 100))['passed'], false);
    expect(evaluateRun(run(pipeline: 80))['passed'], true);
    expect(evaluateRun(run(pipeline: 80))['recommended'], false);
  });
  test(
    'insufficient samples, short confirmation, thermal, drops, errors fail',
    () {
      expect(evaluateRun(run(n: 29, phase: 'survey'))['passed'], false);
      for (final change in [
        <String, dynamic>{'duration_ms': 119999},
        {'thermal_max': 3},
        {'dropped': 1, 'generated': 61},
        {'max_backlog': 3},
        {
          'errors': ['interrupted'],
        },
      ]) {
        expect(evaluateRun({...run(), ...change})['passed'], false);
      }
    },
  );
  test('survey is operational only; minimum stable requires confirmation', () {
    final result = decide([run(hop: 100, phase: 'survey'), run(hop: 250)]);
    expect(result['lowest_operating_hop'], 100);
    expect(result['lowest_stable_hop'], 250);
    expect(result['recommended_hop'], 250);
  });
  test('CSV quotes and formula escape', () {
    expect(csvCell('=A1'), '"\'=A1"');
    expect(csvCell('a,"b'), '"a,""b"');
  });
}
