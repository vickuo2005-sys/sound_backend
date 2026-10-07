import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:shared_preferences/shared_preferences.dart';

class PendingEventUpload {
  const PendingEventUpload({
    required this.eventId,
    required this.eventJson,
    required this.createdAtMs,
    required this.nextAttemptAtMs,
    required this.attempts,
    required this.metadataUploaded,
    required this.lastError,
    required this.state,
  });

  final String eventId;
  final Map<String, dynamic> eventJson;
  final int createdAtMs;
  final int nextAttemptAtMs;
  final int attempts;
  final bool metadataUploaded;
  final String? lastError;
  final String state;

  bool isDue(int nowMs) => state != 'completed' && nextAttemptAtMs <= nowMs;

  PendingEventUpload copyWith({
    Map<String, dynamic>? eventJson,
    int? nextAttemptAtMs,
    int? attempts,
    bool? metadataUploaded,
    String? lastError,
    String? state,
  }) {
    return PendingEventUpload(
      eventId: eventId,
      eventJson: eventJson ?? this.eventJson,
      createdAtMs: createdAtMs,
      nextAttemptAtMs: nextAttemptAtMs ?? this.nextAttemptAtMs,
      attempts: attempts ?? this.attempts,
      metadataUploaded: metadataUploaded ?? this.metadataUploaded,
      lastError: lastError,
      state: state ?? this.state,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'event_id': eventId,
      'event_json': eventJson,
      'created_at_ms': createdAtMs,
      'next_attempt_at_ms': nextAttemptAtMs,
      'attempts': attempts,
      'metadata_uploaded': metadataUploaded,
      'last_error': lastError,
      'state': state,
    };
  }

  static PendingEventUpload? fromJson(dynamic raw) {
    if (raw is! Map) return null;
    final eventId = raw['event_id']?.toString() ?? '';
    final eventJson = raw['event_json'];
    if (eventId.isEmpty || eventJson is! Map) return null;

    return PendingEventUpload(
      eventId: eventId,
      eventJson: Map<String, dynamic>.from(eventJson),
      createdAtMs: _intValue(raw['created_at_ms']),
      nextAttemptAtMs: _intValue(raw['next_attempt_at_ms']),
      attempts: _intValue(raw['attempts']),
      metadataUploaded: raw['metadata_uploaded'] == true,
      lastError: raw['last_error']?.toString(),
      state: raw['state']?.toString() ?? 'metadata_pending',
    );
  }

  static int _intValue(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }
}

class EventUploadQueue {
  EventUploadQueue({
    this.preferenceKey = 'pending_event_upload_queue_v1',
    this.maxPendingItems = 24,
  });

  final String preferenceKey;
  final int maxPendingItems;
  Future<void> _operationTail = Future<void>.value();

  Future<List<PendingEventUpload>> load() async {
    return _serialized(_load);
  }

