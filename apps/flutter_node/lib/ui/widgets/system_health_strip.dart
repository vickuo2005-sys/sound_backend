import 'package:flutter/material.dart';

import 'status_badge.dart';

class HealthStatusItem {
  const HealthStatusItem({
    required this.label,
    required this.detail,
    required this.icon,
    required this.level,
  });

  final String label;
  final String detail;
  final IconData icon;
  final OperationalStatusLevel level;
}

class SystemHealthStrip extends StatelessWidget {
  const SystemHealthStrip({super.key, required this.items, this.onTap});

  final List<HealthStatusItem> items;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      button: onTap != null,
      label: '系統健康狀態',
      child: Card(
        key: const ValueKey('system-health-strip'),
        clipBehavior: Clip.antiAlias,
        color: scheme.surfaceContainerLow,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 7),
            child: Row(
              children: [
                for (var index = 0; index < items.length; index++) ...[
                  Expanded(child: _HealthCell(item: items[index])),
                  if (index < items.length - 1)
                    Container(
                      width: 1,
                      height: 38,
                      color: scheme.outlineVariant,
                    ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _HealthCell extends StatelessWidget {
  const _HealthCell({required this.item});

  final HealthStatusItem item;

  @override
  Widget build(BuildContext context) {
    final color = operationalStatusColor(context, item.level);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 3),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(item.icon, size: 14, color: color),
              const SizedBox(width: 3),
              Flexible(
                child: Text(
                  item.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            item.detail,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}
