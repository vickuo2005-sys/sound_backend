import 'package:flutter/material.dart';

import '../models/classification_presentation.dart';
import 'status_badge.dart';

class ClassificationCard extends StatelessWidget {
  const ClassificationCard({
    super.key,
    required this.label,
    this.confidence,
    this.aircraftProbability,
    this.subtype,
    this.targetOverride,
  });

  final String label;
  final double? confidence;
  final double? aircraftProbability;
  final String? subtype;
  final bool? targetOverride;

  double _normalized(double value) {
    return (value > 1 ? value / 100 : value).clamp(0.0, 1.0);
  }

  String _percentage(double value) {
    return '${(_normalized(value) * 100).toStringAsFixed(0)}%';
  }

  @override
  Widget build(BuildContext context) {
    final presentation = classificationPresentationFor(
      label,
      targetOverride: targetOverride,
    );
    final scheme = Theme.of(context).colorScheme;
    final accent = operationalStatusColor(context, presentation.level);
    final hasResult =
        label.trim().isNotEmpty &&
        label != 'N/A' &&
        label != 'sound_event' &&
        label != 'ai_failed';

    return Container(
      key: const ValueKey('classification-result-card'),
      padding: const EdgeInsets.all(11),
      decoration: BoxDecoration(
        color: presentation.isTarget
            ? accent.withValues(alpha: 0.055)
            : scheme.surfaceContainer,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: presentation.isTarget
              ? accent.withValues(alpha: 0.78)
              : scheme.outlineVariant,
          width: presentation.isTarget ? 1.4 : 1,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'AI 偵測結果',
                  style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (presentation.isTarget)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.notification_important, size: 14, color: accent),
                    const SizedBox(width: 3),
                    Text(
                      '目標',
                      style: TextStyle(
                        color: accent,
                        fontSize: 10,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 5),
          Row(
            children: [
              Container(
                width: 46,
                height: 46,
                decoration: BoxDecoration(
                  color: presentation.isTarget
                      ? scheme.tertiaryContainer
                      : accent.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(13),
                ),
                child: Icon(
                  presentation.icon,
                  key: ValueKey('classification-icon-${presentation.rawLabel}'),
                  color: presentation.isTarget ? scheme.tertiary : accent,
                  size: 26,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      hasResult ? presentation.englishLabel : '等待辨識',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      subtype?.trim().isNotEmpty == true
                          ? '${presentation.localizedLabel} · $subtype'
                          : presentation.localizedLabel,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: scheme.onSurfaceVariant,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              if (confidence != null) ...[
                const SizedBox(width: 8),
                Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      _percentage(confidence!),
                      style: TextStyle(
                        color: presentation.isTarget ? accent : null,
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      '信心值',
                      style: TextStyle(
                        color: scheme.onSurfaceVariant,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
          if (presentation.isTarget && confidence != null) ...[
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: LinearProgressIndicator(
                key: const ValueKey('target-confidence-meter'),
                value: _normalized(confidence!),
                minHeight: 6,
                backgroundColor: scheme.surfaceContainerHighest,
                color: accent,
              ),
            ),
            if (aircraftProbability != null) ...[
              const SizedBox(height: 4),
              Align(
                alignment: Alignment.centerRight,
                child: Text(
                  '目標總機率 ${_percentage(aircraftProbability!)}',
                  style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontSize: 10,
                  ),
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
