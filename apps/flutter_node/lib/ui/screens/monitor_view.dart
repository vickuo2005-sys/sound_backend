import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import '../models/event_view_data.dart';
import '../models/sound_level_reading.dart';
import '../widgets/classification_card.dart';
import '../widgets/latest_event_card.dart';
import '../widgets/live_detection_card.dart';
import '../widgets/monitor_primary_action.dart';
import '../widgets/node_identity_header.dart';
import '../widgets/status_badge.dart';
import '../widgets/system_health_strip.dart';

class MonitorView extends StatelessWidget {
  const MonitorView({
    super.key,
    required this.deviceId,
    required this.statusLabel,
    required this.statusIcon,
    required this.statusLevel,
    required this.healthItems,
    required this.isListening,
    required this.listeningTime,
    required this.soundLevel,
    required this.classificationLabel,
    required this.classificationConfidence,
    required this.aircraftProbability,
    required this.latestEvent,
    required this.onOpenSystem,
    required this.onOpenEvents,
    required this.onToggleListening,
  });

  final String deviceId;
  final String statusLabel;
  final IconData statusIcon;
  final OperationalStatusLevel statusLevel;
  final List<HealthStatusItem> healthItems;
  final bool isListening;
  final String listeningTime;
  final ValueListenable<SoundLevelReading> soundLevel;
  final String classificationLabel;
  final double? classificationConfidence;
  final double? aircraftProbability;
  final EventViewData? latestEvent;
  final VoidCallback onOpenSystem;
  final VoidCallback onOpenEvents;
  final VoidCallback onToggleListening;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: Scrollbar(
            child: ListView(
              key: const PageStorageKey('monitor-scroll'),
              padding: const EdgeInsets.fromLTRB(12, 6, 12, 10),
              children: [
                NodeIdentityHeader(
                  deviceId: deviceId,
                  statusLabel: statusLabel,
                  statusIcon: statusIcon,
                  statusLevel: statusLevel,
                ),
                const SizedBox(height: 8),
                LiveDetectionCard(
                  isListening: isListening,
                  listeningTime: listeningTime,
                  soundLevel: soundLevel,
                ),
                const SizedBox(height: 8),
                ClassificationCard(
                  label: classificationLabel,
                  confidence: classificationConfidence,
                  aircraftProbability: aircraftProbability,
                ),
                const SizedBox(height: 8),
                SystemHealthStrip(items: healthItems, onTap: onOpenSystem),
                const SizedBox(height: 8),
                LatestEventCard(event: latestEvent, onTap: onOpenEvents),
              ],
            ),
          ),
        ),
        MonitorPrimaryAction(
          isListening: isListening,
          onPressed: onToggleListening,
        ),
      ],
    );
  }
}
