import 'package:flutter/material.dart';

import '../models/classification_presentation.dart';
import '../models/event_view_data.dart';
import 'status_badge.dart';

class LatestEventCard extends StatelessWidget {
  const LatestEventCard({super.key, required this.event, required this.onTap});

  final EventViewData? event;
  final VoidCallback onTap;

  String _percentage(double value) {
    final normalized = value > 1 ? value : value * 100;
    return '${normalized.clamp(0, 100).toStringAsFixed(0)}%';
  }

  @override
  Widget build(BuildContext context) {
    final current = event;
    final scheme = Theme.of(context).colorScheme;
    if (current == null) {
      return Container(
        key: const ValueKey('latest-event-card'),
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 10),
        decoration: BoxDecoration(
          color: scheme.surfaceContainerLow,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: scheme.outlineVariant),
        ),
        child: Row(
          children: [
            Icon(Icons.history, size: 18, color: scheme.onSurfaceVariant),
            const SizedBox(width: 8),
            const Text(
              '最近事件',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
            ),
            const Spacer(),
            Text(
              '尚無本機事件',
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      );
    }

    final presentation = classificationPresentationFor(
      current.rawLabel,
      targetOverride: current.isTarget,
    );
    final uploaded =
        current.metadataUploadStatus == 'uploaded' ||
        current.metadataUploadStatus.startsWith('uploaded_');
    final accent = operationalStatusColor(context, presentation.level);

    return Card(
      key: const ValueKey('latest-event-card'),
      color: presentation.isTarget
          ? accent.withValues(alpha: 0.055)
          : scheme.surfaceContainerLow,
      clipBehavior: Clip.antiAlias,
      child: Semantics(
        button: true,
        label: '查看最近事件',
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(10, 8, 7, 8),
            child: Row(
              children: [
                Icon(presentation.icon, size: 23, color: accent),
                const SizedBox(width: 9),
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Text(
                              '${presentation.englishLabel} · ${presentation.localizedLabel}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                          if (current.confidence != null) ...[
                            const SizedBox(width: 7),
                            Text(
                              _percentage(current.confidence!),
                              style: TextStyle(
                                color: accent,
                                fontSize: 13,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        [
                          current.time,
                          if (current.estimatedPeakDb != null)
                            '${current.estimatedPeakDb!.toStringAsFixed(1)} dB 估算',
                          uploaded ? '✓ 已上傳' : '↻ 等待補傳',
                        ].join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 11,
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right, size: 20),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
