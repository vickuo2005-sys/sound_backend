import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:path/path.dart' as path;
import 'package:sqflite/sqflite.dart';

import 'observation_shadow.dart';

enum ObservationQueueState {
  pending('PENDING'),
  inFlight('IN_FLIGHT'),
  retryWait('RETRY_WAIT'),
  completed('COMPLETED'),
  expired('EXPIRED'),
  failedPermanent('FAILED_PERMANENT');

  const ObservationQueueState(this.storageValue);
  final String storageValue;

  static ObservationQueueState fromStorage(String value) {
    return values.firstWhere(
      (state) => state.storageValue == value,
      orElse: () => ObservationQueueState.pending,
    );
  }
}

class ObservationQueuePolicy {
  const ObservationQueuePolicy({
    this.maxEntries = 10000,
    this.maxBytes = 25 * 1024 * 1024,
    this.maxAge = const Duration(hours: 6),
    this.maxDrainBatch = 500,
    this.retryDelays = const <Duration>[
      Duration(seconds: 1),
      Duration(seconds: 2),
      Duration(seconds: 4),
      Duration(seconds: 8),
      Duration(seconds: 15),
      Duration(seconds: 30),
      Duration(seconds: 60),
    ],
    this.jitterRatio = 0.20,
  });

  final int maxEntries;
  final int maxBytes;
  final Duration maxAge;
  final int maxDrainBatch;
  final List<Duration> retryDelays;
  final double jitterRatio;
}

class ObservationQueueRecord {
  const ObservationQueueRecord({
    required this.observationId,
    required this.deviceId,
    required this.processSessionId,
    required this.sequence,
    required this.observedAt,
    required this.eventTimeMs,
    required this.payload,
    required this.payloadBytes,
    required this.createdAtMs,
    required this.attemptCount,
    required this.lastAttemptAtMs,
    required this.nextRetryAtMs,
    required this.state,
    required this.lastError,
    required this.traceId,
    required this.schemaVersion,
  });

  final String observationId;
  final String deviceId;
  final String processSessionId;
  final int sequence;
  final String observedAt;
  final int eventTimeMs;
  final Map<String, dynamic> payload;
  final int payloadBytes;
  final int createdAtMs;
  final int attemptCount;
  final int? lastAttemptAtMs;
  final int nextRetryAtMs;
  final ObservationQueueState state;
  final String? lastError;
  final String traceId;
  final int schemaVersion;

  static ObservationQueueRecord fromRow(Map<String, Object?> row) {
    final decoded = jsonDecode(row['payload_json']! as String);
    return ObservationQueueRecord(
      observationId: row['observation_id']! as String,
      deviceId: row['device_id']! as String,
      processSessionId: row['process_session_id']! as String,
      sequence: row['sequence']! as int,
      observedAt: row['observed_at']! as String,
      eventTimeMs: row['event_time_ms']! as int,
      payload: Map<String, dynamic>.from(decoded as Map),
      payloadBytes: row['payload_bytes']! as int,
      createdAtMs: row['created_at_ms']! as int,
      attemptCount: row['attempt_count']! as int,
      lastAttemptAtMs: row['last_attempt_at_ms'] as int?,
      nextRetryAtMs: row['next_retry_at_ms']! as int,
      state: ObservationQueueState.fromStorage(row['status']! as String),
      lastError: row['last_error'] as String?,
      traceId: row['trace_id']! as String,
      schemaVersion: row['schema_version']! as int,
    );
  }
}

class ObservationQueueEnqueueResult {
  const ObservationQueueEnqueueResult({
    required this.inserted,
    required this.retained,
    required this.expiredCount,
    required this.overflowCount,
  });

  final bool inserted;
  final bool retained;
  final int expiredCount;
  final int overflowCount;
}

class ObservationQueueSnapshot {
  const ObservationQueueSnapshot({
    required this.depth,
    required this.bytes,
    required this.queuedTotal,
    required this.uploadAttemptTotal,
    required this.uploadSuccessTotal,
    required this.uploadFailureTotal,
    required this.retryTotal,
    required this.retrySuccessTotal,
    required this.retryFailureTotal,
    required this.expiredTotal,
    required this.overflowTotal,
    required this.recoveredAfterRestartTotal,
    required this.permanentFailureTotal,
    required this.oldestPendingAgeMs,
    required this.retryDelayMs,
  });

