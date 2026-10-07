import 'dart:async';

/// One in-flight send and one replaceable latest state; never a replay queue.
class RealtimeDetectionState {
  RealtimeDetectionState({required this.send, this.log, this.nextSequence});

  final Future<void> Function(Map<String, dynamic>) send;
  final void Function(String)? log;
  final int Function()? nextSequence;
  Map<String, dynamic>? _latest;
  Map<String, dynamic>? _pending;
  int _sequence = 0;
  int _session = 0;
  bool _connected = false;
  bool _sending = false;
  bool _accepting = true;
  int _connectionGeneration = 0;

  int get session => _session;
  Map<String, dynamic>? get latest =>
      _latest == null ? null : Map<String, dynamic>.unmodifiable(_latest!);

  void inference({
    required int session,
    required bool active,
    required int observedAtMs,
    String? label,
    double? confidence,
  }) {
    if (!_accepting || session != _session) return;
    _publish({
      'active': active,
      'observed_at_ms': observedAtMs,
      'label': label,
      'confidence': confidence?.isFinite == true ? confidence : null,
    });
  }

  void stop({required int observedAtMs}) {
    _accepting = false;
    _session++;
    _publish({
      'active': false,
      'observed_at_ms': observedAtMs,
      'label': null,
      'confidence': null,
    });
  }

  void startSession() {
    _session++;
    _accepting = true;
  }

  void setConnected(bool connected) {
    if (connected != _connected) _connectionGeneration++;
    final becameConnected = connected && !_connected;
    _connected = connected;
    if (!connected) _pending = null;
    if (becameConnected && _latest != null) _publish({..._latest!});
  }

  void _publish(Map<String, dynamic> state) {
    _sequence = nextSequence?.call() ?? _sequence + 1;
    state['sequence'] = _sequence;
    _latest = state;
    log?.call(
      '[RT_DETECTION] seq=$_sequence active=${state['active']} '
      'label=${state['label']} confidence=${state['confidence']} '
      'observed_at_ms=${state['observed_at_ms']} '
      'ws=${_connected ? 'connected' : 'disconnected'}',
    );
    if (!_connected) return;
    _pending = state;
    if (!_sending) unawaited(_drain());
  }

  Future<void> _drain() async {
    _sending = true;
    try {
      while (_connected && _pending != null) {
        final state = _pending!;
        final generation = _connectionGeneration;
        _pending = null;
        try {
          await send(state);
        } catch (_) {
          // Keep latest for reconnect; transport failure never reaches inference.
          if (generation == _connectionGeneration) {
            _connected = false;
            _pending = null;
          }
          log?.call('[RT_DETECTION] send_failed seq=${state['sequence']}');
        }
      }
    } finally {
      _sending = false;
    }
  }
}
