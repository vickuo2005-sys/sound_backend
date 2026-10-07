import 'package:flutter/material.dart';

import 'status_badge.dart';

class NodeIdentityHeader extends StatelessWidget {
  const NodeIdentityHeader({
    super.key,
    required this.deviceId,
    required this.statusLabel,
    required this.statusIcon,
    required this.statusLevel,
  });

  final String deviceId;
  final String statusLabel;
  final IconData statusIcon;
  final OperationalStatusLevel statusLevel;

  String get _shortNodeName {
    final normalized = deviceId.trim();
    if (normalized.toLowerCase().startsWith('node_')) {
      return normalized.substring(5);
    }
    return normalized;
  }

  @override
  Widget build(BuildContext context) {
    final color = operationalStatusColor(context, statusLevel);
    final scheme = Theme.of(context).colorScheme;
    return Container(
      key: const ValueKey('node-identity-header'),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(11),
              border: Border.all(color: color.withValues(alpha: 0.26)),
            ),
            child: Icon(Icons.sensors, color: color, size: 23),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Node $_shortNodeName',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 1),
                Text(
                  '專用聲音偵測節點',
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
          const SizedBox(width: 8),
          StatusBadge(
            label: statusLabel,
            icon: statusIcon,
            level: statusLevel,
            compact: true,
          ),
        ],
      ),
    );
  }
}