  final int depth;
  final int bytes;
  final int queuedTotal;
  final int uploadAttemptTotal;
  final int uploadSuccessTotal;
  final int uploadFailureTotal;
  final int retryTotal;
  final int retrySuccessTotal;
  final int retryFailureTotal;
  final int expiredTotal;
  final int overflowTotal;
  final int recoveredAfterRestartTotal;
  final int permanentFailureTotal;
  final int? oldestPendingAgeMs;
  final int? retryDelayMs;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'observation_queue_depth': depth,
    'observation_queue_bytes': bytes,
    'observation_queued_total': queuedTotal,
    'observation_upload_attempt_total': uploadAttemptTotal,
    'observation_upload_success_total': uploadSuccessTotal,
    'observation_upload_failure_total': uploadFailureTotal,
    'observation_retry_total': retryTotal,
    'observation_retry_success_total': retrySuccessTotal,
    'observation_retry_failure_total': retryFailureTotal,
    'observation_expired_total': expiredTotal,
    'observation_overflow_total': overflowTotal,
    'observation_recovered_after_restart_total': recoveredAfterRestartTotal,
    'persisted_from_previous_process_total': recoveredAfterRestartTotal,
    'observation_failed_permanent_total': permanentFailureTotal,
    'oldest_pending_age_ms': oldestPendingAgeMs,
    'retry_delay_ms': retryDelayMs,
  };
}

abstract class ObservationQueueStore {
  Future<void> initialize();

  Future<ObservationQueueEnqueueResult> enqueue(
    Map<String, dynamic> payload, {
    required int nowMs,
    required ObservationQueuePolicy policy,
  });

  Future<int> recoverInFlight({
    required int nowMs,
    String? currentProcessSessionId,
  });

  Future<int> makeRetriesDue({required int nowMs});

  Future<int> discardExpired({required int nowMs, required Duration maxAge});

  Future<ObservationQueueRecord?> claimNextDue({required int nowMs});

  Future<void> markRetryWait(
    String observationId, {
    required int nextRetryAtMs,
    required String error,
  });

  Future<void> markCompleted(String observationId);

  Future<void> markPermanentFailure(
    String observationId, {
    required String error,
  });

  Future<void> incrementMetric(String key, {int delta = 1});

  Future<void> setMetric(String key, int value);

  Future<int?> nextDueAtMs();

  Future<ObservationQueueSnapshot> snapshot({required int nowMs});

  Future<List<ObservationQueueRecord>> records();

  Future<void> close();
}

class ObservationSqliteStore implements ObservationQueueStore {
  ObservationSqliteStore({
    this.databasePath,
    DatabaseFactory? databaseFactoryOverride,
  }) : _databaseFactory = databaseFactoryOverride ?? databaseFactory;

  final String? databasePath;
  final DatabaseFactory _databaseFactory;
  Future<Database>? _databaseFuture;

  static const String _recordsTable = 'observation_retry_queue';
  static const String _metricsTable = 'observation_retry_metrics';
  static const Set<String> _activeStates = <String>{
    'PENDING',
    'IN_FLIGHT',
    'RETRY_WAIT',
  };

  Future<Database> get _database => _databaseFuture ??= _open();

  Future<Database> _open() async {
    final resolvedPath =
        databasePath ??
        path.join(await getDatabasesPath(), 'observation_retry_queue_v1.db');
    return _databaseFactory.openDatabase(
      resolvedPath,
      options: OpenDatabaseOptions(
        version: 1,
        onCreate: (database, _) async {
          await database.execute('''
CREATE TABLE $_recordsTable (
  observation_id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  process_session_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  observed_at TEXT NOT NULL,
  event_time_ms INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  payload_bytes INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  last_attempt_at_ms INTEGER,
  next_retry_at_ms INTEGER NOT NULL,
  status TEXT NOT NULL,
  last_error TEXT,
  trace_id TEXT NOT NULL,
  schema_version INTEGER NOT NULL
)
''');
          await database.execute('''
CREATE INDEX observation_retry_due_idx
ON $_recordsTable(status, next_retry_at_ms, created_at_ms, sequence)
''');
          await database.execute('''
CREATE INDEX observation_retry_event_time_idx
ON $_recordsTable(device_id, process_session_id, sequence, event_time_ms)
''');
          await database.execute('''
CREATE TABLE $_metricsTable (
  metric_key TEXT PRIMARY KEY,
  metric_value INTEGER NOT NULL
)
''');
        },
      ),
    );
  }

