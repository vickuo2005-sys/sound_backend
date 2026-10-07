import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

class LiveAudioStreamService {
  WebSocket? _socket;
  String? _streamId;
  int _sequenceNumber = 0;
  bool _isStreaming = false;
  Completer<void>? _startCompleter;

  bool get isStreaming => _isStreaming;
  String? get streamId => _streamId;

  Future<void> start({
    required String backendBaseUrl,
    required String deviceId,
    required String uploadToken,
    required String streamId,
    required String streamToken,
  }) async {
    await stop();
    _streamId = streamId;
    _sequenceNumber = 0;
    _startCompleter = Completer<void>();

    final base = Uri.parse(backendBaseUrl);
    final uri = base.replace(
      scheme: base.scheme == 'https' ? 'wss' : 'ws',
      path: '/ws/audio/${Uri.encodeComponent(deviceId)}',
      query: '',
    );

    final socket = await WebSocket.connect(
      uri.toString(),
      headers: {
        'x-upload-token': uploadToken,
        'x-stream-id': streamId,
        'x-stream-token': streamToken,
      },
    ).timeout(const Duration(seconds: 10));

    _socket = socket;

    socket.listen(
      (dynamic message) {
        if (message is String) {
          _handleServerMessage(message);
        }
      },
      onDone: () {
        _isStreaming = false;
        _socket = null;
      },
      onError: (_) {
        _isStreaming = false;
        _socket = null;
      },
      cancelOnError: true,
    );

    try {
      await _startCompleter!.future.timeout(const Duration(seconds: 5));
    } catch (_) {
      _startCompleter = null;
      await stop();
      rethrow;
    }
  }

  Future<void> stop() async {
    _isStreaming = false;
    _startCompleter = null;
    final socket = _socket;
    _socket = null;
    if (socket != null) {
      try {
        socket.add('stop');
        await socket.close();
      } catch (_) {
        // Best-effort cleanup.
      }
    }
  }

  void sendPcmFrame(Map<String, dynamic> frame) {
    final socket = _socket;
    final streamId = _streamId;
    if (!_isStreaming || socket == null || streamId == null) return;

    final rawBytes = frame['pcm_bytes'];
    if (rawBytes is! Uint8List || rawBytes.isEmpty) return;

    final sampleRate = _intValue(frame['sample_rate_hz'], fallback: 16000);
    final channelCount = _intValue(frame['channel_count'], fallback: 1);
    final captureTimestampUs = _intValue(
      frame['capture_timestamp_us'],
      fallback: DateTime.now().microsecondsSinceEpoch,
    );
    final samples = max(1, rawBytes.length ~/ max(1, channelCount * 2));
    final frameDurationMs = max(
      1,
      min(255, (samples * 1000 / sampleRate).round()),
    );

    socket.add(
      buildPcm16Frame(
        streamId: streamId,
        sequenceNumber: _sequenceNumber++,
        captureTimestampUs: captureTimestampUs,
        sampleRateHz: sampleRate,
        channelCount: channelCount,
        frameDurationMs: frameDurationMs,
        payload: rawBytes,
      ),
    );
  }

  Uint8List buildPcm16Frame({
    required String streamId,
    required int sequenceNumber,
    required int captureTimestampUs,
    required int sampleRateHz,
    required int channelCount,
    required int frameDurationMs,
    required Uint8List payload,
  }) {
    const headerLength = 52;
    final frame = Uint8List(headerLength + payload.length);
    final data = ByteData.sublistView(frame);
    final uuidBytes = _uuidToBytes(streamId);

    frame.setRange(0, 4, 'SDAF'.codeUnits);
    data.setUint8(4, 1);
    data.setUint8(5, 0);
    data.setUint16(6, headerLength, Endian.big);
    frame.setRange(8, 24, uuidBytes);
    data.setUint64(24, sequenceNumber, Endian.big);
    data.setUint64(32, captureTimestampUs, Endian.big);
    data.setUint32(40, sampleRateHz, Endian.big);
    data.setUint16(44, channelCount, Endian.big);
    data.setUint8(46, 1); // pcm16
    data.setUint8(47, frameDurationMs);
    data.setUint32(48, payload.length, Endian.big);
    frame.setRange(headerLength, frame.length, payload);
    return frame;
  }

  void _handleServerMessage(String message) {
    try {
      final body = jsonDecode(message);
      if (body is Map && body['type'] == 'audio_stream_rejected') {
        _isStreaming = false;
        _startCompleter?.completeError(
          StateError(body['reason']?.toString() ?? 'audio stream rejected'),
        );
        _startCompleter = null;
      }
      if (body is Map && body['type'] == 'audio_stream_ready') {
        _isStreaming = true;
        _startCompleter?.complete();
        _startCompleter = null;
      }
    } catch (_) {
      // Ignore non-JSON control text.
    }
  }

  int _intValue(dynamic value, {required int fallback}) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    return fallback;
  }

  Uint8List _uuidToBytes(String value) {
    final normalized = value.replaceAll('-', '');
    if (normalized.length != 32) {
      return Uint8List(16);
    }
    final bytes = Uint8List(16);
    for (var i = 0; i < 16; i += 1) {
      bytes[i] = int.parse(normalized.substring(i * 2, i * 2 + 2), radix: 16);
    }
    return bytes;
  }
}
