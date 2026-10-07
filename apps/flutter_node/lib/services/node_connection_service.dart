import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'realtime_detection_state.dart';

enum NodeConnectionStatus {
  disconnected,
  connecting,
  authenticating,
  connected,
  degraded,
  reconnecting,
  stopped,
}

class NodeCommand {
  const NodeCommand({
    required this.commandId,
    required this.commandType,
    required this.args,
    this.idempotencyKey,
    this.expiresAtMs,
  });

  final String commandId;
  final String commandType;
  final Map<String, dynamic> args;
  final String? idempotencyKey;
  final int? expiresAtMs;
}

class NodeCommandExecutionResult {
  const NodeCommandExecutionResult({
    required this.success,
    required this.message,
  });

  final bool success;
  final String message;

  String get protocolStatus => success ? 'succeeded' : 'failed';
}

class NodeConnectionSnapshot {
  const NodeConnectionSnapshot({
    required this.status,
    required this.reconnectCount,
    this.connectionId,
    this.lastError,
  });

  final NodeConnectionStatus status;
  final int reconnectCount;
  final String? connectionId;
  final String? lastError;
}

class NodeConnectionService {
  // Survives service/page recreation within the same app process.
  static int _detectionSequence = 0;
  NodeConnectionService({
    required this.statusProvider,
    required this.onCommand,
    required this.onStateChanged,
    this.protocolVersion = 1,
    this.heartbeatInterval = const Duration(seconds: 5),
  });

  final FutureOr<Map<String, dynamic>> Function() statusProvider;
  final Future<NodeCommandExecutionResult> Function(NodeCommand command)
  onCommand;
  final void Function(NodeConnectionSnapshot snapshot) onStateChanged;
  final int protocolVersion;
  final Duration heartbeatInterval;

  WebSocket? _socket;
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;
  NodeConnectionStatus _status = NodeConnectionStatus.disconnected;
  String _backendBaseUrl = '';
  String _deviceId = '';
  String? _connectionId;
  int _reconnectCount = 0;
  int _backoffSeconds = 1;
  int _connectionSerial = 0;
  int? _activeConnectionSerial;
  bool _manuallyStopped = true;
  bool _connecting = false;
  final Set<String> _executingCommands = <String>{};
  final Map<String, NodeCommandExecutionResult> _completedCommands =
      <String, NodeCommandExecutionResult>{};

  late final RealtimeDetectionState detectionState = RealtimeDetectionState(
    nextSequence: () => ++_detectionSequence,
    send: (state) async {
      final serial = _activeConnectionSerial;
      try {
        await _sendEnvelope('status_update', {
          'detection_state': state,
        }, connectionSerial: serial);
      } catch (error) {
        if (serial != null) _handleSocketDone(serial, error: error);
        rethrow;
      }
    },
    log: (message) {
      // ignore: avoid_print
      print(message);
    },
  );

  void sendDetectionState({
    required int session,
    required bool active,
    required int observedAtMs,
    String? label,
    double? confidence,
  }) => detectionState.inference(
    session: session,
    active: active,
    observedAtMs: observedAtMs,
    label: label,
    confidence: confidence,
  );

  void stopDetection() =>
      detectionState.stop(observedAtMs: DateTime.now().millisecondsSinceEpoch);

  NodeConnectionStatus get status => _status;
  String? get connectionId => _connectionId;
  int get reconnectCount => _reconnectCount;

  void configure({required String backendBaseUrl, required String deviceId}) {
    _backendBaseUrl = backendBaseUrl.trim();
    _deviceId = deviceId.trim();
  }

  Future<void> start() async {
    if (_backendBaseUrl.isEmpty || _deviceId.isEmpty) {
      _setState(
        NodeConnectionStatus.disconnected,
        lastError: 'backend URL or device_id is empty',
      );
      return;
    }
    _manuallyStopped = false;
    await _connect();
  }

  Future<void> reconnect({
    required String backendBaseUrl,
    required String deviceId,
  }) async {
    final nextDeviceId = deviceId.trim();
    final identityChanged =
        nextDeviceId.isNotEmpty && nextDeviceId != _deviceId;
    if (identityChanged) {
      stopDetection();
      _executingCommands.clear();
      _completedCommands.clear();
      _reconnectCount = 0;
    }
    configure(backendBaseUrl: backendBaseUrl, deviceId: deviceId);
    await stop(notifyStopped: false);
    _manuallyStopped = false;
    _backoffSeconds = 1;
    await _connect();
  }

  Future<void> stop({bool notifyStopped = true}) async {
    detectionState.setConnected(false);
    _manuallyStopped = true;
    _reconnectTimer?.cancel();
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _connectionSerial++;
    _activeConnectionSerial = null;
    _connectionId = null;
    final socket = _socket;
    _socket = null;
    if (socket != null) {
      try {
        await socket.close();
      } catch (_) {
        // Best effort shutdown.
      }
    }
    if (notifyStopped) {
      _setState(NodeConnectionStatus.stopped);
    }
  }

