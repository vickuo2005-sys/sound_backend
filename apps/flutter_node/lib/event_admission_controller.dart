class EventAdmissionDecision {
  const EventAdmissionDecision({
    required this.accepted,
    required this.cooldownMs,
    required this.remainingMs,
  });

  final bool accepted;
  final int cooldownMs;
  final int remainingMs;
}

class EventAdmissionController {
  EventAdmissionController({
    this.targetCooldownMs = 10000,
    this.collectionCooldownMs = 3000,
  });

  final int targetCooldownMs;
  final int collectionCooldownMs;
  final Map<String, int> _lastAcceptedAtMs = <String, int>{};

  EventAdmissionDecision evaluate({
    required String deviceId,
    required bool target,
    required int occurredAtMs,
  }) {
    final normalizedDeviceId = deviceId.trim();
    final bucket = target ? 'target' : 'collection';
    final key = '$normalizedDeviceId:$bucket';
    final cooldownMs = target ? targetCooldownMs : collectionCooldownMs;
    final lastAcceptedAtMs = _lastAcceptedAtMs[key];

    if (lastAcceptedAtMs != null) {
      final elapsedMs = occurredAtMs - lastAcceptedAtMs;
      if (elapsedMs < cooldownMs) {
        return EventAdmissionDecision(
          accepted: false,
          cooldownMs: cooldownMs,
          remainingMs: cooldownMs - elapsedMs,
        );
      }
    }

    _lastAcceptedAtMs[key] = occurredAtMs;
    return EventAdmissionDecision(
      accepted: true,
      cooldownMs: cooldownMs,
      remainingMs: 0,
    );
  }

  void reset({String? deviceId}) {
    final normalizedDeviceId = deviceId?.trim();
    if (normalizedDeviceId == null || normalizedDeviceId.isEmpty) {
      _lastAcceptedAtMs.clear();
      return;
    }

    _lastAcceptedAtMs.removeWhere(
      (key, _) => key.startsWith('$normalizedDeviceId:'),
    );
  }
}
