class SoundLevelReading {
  const SoundLevelReading({required this.rms, this.estimatedDb});

  final double rms;
  final double? estimatedDb;
}