  @override
  Future<void> initialize() async {
    await _database;
  }

  @override
  Future<ObservationQueueEnqueueResult> enqueue(
    Map<String, dynamic> payload, {
    required int nowMs,
    required ObservationQueuePolicy policy,
  }) async {
    final observationId = payload['observation_id']?.toString() ?? '';
    final deviceId = payload['device_id']?.toString() ?? '';
    final processSessionId = payload['process_session_id']?.toString() ?? '';
    final observedAt = payload['observed_at']?.toString() ?? '';
    final traceId = payload['trace_id']?.toString() ?? observationId;
    final sequence = _asInt(payload['sequence']);
    final eventTimeMs = _asInt(payload['event_time_ms']);
    final schemaVersion = _asInt(payload['schema_version'], fallback: 1);
    if (observationId.isEmpty ||
        deviceId.isEmpty ||
        processSessionId.isEmpty ||
        observedAt.isEmpty ||
        sequence < 1 ||
        eventTimeMs < 1) {
      throw ArgumentError('Invalid observation queue payload');
    }
    final payloadJson = jsonEncode(payload);
    final payloadBytes = utf8.encode(payloadJson).length;
    final database = await _database;
    return database.transaction((transaction) async {
      final expired = await _discardExpiredTransaction(
        transaction,
        nowMs: nowMs,
        maxAge: policy.maxAge,
      );
      final inserted =
          await transaction.insert(_recordsTable, <String, Object?>{
            'observation_id': observationId,
            'device_id': deviceId,
            'process_session_id': processSessionId,
            'sequence': sequence,
            'observed_at': observedAt,
            'event_time_ms': eventTimeMs,
            'payload_json': payloadJson,
            'payload_bytes': payloadBytes,
            'created_at_ms': nowMs,
            'attempt_count': 0,
            'last_attempt_at_ms': null,
            'next_retry_at_ms': nowMs,
            'status': ObservationQueueState.pending.storageValue,
            'last_error': null,
            'trace_id': traceId,
            'schema_version': schemaVersion,
          }, conflictAlgorithm: ConflictAlgorithm.ignore) !=
          0;
      if (inserted) {
        await _incrementMetricTransaction(
          transaction,
          'observation_queued_total',
          1,
        );
      }
      final overflow = await _enforceBoundsTransaction(
        transaction,
        policy: policy,
      );
      final retained =
          Sqflite.firstIntValue(
            await transaction.rawQuery(
              'SELECT COUNT(*) FROM $_recordsTable WHERE observation_id = ?',
              <Object?>[observationId],
            ),
          ) ==
          1;
      return ObservationQueueEnqueueResult(
        inserted: inserted,
        retained: retained,
        expiredCount: expired,
        overflowCount: overflow,
      );
    });
  }

  @override
  Future<int> recoverInFlight({
    required int nowMs,
    String? currentProcessSessionId,
  }) async {
    final database = await _database;
    return database.transaction((transaction) async {
      final recoveredInFlight = await transaction.update(
        _recordsTable,
        <String, Object?>{
          'status': ObservationQueueState.retryWait.storageValue,
          'next_retry_at_ms': nowMs,
          'last_error': 'recovered_after_restart',
        },
        where: 'status = ?',
        whereArgs: <Object?>[ObservationQueueState.inFlight.storageValue],
      );
      var recovered = recoveredInFlight;
      if (currentProcessSessionId != null &&
          currentProcessSessionId.isNotEmpty) {
        final placeholders = List<String>.filled(
          _activeStates.length,
          '?',
        ).join(',');
        recovered =
            Sqflite.firstIntValue(
              await transaction.rawQuery(
                'SELECT COUNT(*) FROM $_recordsTable '
                'WHERE status IN ($placeholders) AND process_session_id <> ?',
                <Object?>[..._activeStates, currentProcessSessionId],
              ),
            ) ??
            0;
      }
      if (recovered > 0) {
        await _incrementMetricTransaction(
          transaction,
          'observation_recovered_after_restart_total',
          recovered,
        );
      }
      return recovered;
    });
  }

