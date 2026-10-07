import 'package:flutter/material.dart';

import '../widgets/status_badge.dart';

class ClassificationPresentation {
  const ClassificationPresentation({
    required this.rawLabel,
    required this.englishLabel,
    required this.localizedLabel,
    required this.contextLabel,
    required this.icon,
    required this.level,
    required this.isTarget,
  });

  final String rawLabel;
  final String englishLabel;
  final String localizedLabel;
  final String contextLabel;
  final IconData icon;
  final OperationalStatusLevel level;
  final bool isTarget;
}

ClassificationPresentation classificationPresentationFor(
  String rawLabel, {
  bool? targetOverride,
}) {
  final normalized = rawLabel.trim().toLowerCase().replaceAll(' ', '_');
  final base = switch (normalized) {
    'airplane' || 'aircraft' => const ClassificationPresentation(
      rawLabel: 'Airplane',
      englishLabel: 'Airplane',
      localizedLabel: '航空器聲音',
      contextLabel: '注意目標事件',
      icon: Icons.flight,
      level: OperationalStatusLevel.warning,
      isTarget: true,
    ),
    'car' => const ClassificationPresentation(
      rawLabel: 'Car',
      englishLabel: 'Car',
      localizedLabel: '車輛聲音',
      contextLabel: '環境事件',
      icon: Icons.directions_car,
      level: OperationalStatusLevel.neutral,
      isTarget: false,
    ),
    'drone' => const ClassificationPresentation(
      rawLabel: 'Drone',
      englishLabel: 'Drone',
      localizedLabel: '無人機聲音',
      contextLabel: '高優先目標',
      icon: Icons.flight_takeoff,
      level: OperationalStatusLevel.target,
      isTarget: true,
    ),
    'electric_saw' || 'electric-saw' => const ClassificationPresentation(
      rawLabel: 'Electric_saw',
      englishLabel: 'Electric Saw',
      localizedLabel: '電鋸聲音',
      contextLabel: '環境事件',
      icon: Icons.carpenter,
      level: OperationalStatusLevel.neutral,
      isTarget: false,
    ),
    'rainfall' => const ClassificationPresentation(
      rawLabel: 'Rainfall',
      englishLabel: 'Rainfall',
      localizedLabel: '降雨聲音',
      contextLabel: '環境狀態',
      icon: Icons.water_drop,
      level: OperationalStatusLevel.neutral,
      isTarget: false,
    ),
    'non_aircraft' || 'other' => const ClassificationPresentation(
      rawLabel: 'non_aircraft',
      englishLabel: 'Non-target',
      localizedLabel: '非目標聲音',
      contextLabel: '環境事件',
      icon: Icons.graphic_eq,
      level: OperationalStatusLevel.neutral,
      isTarget: false,
    ),
    'ai_failed' || 'sound_event' || 'n/a' => const ClassificationPresentation(
      rawLabel: 'sound_event',
      englishLabel: 'Unknown',
      localizedLabel: '尚無可靠分類',
      contextLabel: '等待有效 AI 結果',
      icon: Icons.help_outline,
      level: OperationalStatusLevel.warning,
      isTarget: false,
    ),
    _ => ClassificationPresentation(
      rawLabel: rawLabel,
      englishLabel: rawLabel.trim().isEmpty ? 'Unknown' : rawLabel.trim(),
      localizedLabel: rawLabel.trim().isEmpty ? '尚無分類' : rawLabel.trim(),
      contextLabel: '模型輸出',
      icon: Icons.graphic_eq,
      level: OperationalStatusLevel.neutral,
      isTarget: false,
    ),
  };

  if (targetOverride == null || targetOverride == base.isTarget) return base;
  return ClassificationPresentation(
    rawLabel: base.rawLabel,
    englishLabel: base.englishLabel,
    localizedLabel: base.localizedLabel,
    contextLabel: targetOverride ? '目標事件' : base.contextLabel,
    icon: base.icon,
    level: targetOverride ? OperationalStatusLevel.target : base.level,
    isTarget: targetOverride,
  );
}
