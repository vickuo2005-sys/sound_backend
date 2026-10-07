import 'package:flutter/material.dart';

class MonitorPrimaryAction extends StatelessWidget {
  const MonitorPrimaryAction({
    super.key,
    required this.isListening,
    required this.onPressed,
  });

  final bool isListening;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 9),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLowest,
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      child: SafeArea(
        top: false,
        bottom: false,
        child: FilledButton.icon(
          key: const ValueKey('monitor-primary-action'),
          onPressed: onPressed,
          icon: Icon(
            isListening ? Icons.stop_rounded : Icons.play_arrow_rounded,
          ),
          label: Text(isListening ? '停止監聽' : '開始監聽'),
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(48),
            backgroundColor: isListening
                ? scheme.errorContainer
                : scheme.primaryContainer,
            foregroundColor: isListening
                ? scheme.onErrorContainer
                : scheme.onPrimaryContainer,
            side: BorderSide(
              color: isListening
                  ? scheme.error.withValues(alpha: 0.45)
                  : scheme.primary.withValues(alpha: 0.42),
            ),
          ),
        ),
      ),
    );
  }
}
