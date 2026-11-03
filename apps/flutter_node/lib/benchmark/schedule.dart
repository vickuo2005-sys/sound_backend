/// V1.1 changes execution policy, not the pass/recommendation thresholds.
const benchmarkPipelineVersion = 'native-wav-ai.v2';
const benchmarkProtocolVersion = 'benchmark.protocol.v1.1';
const warmupMinimumMs = 15000;
const warmupMinimumSamples = 8;
const warmupTimeoutMs = 45000;

bool phaseHasEnoughData(String phase, int samples, int elapsedMs) {
  if (phase == 'warmup') {
    return samples >= warmupMinimumSamples && elapsedMs >= warmupMinimumMs;
  }
  if (phase == 'confirmation') return samples >= 60 && elapsedMs >= 120000;
  return samples >= 30;
}

bool shouldStopOverloaded(String phase, int samples, double p95, int hop) =>
    phase != 'warmup' && samples >= 30 && p95 > 2 * hop;

/// Missing a latency budget alone does not prove throughput overload.
/// Only two consecutive runs with substantial observed loss stop descent.
bool hasSubstantialWindowLoss(int generated, int dropped) =>
    generated >= 30 && dropped / generated >= .25;