  Future<List<PendingEventUpload>> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(preferenceKey);
    if (raw == null || raw.isEmpty) return <PendingEventUpload>[];

    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return <PendingEventUpload>[];
      return decoded
          .map(PendingEventUpload.fromJson)
          .whereType<PendingEventUpload>()
          .where((item) => item.state != 'completed')
          .toList();
    } catch (_) {
      return <PendingEventUpload>[];
    }
  }

  Future<void> enqueueEvent(Map<String, dynamic> eventJson) async {
    await _serialized(() async {
      await _enqueueEvent(eventJson);
    });
  }

  /// Starts the metadata request immediately while durable retry persistence
  /// proceeds in parallel. The queue is always awaited before the result is
  /// committed, so failures remain retryable and successes stay available for
  /// the background audio stage.
  Future<String> enqueueWithImmediateMetadataSend(
    Map<String, dynamic> eventJson,
    Future<String> Function() sendMetadata, {
    void Function()? onPersisted,
  }) async {
    final persistence = enqueueEvent(eventJson).whenComplete(() {
      onPersisted?.call();
    });
    String status;
    try {
      status = await sendMetadata();
    } catch (error) {
      status = 'metadata_send_error_${error.runtimeType}';
    }

    await persistence;
    final eventId = eventJson['event_id']?.toString() ?? '';
    if (eventId.isEmpty) return 'invalid_event_payload';
    if (status == 'uploaded') {
      await markMetadataUploaded(eventId);
    } else {
      await recordFailure(eventId, status);
    }
    return status;
  }

  Future<void> _enqueueEvent(Map<String, dynamic> eventJson) async {
    final eventId = eventJson['event_id']?.toString() ?? '';
    if (eventId.isEmpty) return;
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final items = await _load();
    final index = items.indexWhere((item) => item.eventId == eventId);
    final next = index == -1
        ? PendingEventUpload(
            eventId: eventId,
            eventJson: eventJson,
            createdAtMs: nowMs,
            nextAttemptAtMs: nowMs,
            attempts: 0,
            metadataUploaded: false,
            lastError: null,
            state: 'metadata_pending',
          )
        : items[index].copyWith(
            eventJson: eventJson,
            state: items[index].state,
          );
    if (index == -1) {
      items.add(next);
    } else {
      items[index] = next;
    }
    items.sort((a, b) => a.createdAtMs.compareTo(b.createdAtMs));
    while (items.length > max(1, maxPendingItems)) {
      items.removeAt(0);
    }
    await _save(items);
  }

  Future<List<PendingEventUpload>> dueItems({int limit = 3}) async {
    return _serialized(() async {
      final nowMs = DateTime.now().millisecondsSinceEpoch;
      final items = await _load();
      final due = items.where((item) => item.isDue(nowMs)).toList()
        ..sort((a, b) {
          final metadataPriority = (a.metadataUploaded ? 1 : 0).compareTo(
            b.metadataUploaded ? 1 : 0,
          );
          if (metadataPriority != 0) return metadataPriority;
          return a.createdAtMs.compareTo(b.createdAtMs);
        });
      return due.take(max(1, limit)).toList(growable: false);
    });
  }

  Future<List<PendingEventUpload>> discardExpired({
    int metadataMaxAgeMs = 30000,
    int audioMaxAgeMs = 300000,
    int? nowMs,
  }) async {
    return _serialized(() async {
      final effectiveNowMs = nowMs ?? DateTime.now().millisecondsSinceEpoch;
      final items = await _load();
      final expired = <PendingEventUpload>[];
      final retained = <PendingEventUpload>[];

      for (final item in items) {
        final maxAgeMs = item.metadataUploaded
            ? max(1, audioMaxAgeMs)
            : max(1, metadataMaxAgeMs);
        final invalidCreatedAt = item.createdAtMs <= 0;
        final ageMs = effectiveNowMs - item.createdAtMs;
        if (invalidCreatedAt || ageMs > maxAgeMs) {
          expired.add(item);
        } else {
          retained.add(item);
        }
      }

      if (expired.isNotEmpty) {
        await _save(retained);
      }
      return expired;
    });
  }

  Future<void> markMetadataUploaded(String eventId) async {
    await _serialized(() async {
      await _update(eventId, (item) {
        return item.copyWith(
          metadataUploaded: true,
          state: 'audio_pending',
          lastError: null,
        );
      });
    });
  }

  Future<void> markCompleted(String eventId) async {
    await _serialized(() async {
      final items = await _load();
      items.removeWhere((item) => item.eventId == eventId);
      await _save(items);
    });
  }

  Future<void> markPermanentFailure(String eventId, String error) async {
    await _serialized(() async {
      await _update(eventId, (item) {
        return item.copyWith(
          state: 'permanent_failure',
          lastError: error,
          nextAttemptAtMs: 1 << 62,
        );
      });
    });
  }

  Future<void> recordFailure(String eventId, String error) async {
    await _serialized(() async {
      await _update(eventId, (item) {
        final nextAttempts = item.attempts + 1;
        final backoffSeconds = min(3600, 10 * (1 << min(nextAttempts, 8)));
        final jitterMs = Random().nextInt(1200);
        return item.copyWith(
          attempts: nextAttempts,
          state: item.metadataUploaded
              ? 'audio_retry_wait'
              : 'metadata_retry_wait',
          lastError: error,
          nextAttemptAtMs:
              DateTime.now().millisecondsSinceEpoch +
              backoffSeconds * 1000 +
              jitterMs,
        );
      });
    });
  }

  Future<void> _update(
    String eventId,
    PendingEventUpload Function(PendingEventUpload item) update,
  ) async {
    final items = await _load();
    final index = items.indexWhere((item) => item.eventId == eventId);
    if (index == -1) return;
    items[index] = update(items[index]);
    await _save(items);
  }

  Future<void> _save(List<PendingEventUpload> items) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      preferenceKey,
      jsonEncode(items.map((item) => item.toJson()).toList()),
    );
  }

  Future<T> _serialized<T>(Future<T> Function() operation) {
    final completer = Completer<T>();
    _operationTail = _operationTail.then((_) async {
      try {
        completer.complete(await operation());
      } catch (error, stackTrace) {
        completer.completeError(error, stackTrace);
      }
    });
    return completer.future;
  }
}