  Future<void> sendStatusUpdate() async {
    await _sendEnvelope('status_update', await statusProvider());
  }

  Uri _webSocketUri() {
    final base = Uri.parse(_backendBaseUrl);
    final scheme = base.scheme == 'https' ? 'wss' : 'ws';
    return base.replace(
      scheme: scheme,
      path: '/ws/node/${Uri.encodeComponent(_deviceId)}',
      query: '',
    );
  }

  Future<void> _connect() async {
    if (_connecting || _manuallyStopped) return;
    _connecting = true;
    final connectionSerial = ++_connectionSerial;
    _setState(
      _reconnectCount == 0
          ? NodeConnectionStatus.connecting
          : NodeConnectionStatus.reconnecting,
    );

    try {
      final socket = await WebSocket.connect(
        _webSocketUri().toString(),
      ).timeout(const Duration(seconds: 10));
      if (_manuallyStopped || connectionSerial != _connectionSerial) {
        await socket.close();
        return;
      }
      _socket = socket;
      _activeConnectionSerial = connectionSerial;
      _setState(NodeConnectionStatus.authenticating);

      await _sendEnvelope('hello', {
        ...await statusProvider(),
        'reconnect_count': _reconnectCount,
      }, connectionSerial: connectionSerial);

      socket.listen(
        (dynamic message) {
          if (message is String) {
            unawaited(_handleTextMessage(message, connectionSerial));
          }
        },
        onDone: () => _handleSocketDone(connectionSerial),
        onError: (Object error) {
          _handleSocketDone(connectionSerial, error: error);
        },
        cancelOnError: true,
      );
    } catch (error) {
      if (connectionSerial == _connectionSerial) {
        _scheduleReconnect('connect failed: $error', connectionSerial);
      }
    } finally {
      _connecting = false;
    }
  }

  Future<void> _handleTextMessage(
    String rawMessage,
    int connectionSerial,
  ) async {
    if (connectionSerial != _activeConnectionSerial) return;
    dynamic decoded;
    try {
      decoded = jsonDecode(rawMessage);
    } catch (_) {
      return;
    }
    if (decoded is! Map<String, dynamic>) return;

    final messageType = decoded['message_type']?.toString() ?? '';
    final payload = decoded['payload'] is Map
        ? Map<String, dynamic>.from(decoded['payload'] as Map)
        : <String, dynamic>{};

    if (messageType == 'hello_ack') {
      if (connectionSerial != _activeConnectionSerial) return;
      _connectionId = payload['connection_id']?.toString();
      _backoffSeconds = 1;
      _setState(NodeConnectionStatus.connected);
      _startHeartbeat(connectionSerial);
      return;
    }

    if (messageType == 'ping' || messageType == 'request_status') {
      await _sendEnvelope(
        'status_update',
        await statusProvider(),
        connectionSerial: connectionSerial,
      );
      return;
    }

    if (messageType == 'command') {
      await _handleCommand(payload, connectionSerial);
      return;
    }
  }

