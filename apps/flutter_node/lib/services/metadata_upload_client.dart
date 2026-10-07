import 'dart:convert';

import 'package:http/http.dart' as http;

/// Long-lived metadata HTTP transport. One instance is kept for the lifetime
/// of the detector page so TCP/TLS connections can be reused across events.
class MetadataUploadClient {
  MetadataUploadClient({http.Client? client})
    : _client = client ?? http.Client();

  final http.Client _client;
  bool _closed = false;

  Future<http.Response> postEvent({
    required Uri uri,
    required String uploadToken,
    required Map<String, dynamic> payload,
    Duration timeout = const Duration(seconds: 75),
  }) {
    if (_closed) {
      throw StateError('MetadataUploadClient is closed');
    }
    return _client
        .post(
          uri,
          headers: <String, String>{
            'Content-Type': 'application/json',
            'x-upload-token': uploadToken,
          },
          body: jsonEncode(payload),
        )
        .timeout(timeout);
  }

  void close() {
    if (_closed) return;
    _closed = true;
    _client.close();
  }
}
