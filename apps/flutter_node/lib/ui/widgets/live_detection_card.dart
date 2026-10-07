import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../models/sound_level_reading.dart';
import 'status_badge.dart';

class LiveDetectionCard extends StatelessWidget {
  const LiveDetectionCard({
    super.key,
    required this.isListening,
    required this.listeningTime,
    required this.soundLevel,
  });

  final bool isListening;
  final String listeningTime;
  final ValueListenable<SoundLevelReading> soundLevel;

  @override
  Widget build(BuildContext context) {
    final level = isListening
        ? OperationalStatusLevel.healthy
        : OperationalStatusLevel.neutral;
    final accent = operationalStatusColor(context, level);
    final scheme = Theme.of(context).colorScheme;

    return Card(
      key: const ValueKey('live-detection-card'),
      color: scheme.surfaceContainer,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 11, 14, 10),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(Icons.graphic_eq, size: 16, color: accent),
                const SizedBox(width: 6),
                const Text(
                  '即時聲音偵測',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.5,
                  ),
                ),
                const Spacer(),
                Icon(
                  isListening
                      ? Icons.fiber_manual_record
                      : Icons.radio_button_unchecked,
                  size: 14,
                  color: accent,
                ),
              ],
            ),
            const SizedBox(height: 7),
            Center(
              child: Container(
                width: 30,
                height: 30,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: accent.withValues(alpha: 0.10),
                  border: Border.all(
                    color: accent.withValues(alpha: 0.45),
                    width: 1.5,
                  ),
                ),
                child: Icon(
                  isListening ? Icons.hearing : Icons.mic_off_outlined,
                  color: accent,
                  size: 17,
                ),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              isListening ? '正在監聽' : '聲音監聽\n未啟動',
              key: const ValueKey('live-listening-state'),
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 17,
                height: 1.05,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              listeningTime,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: isListening ? accent : scheme.onSurfaceVariant,
                fontSize: 25,
                height: 1.05,
                fontWeight: FontWeight.w700,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
            const SizedBox(height: 5),
            ValueListenableBuilder<SoundLevelReading>(
              valueListenable: soundLevel,
              builder: (context, reading, _) {
                final value = isListening ? reading.estimatedDb : null;
                return Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      value == null ? '—' : value.toStringAsFixed(1),
                      key: const ValueKey('live-estimated-db'),
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 35,
                        height: 0.95,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      'dB 估算',
                      style: TextStyle(
                        color: scheme.onSurfaceVariant,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                );
              },
            ),
            const SizedBox(height: 7),
            ValueListenableBuilder<SoundLevelReading>(
              valueListenable: soundLevel,
              builder: (context, reading, _) {
                return _SegmentedLevelMeter(
                  key: const ValueKey('live-level-meter'),
                  estimatedDb: isListening ? reading.estimatedDb : null,
                );
              },
            ),
            const SizedBox(height: 5),
            Text(
              isListening ? '尚未校正為 SPL' : '尚未取得聲音訊號',
              textAlign: TextAlign.center,
              style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 10),
            ),
          ],
        ),
      ),
    );
  }
}

class _SegmentedLevelMeter extends StatelessWidget {
  const _SegmentedLevelMeter({super.key, required this.estimatedDb});

  static const int _segmentCount = 18;

  final double? estimatedDb;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final normalized = ((estimatedDb ?? 0) / 95).clamp(0.0, 1.0);
    final activeCount = (normalized * _segmentCount).round();

    return Semantics(
      label: estimatedDb == null
          ? '尚未取得聲音強度'
          : '目前聲音強度 ${estimatedDb!.toStringAsFixed(1)} dB 估算',
      child: Row(
        children: List.generate(_segmentCount, (index) {
          final active = index < activeCount;
          final segmentColor = index >= 15
              ? const Color(0xFFFB923C)
              : index >= 11
              ? const Color(0xFFFBBF24)
              : scheme.primary;
          return Expanded(
            child: Container(
              height: 7,
              margin: EdgeInsets.only(
                right: index == _segmentCount - 1 ? 0 : 3,
              ),
              decoration: BoxDecoration(
                color: active ? segmentColor : scheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          );
        }),
      ),
    );
  }
}
