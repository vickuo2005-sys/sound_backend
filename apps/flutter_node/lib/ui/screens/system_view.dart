import 'package:flutter/material.dart';

import '../widgets/status_badge.dart';

class SystemModelOption {
  const SystemModelOption({required this.id, required this.name});

  final String id;
  final String name;
}

class SystemStatusData {
  const SystemStatusData({
    required this.label,
    required this.value,
    required this.icon,
    required this.level,
  });

  final String label;
  final String value;
  final IconData icon;
  final OperationalStatusLevel level;
}

class SystemInfoData {
  const SystemInfoData({required this.label, required this.value});

  final String label;
  final String value;
}

class SystemView extends StatelessWidget {
  const SystemView({
    super.key,
    required this.deviceIdController,
    required this.savedDeviceId,
    required this.isListening,
    required this.dedicatedNodeMode,
    required this.onSaveDeviceId,
    required this.selectedModelId,
    required this.modelOptions,
    required this.onModelChanged,
    required this.modelStatus,
    required this.sampleRateHz,
    required this.windowMs,
    required this.hopMs,
    required this.uploadMode,
    required this.onUploadModeChanged,
    required this.connectivity,
    required this.automation,
    required this.diagnostics,
    required this.themeMode,
    required this.onThemeModeChanged,
    required this.onUploadLatestWav,
    required this.onClearLocalRecords,
  });

  final TextEditingController deviceIdController;
  final String savedDeviceId;
  final bool isListening;
  final bool dedicatedNodeMode;
  final VoidCallback onSaveDeviceId;
  final String selectedModelId;
  final List<SystemModelOption> modelOptions;
  final ValueChanged<String?> onModelChanged;
  final String modelStatus;
  final int sampleRateHz;
  final int windowMs;
  final int hopMs;
  final String uploadMode;
  final ValueChanged<String> onUploadModeChanged;
  final List<SystemStatusData> connectivity;
  final List<SystemInfoData> automation;
  final List<SystemInfoData> diagnostics;
  final ThemeMode themeMode;
  final ValueChanged<ThemeMode> onThemeModeChanged;
  final VoidCallback onUploadLatestWav;
  final VoidCallback onClearLocalRecords;

