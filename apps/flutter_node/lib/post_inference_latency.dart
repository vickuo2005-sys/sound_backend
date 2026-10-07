Map<String, double> parseServerTimingDurations(String? header) {
  final output = <String, double>{};
  for (final metric in (header ?? '').split(',')) {
    final parts = metric
        .split(';')
        .map((part) => part.trim())
        .where((part) => part.isNotEmpty)
        .toList();
    if (parts.isEmpty) continue;
    final durationPart = parts.skip(1).where((part) => part.startsWith('dur='));
    if (durationPart.isEmpty) continue;
    final duration = double.tryParse(durationPart.first.substring(4));
    if (duration == null || !duration.isFinite || duration < 0) continue;
    output[parts.first] = duration;
  }
  return output;
}

double? monotonicDurationMs(
  Map<String, dynamic> trace,
  String start,
  String end,
) {
  final startValue = trace[start];
  final endValue = trace[end];
  if (startValue is! num || endValue is! num) return null;
  final duration = endValue.toDouble() - startValue.toDouble();
  if (!duration.isFinite || duration < 0) return null;
  return duration;
}