  @override
  Future<int> makeRetriesDue({required int nowMs}) async {
    final database = await _database;
    return database.update(
      _recordsTable,
      <String, Object?>{'next_retry_at_ms': nowMs},
      where: 'status = ? AND next_retry_at_ms > ?',
      whereArgs: <Object?>[ObservationQueueState.retryWait.storageValue, nowMs],
    );
  }

  @override
  Future<int> discardExpired({
    required int nowMs,
    required Duration maxAge,
  }) async {
    final database = await _database;
    return database.transaction(
      (transaction) =>
          _discardExpiredTransaction(transaction, nowMs: nowMs, maxAge: maxAge),
    );
  }

  Future<int> _discardExpiredTransaction(
    DatabaseExecutor executor, {
    required int nowMs,
    required Duration maxAge,
  }) async {
    final cutoff = nowMs - max(1, maxAge.inMilliseconds);
    final expired = await executor.delete(
      _recordsTable,
      where: 'created_at_ms <= ?',
      whereArgs: <Object?>[cutoff],
    );
    if (expired > 0) {
      await _incrementMetricTransaction(
        executor,
        'observation_expired_total',
        expired,
      );
    }
    return expired;
  }

  Future<int> _enforceBoundsTransaction(
    DatabaseExecutor executor, {
    required ObservationQueuePolicy policy,
  }) async {
    var overflow = 0;
    while (true) {
      final totals = (await executor.rawQuery(
        'SELECT COUNT(*) AS item_count, '
        'COALESCE(SUM(payload_bytes), 0) AS byte_count FROM $_recordsTable',
      )).first;
      final count = _asInt(totals['item_count']);
      final bytes = _asInt(totals['byte_count']);
      if (count <= max(1, policy.maxEntries) &&
          bytes <= max(1, policy.maxBytes)) {
        break;
      }
      final candidates = await executor.rawQuery('''
SELECT observation_id FROM $_recordsTable
ORDER BY CASE status WHEN 'FAILED_PERMANENT' THEN 0 ELSE 1 END,
         created_at_ms ASC,
         event_time_ms ASC,
         sequence ASC
LIMIT 1
''');
      if (candidates.isEmpty) break;
      overflow += await executor.delete(
        _recordsTable,
        where: 'observation_id = ?',
        whereArgs: <Object?>[candidates.first['observation_id']],
      );
    }
    if (overflow > 0) {
      await _incrementMetricTransaction(
        executor,
        'observation_overflow_total',
        overflow,
      );
    }
    return overflow;
  }

  @override
  Future<ObservationQueueRecord?> claimNextDue({required int nowMs}) async {
    final database = await _database;
    return database.transaction((transaction) async {
      final rows = await transaction.query(
        _recordsTable,
        where: 'status IN (?, ?) AND next_retry_at_ms <= ?',
        whereArgs: <Object?>[
          ObservationQueueState.pending.storageValue,
          ObservationQueueState.retryWait.storageValue,
          nowMs,
        ],
        orderBy: 'created_at_ms ASC, event_time_ms ASC, sequence ASC',
        limit: 1,
      );
      if (rows.isEmpty) return null;
      final observationId = rows.first['observation_id']! as String;
      await transaction.rawUpdate(
        'UPDATE $_recordsTable SET status = ?, attempt_count = attempt_count + 1, '
        'last_attempt_at_ms = ? WHERE observation_id = ?',
        <Object?>[
          ObservationQueueState.inFlight.storageValue,
          nowMs,
          observationId,
        ],
      );
      final claimed = await transaction.query(
        _recordsTable,
        where: 'observation_id = ?',
        whereArgs: <Object?>[observationId],
        limit: 1,
      );
      return ObservationQueueRecord.fromRow(claimed.first);
    });
  }