  @override
  Widget build(BuildContext context) {
    return Scrollbar(
      child: ListView(
        key: const PageStorageKey('system-scroll'),
        padding: const EdgeInsets.fromLTRB(12, 6, 12, 18),
        children: [
          _SettingsSection(
            title: '節點',
            icon: Icons.sensors,
            child: Column(
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: TextField(
                        key: const ValueKey('system-node-id-field'),
                        controller: deviceIdController,
                        enabled: !isListening,
                        textInputAction: TextInputAction.done,
                        decoration: const InputDecoration(labelText: '節點 ID'),
                        onSubmitted: (_) {
                          if (!isListening) onSaveDeviceId();
                        },
                      ),
                    ),
                    const SizedBox(width: 8),
                    IconButton.filledTonal(
                      key: const ValueKey('system-save-node-id'),
                      tooltip: '儲存節點 ID',
                      onPressed: isListening ? null : onSaveDeviceId,
                      icon: const Icon(Icons.save_outlined),
                    ),
                  ],
                ),
                if (isListening) const _InlineNotice('監聽中鎖定節點 ID，請先停止監聽。'),
                ValueListenableBuilder<TextEditingValue>(
                  valueListenable: deviceIdController,
                  builder: (context, input, _) {
                    if (input.text.trim() == savedDeviceId.trim()) {
                      return const SizedBox.shrink();
                    }
                    return _InlineNotice(
                      '尚未儲存變更 · 目前已儲存：$savedDeviceId',
                      key: const ValueKey('system-node-id-unsaved'),
                    );
                  },
                ),
                const SizedBox(height: 4),
                const Divider(),
                _InfoRow(
                  label: '專用節點模式',
                  value: dedicatedNodeMode ? '啟用' : '未啟用',
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          _SettingsSection(
            title: '外觀',
            icon: Icons.contrast,
            child: SizedBox(
              width: double.infinity,
              child: SegmentedButton<ThemeMode>(
                key: const ValueKey('system-theme-selector'),
                showSelectedIcon: false,
                style: const ButtonStyle(
                  visualDensity: VisualDensity.compact,
                  minimumSize: WidgetStatePropertyAll(Size.fromHeight(38)),
                ),
                segments: const [
                  ButtonSegment(
                    value: ThemeMode.dark,
                    label: Text('深色'),
                    icon: Icon(Icons.dark_mode_outlined),
                  ),
                  ButtonSegment(
                    value: ThemeMode.system,
                    label: Text('系統'),
                    icon: Icon(Icons.settings_brightness_outlined),
                  ),
                  ButtonSegment(
                    value: ThemeMode.light,
                    label: Text('淺色'),
                    icon: Icon(Icons.light_mode_outlined),
                  ),
                ],
                selected: {themeMode},
                onSelectionChanged: (selection) {
                  onThemeModeChanged(selection.first);
                },
              ),
            ),
          ),
          const SizedBox(height: 12),
          _SettingsSection(
            title: '偵測',
            icon: Icons.radar,
            child: Column(
              children: [
                DropdownButtonFormField<String>(
                  key: const ValueKey('system-model-selector'),
                  initialValue: selectedModelId,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'AI 模型'),
                  items: modelOptions.map((option) {
                    return DropdownMenuItem<String>(
                      value: option.id,
                      child: Text(
                        option.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    );
                  }).toList(),
                  onChanged: isListening ? null : onModelChanged,
                ),
                if (isListening) const _InlineNotice('監聽中鎖定模型，請先停止監聽。'),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  child: SegmentedButton<String>(
                    showSelectedIcon: false,
                    style: const ButtonStyle(
                      visualDensity: VisualDensity.compact,
                      minimumSize: WidgetStatePropertyAll(Size.fromHeight(38)),
                    ),
                    segments: const [
                      ButtonSegment(
                        value: 'detection_only',
                        label: Text('偵測模式'),
                        icon: Icon(Icons.radar),
                      ),
                      ButtonSegment(
                        value: 'collect_all',
                        label: Text('蒐集模式'),
                        icon: Icon(Icons.dataset_outlined),
                      ),
                    ],
                    selected: {uploadMode},
                    onSelectionChanged: isListening
                        ? null
                        : (selection) => onUploadModeChanged(selection.first),
                  ),
                ),
                const SizedBox(height: 6),
                _InfoRow(label: '模型狀態', value: modelStatus),
                const Divider(),
                _InfoRow(label: '取樣率', value: '$sampleRateHz Hz'),
                const Divider(),
                _InfoRow(
                  label: '分析視窗',
                  value: '${(windowMs / 1000).toStringAsFixed(1)} s',
                ),
                const Divider(),
                _InfoRow(
                  label: '推論間隔',
                  value: '${(hopMs / 1000).toStringAsFixed(1)} s',
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          _SettingsSection(
            title: '連線狀態',
            icon: Icons.hub_outlined,
            child: Column(
              children: [
                for (var index = 0; index < connectivity.length; index++) ...[
                  _StatusRow(data: connectivity[index]),
                  if (index < connectivity.length - 1) const Divider(),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),
          _SettingsSection(
            title: '自動化',
            icon: Icons.settings_suggest_outlined,
            child: Column(
              children: [
                for (var index = 0; index < automation.length; index++) ...[
                  _InfoRow(
                    label: automation[index].label,
                    value: automation[index].value,
                  ),
                  if (index < automation.length - 1) const Divider(),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),
          _DiagnosticsPanel(
            diagnostics: diagnostics,
            onUploadLatestWav: onUploadLatestWav,
            onClearLocalRecords: onClearLocalRecords,
          ),
        ],
      ),
    );
  }
}

class _SettingsSection extends StatelessWidget {
  const _SettingsSection({
    required this.title,
    required this.icon,
    required this.child,
  });

  final String title;
  final IconData icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 0, 4, 5),
          child: Row(
            children: [
              Icon(icon, size: 15, color: scheme.primary),
              const SizedBox(width: 6),
              Text(
                title,
                style: TextStyle(
                  color: scheme.onSurfaceVariant,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.8,
                ),
              ),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          decoration: BoxDecoration(
            color: scheme.surfaceContainerLow,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: child,
        ),
      ],
    );
  }
}

class _DiagnosticsPanel extends StatefulWidget {
  const _DiagnosticsPanel({
    required this.diagnostics,
    required this.onUploadLatestWav,
    required this.onClearLocalRecords,
  });

  final List<SystemInfoData> diagnostics;
  final VoidCallback onUploadLatestWav;
  final VoidCallback onClearLocalRecords;

  @override
  State<_DiagnosticsPanel> createState() => _DiagnosticsPanelState();
}

class _DiagnosticsPanelState extends State<_DiagnosticsPanel> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          InkWell(
            key: const ValueKey('system-diagnostics-header'),
            borderRadius: BorderRadius.circular(14),
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
              child: Row(
                children: [
                  Icon(
                    Icons.monitor_heart_outlined,
                    size: 17,
                    color: scheme.primary,
                  ),
                  const SizedBox(width: 7),
                  const Expanded(
                    child: Text(
                      '診斷資訊',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.8,
                      ),
                    ),
                  ),
                  Text(
                    _expanded ? '收合' : '查看進階資訊',
                    style: TextStyle(
                      fontSize: 11,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(width: 5),
                  Icon(
                    _expanded ? Icons.expand_less : Icons.chevron_right,
                    size: 20,
                  ),
                ],
              ),
            ),
          ),
          if (_expanded)
            Padding(
              key: const ValueKey('system-diagnostics-content'),
              padding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
              child: Column(
                children: [
                  const Divider(),
                  for (
                    var index = 0;
                    index < widget.diagnostics.length;
                    index++
                  ) ...[
                    _InfoRow(
                      label: widget.diagnostics[index].label,
                      value: widget.diagnostics[index].value,
                    ),
                    if (index < widget.diagnostics.length - 1) const Divider(),
                  ],
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: widget.onUploadLatestWav,
                          icon: const Icon(Icons.upload_file),
                          label: const Text('上傳最新 WAV'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: widget.onClearLocalRecords,
                          icon: const Icon(Icons.cleaning_services_outlined),
                          label: const Text('清除本機紀錄'),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  const _StatusRow({required this.data});

  final SystemStatusData data;

  @override
  Widget build(BuildContext context) {
    final color = operationalStatusColor(context, data.level);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        children: [
          Expanded(
            child: Text(data.label, style: const TextStyle(fontSize: 13)),
          ),
          const SizedBox(width: 10),
          Icon(data.icon, size: 16, color: color),
          const SizedBox(width: 5),
          Flexible(
            child: Text(
              data.value,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.right,
              style: TextStyle(
                color: color,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: Text(label, style: const TextStyle(fontSize: 13))),
          const SizedBox(width: 12),
          Flexible(
            child: Text(
              value,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}

class _InlineNotice extends StatelessWidget {
  const _InlineNotice(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 5),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Text(
          text,
          style: TextStyle(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
            fontSize: 11,
          ),
        ),
      ),
    );
  }
}
