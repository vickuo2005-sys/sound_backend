import 'dart:math';

const benchmarkHops = [1500, 1000, 750, 500, 350, 250, 200, 150, 100];
const criteriaVersion = 'benchmark.v1';
const timingMetrics = [
  'native_queue_ms',
  'native_save_ms',
  'bridge_upper_ms',
  'flutter_queue_ms',
  'preprocess_ms',
  'inference_ms',
  'pipeline_upper_ms',
];

Map<String, dynamic> runStatistics(Map<String, dynamic> run) => {
  for (final metric in timingMetrics)
    metric: summarize((run['samples'] as List).map((s) => s[metric] as num)),
  'evaluation': evaluateRun(run),
};

Map<String, double>? summarize(Iterable<num> input) {
  final values = input.map((v) => v.toDouble()).toList()..sort();
  if (values.isEmpty) return null;
  if (values.any((v) => !v.isFinite || v < 0)) {
    throw ArgumentError('invalid duration');
  }
  double p(double q) => values[max(0, (q * values.length).ceil() - 1)];
  return {
    'p50': p(.5),
    'p95': p(.95),
    'p99': p(.99),
    'average': values.reduce((a, b) => a + b) / values.length,
    'maximum': values.last,
  };
}

Map<String, dynamic> evaluateRun(Map<String, dynamic> run) {
  final samples = (run['samples'] as List).cast<Map<String, dynamic>>();
  final p = summarize(samples.map((s) => s['pipeline_upper_ms'] as num));
  final errors = <String>[];
  final confirmation = run['phase'] == 'confirmation';
  if (samples.length < (confirmation ? 60 : 30)) {
    errors.add('insufficient_samples');
  }
  if (confirmation && (run['duration_ms'] as num) < 120000) {
    errors.add('confirmation_too_short');
  }
  if (samples.isEmpty ||
      samples.where((s) => s['success'] == true).length / samples.length <
          .99) {
    errors.add('inference_success');
  }
  if ((run['dropped'] as num) / max(1, run['generated'] as int) > .01) {
    errors.add('dropped_rate');
  }
  if (p == null || p['p95']! >= (run['hop_ms'] as num)) {
    errors.add('pipeline_budget');
  }
  if ((run['max_backlog'] as num) > 2) errors.add('backlog');
  if (run['thermal_max'] != null && (run['thermal_max'] as num) >= 3) {
    errors.add('thermal');
  }
  if ((run['errors'] as List).isNotEmpty) errors.add('interrupted_or_error');
  return {
    'passed': errors.isEmpty,
    'reasons': errors,
    'pipeline': p,
    'recommended': errors.isEmpty && p!['p95']! < .8 * (run['hop_ms'] as num),
  };
}

Map<String, int?> decide(List<Map<String, dynamic>> runs) {
  int? lowest(Iterable<Map<String, dynamic>> rs) =>
      rs.isEmpty ? null : rs.map((r) => r['hop_ms'] as int).reduce(min);
  return {
    'lowest_operating_hop': lowest(
      runs.where(
        (r) =>
            (r['processed'] as int) >= 30 &&
            (r['samples'] as List).every((s) => s['success'] == true) &&
            (r['errors'] as List).isEmpty,
      ),
    ),
    'lowest_stable_hop': lowest(
      runs.where(
        (r) => r['phase'] == 'confirmation' && evaluateRun(r)['passed'] == true,
      ),
    ),
    'recommended_hop': lowest(
      runs.where(
        (r) =>
            r['phase'] == 'confirmation' &&
            evaluateRun(r)['recommended'] == true,
      ),
    ),
  };
}

String csvCell(Object? value) {
  var text = value?.toString() ?? '';
  if (RegExp(r'^\s*[=+@-]').hasMatch(text)) text = "'$text";
  return '"${text.replaceAll('"', '""')}"';
}
