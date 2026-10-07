import 'package:flutter/material.dart';

enum OperationalStatusLevel { healthy, warning, target, error, neutral }

Color operationalStatusColor(
  BuildContext context,
  OperationalStatusLevel level,
) {
  final isDark = Theme.of(context).brightness == Brightness.dark;
  return switch (level) {
    OperationalStatusLevel.healthy =>
      isDark ? const Color(0xFF4ADE80) : const Color(0xFF15803D),
    OperationalStatusLevel.warning =>
      isDark ? const Color(0xFFFBBF24) : const Color(0xFFB45309),
    OperationalStatusLevel.target =>
      isDark ? const Color(0xFFFB923C) : const Color(0xFFC2410C),
    OperationalStatusLevel.error =>
      isDark ? const Color(0xFFF87171) : const Color(0xFFB91C1C),
    OperationalStatusLevel.neutral =>
      isDark ? const Color(0xFF94A3B8) : const Color(0xFF475569),
  };
}

class StatusBadge extends StatelessWidget {
  const StatusBadge({
    super.key,
    required this.label,
    required this.icon,
    required this.level,
    this.compact = false,
  });

  final String label;
  final IconData icon;
  final OperationalStatusLevel level;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final color = operationalStatusColor(context, level);
    return Semantics(
      label: label,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: compact ? 8 : 10,
          vertical: compact ? 5 : 7,
        ),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.11),
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: color.withValues(alpha: 0.30)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: compact ? 14 : 16, color: color),
            const SizedBox(width: 5),
            Flexible(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: color,
                  fontSize: compact ? 12 : 13,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