  @override
  Future<void> markRetryWait(
    String observationId, {
    required int nextRetryAtMs,
    required String error,
  }) async {
    final database = await _database;
    await database.update(
      _recordsTable,
      <String, Object?>{
        'status': ObservationQueueState.retryWait.storageValue,
        'next_retry_at_ms': nextRetryAtMs,
        'last_error': error,
      },
      where: 'observation_id = ?',
      whereArgs: <Object?>[observationId],
    );
  }

  @override
  Future<void> markCompleted(String observationId) async {
    final database = await _database;
    await database.delete(
      _recordsTable,
      where: 'observation_id = ?',
      whereArgs: <Object?>[observationId],
    );
  }

  @override
  Future<void> markPermanentFailure(
    String observationId, {
    required String error,
  }) async {
    final database = await _database;
    await database.update(
      _recordsTable,
      <String, Object?>{
        'status': ObservationQueueState.failedPermanent.storageValue,
        'next_retry_at_ms': 1 << 62,
        'last_error': error,
      },
      where: 'observation_id = ?',
      whereArgs: <Object?>[observationId],
    );
  }

  @override
  Future<void> incrementMetric(String key, {int delta = 1}) async {
    final database = await _database;
    await _incrementMetricTransaction(database, key, delta);
  }

  @override
  Future<void> setMetric(String key, int value) async {
    final database = await _database;
    await database.insert(_metricsTable, <String, Object?>{
      'metric_key': key,
      'metric_value': value,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> _incrementMetricTransaction(
    DatabaseExecutor executor,
    String key,
    int delta,
  ) async {
    final updated = await executor.rawUpdate(
      'UPDATE $_metricsTable SET metric_value = metric_value + ? '
      'WHERE metric_key = ?',
      <Object?>[delta, key],
    );
    if (updated == 0) {
      await executor.insert(_metricsTable, <String, Object?>{
        'metric_key': key,
        'metric_value': delta,
      });
    }
  }

  @override
  Future<int?> nextDueAtMs() async {
    final database = await _database;
    final rows = await database.rawQuery(
      'SELECT MIN(next_retry_at_ms) AS next_due FROM $_recordsTable '
      'WHERE status IN (?, ?)',
      <Object?>[
        ObservationQueueState.pending.storageValue,
        ObservationQueueState.retryWait.storageValue,
      ],
    );
    return rows.isEmpty ? null : rows.first['next_due'] as int?;
  }

  @override
  Future<ObservationQueueSnapshot> snapshot({required int nowMs}) async {
    final database = await _database;
    final placeholders = List<String>.filled(
      _activeStates.length,
      '?',
    ).join(',');
    final active = (await database.rawQuery(
      'SELECT COUNT(*) AS item_count, COALESCE(SUM(payload_bytes), 0) AS byte_count, '
      'MIN(created_at_ms) AS oldest_created_at FROM $_recordsTable '
      'WHERE status IN ($placeholders)',
      _activeStates.toList(growable: false),
    )).first;
    final metricRows = await database.query(_metricsTable);
    final metrics = <String, int>{
      for (final row in metricRows)
        row['metric_key']! as String: row['metric_value']! as int,
    };
    final oldestCreatedAt = active['oldest_created_at'] as int?;
    return ObservationQueueSnapshot(
      depth: _asInt(active['item_count']),
      bytes: _asInt(active['byte_count']),
      queuedTotal: metrics['observation_queued_total'] ?? 0,
      uploadAttemptTotal: metrics['observation_upload_attempt_total'] ?? 0,
      uploadSuccessTotal: metrics['observation_upload_success_total'] ?? 0,
      uploadFailureTotal: metrics['observation_upload_failure_total'] ?? 0,
      retryTotal: metrics['observation_retry_total'] ?? 0,
      retrySuccessTotal: metrics['observation_retry_success_total'] ?? 0,
      retryFailureTotal: metrics['observation_retry_failure_total'] ?? 0,
      expiredTotal: metrics['observation_expired_total'] ?? 0,
      overflowTotal: metrics['observation_overflow_total'] ?? 0,
      recoveredAfterRestartTotal:
          metrics['observation_recovered_after_restart_total'] ?? 0,
      permanentFailureTotal: metrics['observation_failed_permanent_total'] ?? 0,
      oldestPendingAgeMs: oldestCreatedAt == null
          ? null
          : max(0, nowMs - oldestCreatedAt),
      retryDelayMs: metrics['retry_delay_ms'],
    );
  }

  @override
  Future<List<ObservationQueueRecord>> records() async {
    final database = await _database;
    final rows = await database.query(
      _recordsTable,
      orderBy: 'created_at_ms ASC, event_time_ms ASC, sequence ASC',
    );
    return rows.map(ObservationQueueRecord.fromRow).toList(growable: false);
  }

  @override
  Future<void> close() async {
    final future = _databaseFuture;
    _databaseFuture = null;
    if (future != null) {
      await (await future).close();
    }
  }
}

typedef ObservationQueueUploader =
    Future<ObservationUploadResult> Function(Map<String, dynamic> payload);

class ObservationQueueAttemptEvent {
  const ObservationQueueAttemptEvent({
    required this.record,
    required this.result,
    required this.isRetry,
    required this.queue,
  });

  final ObservationQueueRecord record;
  final ObservationUploadResult result;
  final bool isRetry;
  final ObservationQueueSnapshot queue;
}

class ObservationRetryDispatcher {
  ObservationRetryDispatcher({
    required this.store,
    required this.uploader,
    this.policy = const ObservationQueuePolicy(),
    DateTime Function()? now,
    Random? random,
    this.onAttempt,
    this.onMetrics,
    this.autoDrain = true,
    this.currentProcessSessionId,
  }) : _now = now ?? DateTime.now,
       _random = random ?? Random.secure();

  final ObservationQueueStore store;
  final ObservationQueueUploader uploader;
  final ObservationQueuePolicy policy;
  final DateTime Function() _now;
  final Random _random;
  final void Function(ObservationQueueAttemptEvent event)? onAttempt;
  final void Function(String reason, ObservationQueueSnapshot snapshot)?
  onMetrics;
  final bool autoDrain;
  final String? currentProcessSessionId;

  Timer? _timer;
  bool _initialized = false;
  bool _draining = false;
  bool _closed = false;
  int _networkRetryNotBeforeMs = 0;

  int get _nowMs => _now().millisecondsSinceEpoch;

  Future<void> initialize() async {
    if (_initialized) return;
    await store.initialize();
    final nowMs = _nowMs;
    final recovered = await store.recoverInFlight(
      nowMs: nowMs,
      currentProcessSessionId: currentProcessSessionId,
    );
    final expired = await store.discardExpired(
      nowMs: nowMs,
      maxAge: policy.maxAge,
    );
    _initialized = true;
    await _emitMetrics(
      recovered > 0
          ? 'recovered_after_restart'
          : expired > 0
          ? 'expired_on_start'
          : 'initialized',
    );
  }

  Future<ObservationQueueEnqueueResult> enqueuePayload(
    Map<String, dynamic> payload,
  ) async {
    await initialize();
    final result = await store.enqueue(payload, nowMs: _nowMs, policy: policy);
    await _emitMetrics(result.overflowCount > 0 ? 'overflow' : 'queued');
    wake();
    return result;
  }

  void wake({bool forceNetworkProbe = false}) {
    if (_closed || !_initialized || !autoDrain) return;
    if (forceNetworkProbe) {
      _networkRetryNotBeforeMs = 0;
    }
    _timer?.cancel();
    _timer = null;
    unawaited(drainNow(forceNetworkProbe: forceNetworkProbe));
  }

  Future<void> drainNow({bool forceNetworkProbe = false}) async {
    if (_closed) return;
    if (!_initialized) await initialize();
    if (_draining) return;
    if (forceNetworkProbe) {
      _networkRetryNotBeforeMs = 0;
      await store.makeRetriesDue(nowMs: _nowMs);
    }
    _draining = true;
    try {
      final expired = await store.discardExpired(
        nowMs: _nowMs,
        maxAge: policy.maxAge,
      );
      if (expired > 0) await _emitMetrics('expired');
      if (_nowMs < _networkRetryNotBeforeMs) return;

      for (
        var processed = 0;
        processed < max(1, policy.maxDrainBatch);
        processed++
      ) {
        final record = await store.claimNextDue(nowMs: _nowMs);
        if (record == null) break;
        final isRetry = record.attemptCount > 1;
        await store.incrementMetric('observation_upload_attempt_total');
        if (isRetry) await store.incrementMetric('observation_retry_total');

        ObservationUploadResult result;
        try {
          result = await uploader(record.payload);
        } catch (error) {
          result = ObservationUploadResult(
            status: ObservationUploadStatus.failed,
            payloadBytes: record.payloadBytes,
            estimatedRequestBytes: record.payloadBytes,
            httpDurationMs: 0,
            error: 'uploader_${error.runtimeType}',
          );
        }

        if (result.status == ObservationUploadStatus.uploaded) {
          await store.markCompleted(record.observationId);
          await store.incrementMetric('observation_upload_success_total');
          if (isRetry) {
            await store.incrementMetric('observation_retry_success_total');
          }
          await _emitAttempt(record, result, isRetry);
          continue;
        }

        await store.incrementMetric('observation_upload_failure_total');
        if (isRetry) {
          await store.incrementMetric('observation_retry_failure_total');
        }
        final error =
            result.error ??
            (result.statusCode == null
                ? 'network_unavailable'
                : 'http_${result.statusCode}');
        if (_isPermanent(result.statusCode)) {
          await store.markPermanentFailure(record.observationId, error: error);
          await store.incrementMetric('observation_failed_permanent_total');
          await _emitAttempt(record, result, isRetry);
          continue;
        }

        final delayMs = _retryDelayMs(record.attemptCount);
        final nextRetryAtMs = _nowMs + delayMs;
        await store.markRetryWait(
          record.observationId,
          nextRetryAtMs: nextRetryAtMs,
          error: error,
        );
        await store.setMetric('retry_delay_ms', delayMs);
        _networkRetryNotBeforeMs = nextRetryAtMs;
        await _emitAttempt(record, result, isRetry);
        break;
      }
    } finally {
      _draining = false;
      if (autoDrain && !_closed) await _scheduleNext();
    }
  }

  int _retryDelayMs(int attemptCount) {
    final delays = policy.retryDelays.isEmpty
        ? const <Duration>[Duration(seconds: 60)]
        : policy.retryDelays;
    final index = min(max(1, attemptCount) - 1, delays.length - 1);
    final baseMs = max(1, delays[index].inMilliseconds);
    final ratio = policy.jitterRatio.clamp(0.0, 1.0);
    final jitter = ((2 * _random.nextDouble() - 1) * baseMs * ratio).round();
    return max(1, baseMs + jitter);
  }

  bool _isPermanent(int? statusCode) {
    if (statusCode == null) return false;
    return statusCode >= 400 &&
        statusCode < 500 &&
        statusCode != 408 &&
        statusCode != 409 &&
        statusCode != 425 &&
        statusCode != 429;
  }

  Future<void> _emitAttempt(
    ObservationQueueRecord record,
    ObservationUploadResult result,
    bool isRetry,
  ) async {
    final snapshot = await store.snapshot(nowMs: _nowMs);
    onAttempt?.call(
      ObservationQueueAttemptEvent(
        record: record,
        result: result,
        isRetry: isRetry,
        queue: snapshot,
      ),
    );
    onMetrics?.call('upload_${result.status.name}', snapshot);
  }

  Future<void> _emitMetrics(String reason) async {
    final snapshot = await store.snapshot(nowMs: _nowMs);
    onMetrics?.call(reason, snapshot);
  }

  Future<void> _scheduleNext() async {
    _timer?.cancel();
    _timer = null;
    final dueAt = await store.nextDueAtMs();
    if (dueAt == null || _closed) return;
    final target = max(dueAt, _networkRetryNotBeforeMs);
    final delayMs = max(1, target - _nowMs);
    _timer = Timer(Duration(milliseconds: delayMs), wake);
  }

  Future<ObservationQueueSnapshot> snapshot() async {
    await initialize();
    return store.snapshot(nowMs: _nowMs);
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    _timer?.cancel();
    _timer = null;
    await store.close();
  }
}

int _asInt(Object? value, {int fallback = 0}) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}
