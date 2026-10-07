import 'package:flutter/material.dart';

import '../models/classification_presentation.dart';
import '../models/event_view_data.dart';
import 'status_badge.dart';

class EventListItem extends StatelessWidget {
  const EventListItem({
    super.key,
    required this.event,
    required this.isPlaying,
    required this.onTap,
    required this.onPlay,
  });

  final EventViewData event;
  final bool isPlaying;
  final VoidCallback onTap;
  final VoidCallback onPlay;

  String _percentage(double value) {
    final normalized = value > 1 ? value : value * 100;
    return '${normalized.clamp(0, 100).toStringAsFixed(0)}%';
  }

  @override
  Widget build(BuildContext context) {
    final presentation = classificationPresentationFor(
      event.rawLabel,
      targetOverride: event.isTarget,
    );
    final uploaded =
        event.metadataUploadStatus == 'uploaded' ||
        event.metadataUploadStatus.startsWith('uploaded_');
    final accent = operationalStatusColor(context, presentation.level);
    final scheme = Theme.of(context).colorScheme;

    return Card(
      key: ValueKey('event-row-${event.eventId}'),
      margin: const EdgeInsets.only(bottom: 6),
      color: presentation.isTarget
          ? accent.withValues(alpha: 0.045)
          : scheme.surfaceContainerLow,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 88),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(10, 8, 4, 8),
            child: Row(
              children: [
                Container(
                  width: 38,
                  height: 38,
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: 0.11),
                    borderRadius: BorderRadius.circular(11),
                    border: Border.all(color: accent.withValues(alpha: 0.24)),
                  ),
                  child: Icon(presentation.icon, color: accent, size: 22),
                ),
                const SizedBox(width: 9),
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
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
                          if (event.confidence != null)
                            Text(
                              _percentage(event.confidence!),
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                        ],
                      ),
                      const SizedBox(height: 3),
                      Text(
                        [
                          event.time,
                          if (event.estimatedPeakDb != null)
                            '${event.estimatedPeakDb!.toStringAsFixed(1)} dB 估算',
                        ].join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: scheme.onSurfaceVariant,
                          fontSize: 11,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          Icon(
                            presentation.isTarget
                                ? Icons.notification_important
                                : Icons.eco_outlined,
                            size: 13,
                            color: accent,
                          ),
                          const SizedBox(width: 3),
                          Text(
                            presentation.isTarget ? '目標' : '其他',
                            style: TextStyle(
                              color: accent,
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Icon(
                            uploaded ? Icons.cloud_done : Icons.sync,
                            size: 13,
                            color: uploaded
                                ? operationalStatusColor(
                                    context,
                                    OperationalStatusLevel.healthy,
                                  )
                                : operationalStatusColor(
                                    context,
                                    OperationalStatusLevel.warning,
                                  ),
                          ),
                          const SizedBox(width: 3),
                          Text(
                            uploaded ? '已上傳' : '等待補傳',
                            style: TextStyle(
                              color: scheme.onSurfaceVariant,
                              fontSize: 10,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                IconButton(
                  key: ValueKey('event-play-${event.eventId}'),
                  tooltip: isPlaying ? '停止播放' : '播放音檔',
                  onPressed: event.audioAvailable ? onPlay : null,
                  visualDensity: VisualDensity.compact,
                  iconSize: 21,
                  icon: Icon(
                    isPlaying ? Icons.stop_circle_outlined : Icons.play_circle,
                  ),
                ),
                const Icon(Icons.chevron_right, size: 18),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class EventDetailSheet extends StatelessWidget {
  const EventDetailSheet({
    super.key,
    required this.event,
    required this.isPlaying,
    required this.onPlay,
    required this.onDelete,
  });

  final EventViewData event;
  final bool isPlaying;
  final VoidCallback onPlay;
  final VoidCallback onDelete;

  String _number(double? value, {int digits = 2}) {
    return value == null ? '無' : value.toStringAsFixed(digits);
  }

  String _probability(double? value) {
    if (value == null) return '無';
    final normalized = value > 1 ? value : value * 100;
    return '${normalized.clamp(0, 100).toStringAsFixed(1)}%';
  }

  String _statusText(String? value) {
    if (value == null || value.isEmpty || value == 'N/A') return '無';
    return switch (value) {
      'uploaded' => '已上傳',
      'pending' => '等待處理',
      'success' => '成功',
      'failed' => '失敗',
      'no_location' => '無位置',
      'available' => '可用',
      'unavailable' => '不可用',
      _ => value,
    };
  }

  @override
  Widget build(BuildContext context) {
    final presentation = classificationPresentationFor(
      event.rawLabel,
      targetOverride: event.isTarget,
    );
    final accent = operationalStatusColor(context, presentation.level);
    final metadataUploaded =
        event.metadataUploadStatus == 'uploaded' ||
        event.metadataUploadStatus.startsWith('uploaded_');
    final audioUploaded = event.cloudAudioPath?.isNotEmpty == true;

    return SafeArea(
      top: false,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 22),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.outline,
                  borderRadius: BorderRadius.circular(99),
                ),
              ),
            ),
            const SizedBox(height: 15),
            Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: Icon(presentation.icon, color: accent, size: 25),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        presentation.englishLabel,
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Text(
                        presentation.localizedLabel,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                if (event.isTarget)
                  StatusBadge(
                    label: '目標',
                    icon: Icons.notification_important,
                    level: OperationalStatusLevel.target,
                    compact: true,
                  ),
              ],
            ),
            const SizedBox(height: 16),
            _DetailSection(
              title: '分類',
              rows: [
                _DetailValue(label: '模型分類', value: event.rawLabel),
                _DetailValue(
                  label: '信心值',
                  value: _probability(event.confidence),
                ),
                if (event.aircraftProbability != null)
                  _DetailValue(
                    label: '目標總機率',
                    value: _probability(event.aircraftProbability),
                  ),
              ],
            ),
            _DetailSection(
              title: '時間',
              rows: [
                _DetailValue(label: '事件時間', value: event.time),
                _DetailValue(label: '節點 ID', value: event.deviceId),
                if (event.aiInferenceTimeMs != null)
                  _DetailValue(
                    label: 'AI 推論耗時',
                    value: '${event.aiInferenceTimeMs} ms',
                  ),
              ],
            ),
            _DetailSection(
              title: '訊號',
              rows: [
                if (event.estimatedPeakDb != null)
                  _DetailValue(
                    label: '峰值',
                    value: '${event.estimatedPeakDb!.toStringAsFixed(1)} dB 估算',
                  ),
                if (event.estimatedAvgDb != null)
                  _DetailValue(
                    label: '平均值',
                    value: '${event.estimatedAvgDb!.toStringAsFixed(1)} dB 估算',
                  ),
                if (event.avgRms != null)
                  _DetailValue(label: '平均 RMS', value: _number(event.avgRms)),
                if (event.peakRms != null)
                  _DetailValue(label: '峰值 RMS', value: _number(event.peakRms)),
              ],
            ),
            _DetailSection(
              title: '位置',
              rows: [
                _DetailValue(
                  label: 'GPS',
                  value: event.latitude != null && event.longitude != null
                      ? '${event.latitude!.toStringAsFixed(6)}, ${event.longitude!.toStringAsFixed(6)}'
                      : '無',
                ),
                if (event.gpsAccuracyM != null)
                  _DetailValue(
                    label: '定位精度',
                    value: '±${event.gpsAccuracyM!.toStringAsFixed(1)} m',
                  ),
                if (event.locationStatus != null)
                  _DetailValue(
                    label: '定位狀態',
                    value: _statusText(event.locationStatus),
                  ),
              ],
            ),
            _DetailSection(
              title: '上傳',
              rows: [
                _DetailValue(
                  label: '事件資料',
                  value: metadataUploaded
                      ? '✓ 已上傳'
                      : '↻ ${_statusText(event.metadataUploadStatus)}',
                ),
                _DetailValue(
                  label: '音檔',
                  value: audioUploaded ? '✓ 已上傳' : '尚未上傳',
                ),
                _DetailValue(
                  label: '本機音檔',
                  value: event.audioAvailable ? '可用' : '不可用',
                ),
                if (event.audioFormat != null)
                  _DetailValue(label: '格式', value: event.audioFormat!),
                if (event.audioEncodingStatus != null)
                  _DetailValue(
                    label: '編碼狀態',
                    value: _statusText(event.audioEncodingStatus),
                  ),
                if (event.aiInferenceStatus != null)
                  _DetailValue(
                    label: 'AI 狀態',
                    value: _statusText(event.aiInferenceStatus),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            const _SectionLabel('操作'),
            const SizedBox(height: 7),
            FilledButton.tonalIcon(
              onPressed: event.audioAvailable ? onPlay : null,
              icon: Icon(isPlaying ? Icons.stop : Icons.play_arrow),
              label: Text(isPlaying ? '停止播放' : '播放音檔'),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              key: const ValueKey('event-detail-delete'),
              onPressed: onDelete,
              icon: const Icon(Icons.delete_outline),
              label: const Text('刪除本機紀錄'),
              style: OutlinedButton.styleFrom(
                foregroundColor: Theme.of(context).colorScheme.error,
                side: BorderSide(
                  color: Theme.of(
                    context,
                  ).colorScheme.error.withValues(alpha: 0.55),
                ),
                minimumSize: const Size.fromHeight(46),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DetailSection extends StatelessWidget {
  const _DetailSection({required this.title, required this.rows});

  final String title;
  final List<_DetailValue> rows;

  @override
  Widget build(BuildContext context) {
    if (rows.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _SectionLabel(title),
          const SizedBox(height: 5),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainer,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: Theme.of(context).colorScheme.outlineVariant,
              ),
            ),
            child: Column(
              children: [
                for (var index = 0; index < rows.length; index++) ...[
                  rows[index],
                  if (index < rows.length - 1) const Divider(),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: TextStyle(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        fontSize: 10,
        fontWeight: FontWeight.w700,
        letterSpacing: 0.9,
      ),
    );
  }
}

class _DetailValue extends StatelessWidget {
  const _DetailValue({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 112,
            child: Text(
              label,
              style: TextStyle(
                fontSize: 12,
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