  Future<void> _handleCommand(
    Map<String, dynamic> payload,
    int connectionSerial,
  ) async {
    final command = NodeCommand(
      commandId: payload['command_id']?.toString() ?? '',
      commandType: payload['command_type']?.toString() ?? '',
      idempotencyKey: payload['idempotency_key']?.toString(),
      expiresAtMs: _intOrNull(payload['expires_at_ms']),
      args: payload['args'] is Map
          ? Map<String, dynamic>.from(payload['args'] as Map)
          : <String, dynamic>{},
    );

    if (command.commandId.isEmpty || command.commandType.isEmpty) {
      await _sendEnvelope('protocol_error', {
        'error': 'invalid command payload',
      }, connectionSerial: connectionSerial);
      return;
    }

    final commandKey = command.idempotencyKey?.isNotEmpty == true
        ? command.idempotencyKey!
        : command.commandId;
    final nowMs = DateTime.now().millisecondsSinceEpoch;

    if (command.expiresAtMs != null && command.expiresAtMs! < nowMs) {
      await _sendEnvelope('command_ack', {
        'command_id': command.commandId,
        'command_type': command.commandType,
        'status': 'rejected',
        'message': 'command expired',
      }, connectionSerial: connectionSerial);
      await _sendEnvelope('command_result', {
        'command_id': command.commandId,
        'command_type': command.commandType,
        'status': 'failed',
        'error_code': 'expired',
        'error_message': 'command expired',
      }, connectionSerial: connectionSerial);
      return;
    }

    final completed = _completedCommands[commandKey];
    if (completed != null) {
      await _sendEnvelope('command_ack', {
        'command_id': command.commandId,
        'command_type': command.commandType,
        'status': 'accepted',
        'message': 'duplicate command already completed',
      }, connectionSerial: connectionSerial);
      await _sendEnvelope('command_result', {
        'command_id': command.commandId,
        'command_type': command.commandType,
        'status': completed.success ? 'success' : 'failed',
        'message': completed.message,
        'duplicate': true,
      }, connectionSerial: connectionSerial);
      return;
    }

    if (_executingCommands.contains(commandKey)) {
      await _sendEnvelope('command_ack', {
        'command_id': command.commandId,
        'command_type': command.commandType,
        'status': 'accepted',
        'message': 'command already running',
      }, connectionSerial: connectionSerial);
      await _sendEnvelope('command_result', {
        'command_id': command.commandId,
        'command_type': command.commandType,
        'status': 'running',
        'message': 'command already running',
      }, connectionSerial: connectionSerial);
      return;
    }

    await _sendEnvelope('command_ack', {
      'command_id': command.commandId,
      'command_type': command.commandType,
      'status': 'accepted',
      'message': 'command received',
    }, connectionSerial: connectionSerial);

    _executingCommands.add(commandKey);
    final result = await onCommand(command);
    _executingCommands.remove(commandKey);
    _completedCommands[commandKey] = result;
    if (_completedCommands.length > 100) {
      _completedCommands.remove(_completedCommands.keys.first);
    }

    await _sendEnvelope('command_result', {
      'command_id': command.commandId,
      'command_type': command.commandType,
      'status': result.success ? 'success' : 'failed',
      'message': result.message,
      'completed_at_ms': DateTime.now().millisecondsSinceEpoch,
    }, connectionSerial: connectionSerial);
  }

  void _startHeartbeat(int connectionSerial) {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(heartbeatInterval, (_) {
      unawaited(
        _sendEnvelope(
          'heartbeat',
          statusProvider(),
          connectionSerial: connectionSerial,
        ),
      );
    });
    unawaited(
      _sendEnvelope(
        'heartbeat',
        statusProvider(),
        connectionSerial: connectionSerial,
      ),
    );
  }

  Future<void> _sendEnvelope(
    String messageType,
    FutureOr<Map<String, dynamic>> payload, {
    int? connectionSerial,
  }) async {
    if (connectionSerial != null &&
        connectionSerial != _activeConnectionSerial) {
      return;
    }
    final socket = _socket;
    if (socket == null) return;
    final body = {
      'protocol_version': protocolVersion,
      'message_type': messageType,
      'device_id': _deviceId,
      'message_id': _randomMessageId(),
      'sent_at_ms': DateTime.now().millisecondsSinceEpoch,
      'payload': await payload,
    };
    // A reconnect can complete while an asynchronous status provider is running.
    if (!identical(socket, _socket) ||
        (connectionSerial != null &&
            connectionSerial != _activeConnectionSerial)) {
      return;
    }
    socket.add(jsonEncode(body));
  }

  void _handleSocketDone(int connectionSerial, {Object? error}) {
    if (connectionSerial != _activeConnectionSerial) return;
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _socket = null;
    _activeConnectionSerial = null;
    if (_manuallyStopped) {
      _setState(NodeConnectionStatus.stopped);
      return;
    }
    _scheduleReconnect(
      error == null ? 'socket closed' : error.toString(),
      connectionSerial,
    );
  }

  void _scheduleReconnect(String reason, int connectionSerial) {
    if (_manuallyStopped) return;
    if (connectionSerial != _connectionSerial) return;
    _socket = null;
    _activeConnectionSerial = null;
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _setState(NodeConnectionStatus.reconnecting, lastError: reason);
    _reconnectTimer?.cancel();
    final jitterMs = Random().nextInt(400);
    final delay = Duration(seconds: _backoffSeconds, milliseconds: jitterMs);
    _backoffSeconds = min(_backoffSeconds * 2, 30);
    _reconnectCount += 1;
    _reconnectTimer = Timer(delay, () {
      unawaited(_connect());
    });
  }

  void _setState(NodeConnectionStatus status, {String? lastError}) {
    _status = status;
    detectionState.setConnected(status == NodeConnectionStatus.connected);
    onStateChanged(
      NodeConnectionSnapshot(
        status: status,
        reconnectCount: _reconnectCount,
        connectionId: _connectionId,
        lastError: lastError,
      ),
    );
  }

  String _randomMessageId() {
    final now = DateTime.now().microsecondsSinceEpoch;
    final suffix = Random().nextInt(1 << 32).toRadixString(16);
    return '$now-$suffix';
  }

  int? _intOrNull(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value);
    return null;
  }
}
