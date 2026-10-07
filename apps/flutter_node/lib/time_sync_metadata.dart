class TimeSyncMetadata {
  static const int version = 1;
  static const Duration freshnessWindow = Duration(seconds: 120);

  final double offsetMs;
  final double rttMs;
  final String quality;
  final DateTime syncedAtUtc;

  const TimeSyncMetadata({
    required this.offsetMs,
    required this.rttMs,
    required this.quality,
    required this.syncedAtUtc,
  });

  bool get isFresh {
    return DateTime.now().toUtc().difference(syncedAtUtc).abs() <=
        freshnessWindow;
  }

  String get syncedAtIso => syncedAtUtc.toIso8601String();
  int get syncedAtMs => syncedAtUtc.millisecondsSinceEpoch;

  int ageMsAt(DateTime nowUtc) {
    return nowUtc.toUtc().difference(syncedAtUtc).inMilliseconds.abs();
  }

  Map<String, dynamic> toJson() {
    return {
      'time_sync_version': version,
      'time_sync_offset_ms': offsetMs,
      'time_sync_rtt_ms': rttMs,
      'time_sync_quality': isFresh ? quality : 'stale',
      'time_sync_synced_at_ms': syncedAtMs,
      'time_sync_age_ms': ageMsAt(DateTime.now().toUtc()),
      'time_sync_at': syncedAtIso,
      'last_time_sync_at': syncedAtIso,
    };
  }

  static String qualityForRtt(double? rttMs) {
    if (rttMs == null || rttMs < 0) return 'missing';
    if (rttMs <= 50) return 'good';
    if (rttMs <= 150) return 'medium';
    if (rttMs <= 300) return 'poor';
    return 'bad';
  }
}

class TimeSyncSample {
  final int clientSendMs;
  final int serverTimeMs;
  final int clientReceiveMs;

  const TimeSyncSample({
    required this.clientSendMs,
    required this.serverTimeMs,
    required this.clientReceiveMs,
  });

  double get rttMs => (clientReceiveMs - clientSendMs).toDouble();
  double get midpointMs => (clientSendMs + clientReceiveMs) / 2.0;
  double get offsetMs => serverTimeMs - midpointMs;

  TimeSyncMetadata toMetadata({DateTime? syncedAtUtc}) {
    return TimeSyncMetadata(
      offsetMs: offsetMs,
      rttMs: rttMs,
      quality: TimeSyncMetadata.qualityForRtt(rttMs),
      syncedAtUtc: syncedAtUtc ?? DateTime.now().toUtc(),
    );
  }
}

TimeSyncSample? bestTimeSyncSample(Iterable<TimeSyncSample> samples) {
  TimeSyncSample? best;
  for (final sample in samples) {
    if (sample.rttMs < 0) continue;
    if (best == null || sample.rttMs < best.rttMs) {
      best = sample;
    }
  }
  return best;
}
