import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/time_sync_metadata.dart';

void main() {
  test('calculates offset from client midpoint and server time', () {
    const sample = TimeSyncSample(
      clientSendMs: 1000,
      serverTimeMs: 1120,
      clientReceiveMs: 1040,
    );

    expect(sample.rttMs, 40);
    expect(sample.midpointMs, 1020);
    expect(sample.offsetMs, 100);
  });

  test('maps RTT to time sync quality', () {
    expect(TimeSyncMetadata.qualityForRtt(null), 'missing');
    expect(TimeSyncMetadata.qualityForRtt(20), 'good');
    expect(TimeSyncMetadata.qualityForRtt(100), 'medium');
    expect(TimeSyncMetadata.qualityForRtt(250), 'poor');
    expect(TimeSyncMetadata.qualityForRtt(450), 'bad');
  });

  test('chooses lowest RTT sample', () {
    final best = bestTimeSyncSample(const [
      TimeSyncSample(clientSendMs: 0, serverTimeMs: 50, clientReceiveMs: 200),
      TimeSyncSample(clientSendMs: 0, serverTimeMs: 50, clientReceiveMs: 30),
      TimeSyncSample(clientSendMs: 0, serverTimeMs: 50, clientReceiveMs: 90),
    ]);

    expect(best?.rttMs, 30);
  });

  test('marks old metadata stale in payload', () {
    final metadata = TimeSyncMetadata(
      offsetMs: 12.5,
      rttMs: 30,
      quality: 'good',
      syncedAtUtc: DateTime.now().toUtc().subtract(const Duration(minutes: 3)),
    );

    expect(metadata.isFresh, isFalse);
    final payload = metadata.toJson();
    expect(payload['time_sync_version'], TimeSyncMetadata.version);
    expect(payload['time_sync_quality'], 'stale');
    expect(payload['time_sync_synced_at_ms'], metadata.syncedAtMs);
    expect(payload['time_sync_age_ms'], greaterThanOrEqualTo(180000));
    expect(payload['time_sync_at'], metadata.syncedAtIso);
    expect(payload['last_time_sync_at'], metadata.syncedAtIso);
  });
}
