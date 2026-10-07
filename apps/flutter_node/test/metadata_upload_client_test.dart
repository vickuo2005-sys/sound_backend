import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sound_detector_clean/services/metadata_upload_client.dart';

class RecordingClient extends http.BaseClient {
  int requestCount = 0;
  bool closed = false;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    requestCount += 1;
    final requestBody = await request.finalize().bytesToString();
    final decoded = jsonDecode(requestBody) as Map<String, dynamic>;
    expect(decoded['event_id'], isNotEmpty);
    return http.StreamedResponse(
      Stream<List<int>>.value(utf8.encode('{"status":"success"}')),
      200,
      headers: <String, String>{'server-timing': 'db;dur=2.1'},
    );
  }

  @override
  void close() {
    closed = true;
    super.close();
  }
}

void main() {
  test('reuses one persistent HTTP client and closes it on dispose', () async {
    final transport = RecordingClient();
    final client = MetadataUploadClient(client: transport);

    for (var index = 0; index < 2; index += 1) {
      final response = await client.postEvent(
        uri: Uri.parse('https://example.test/events'),
        uploadToken: 'test-token',
        payload: <String, dynamic>{'event_id': 'event_$index'},
      );
      expect(response.statusCode, 200);
      expect(response.headers['server-timing'], 'db;dur=2.1');
    }

    expect(transport.requestCount, 2);
    client.close();
    expect(transport.closed, isTrue);
  });
}
