import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/services/node_connection_service.dart';

void main() {
  test(
    'existing Node socket envelopes carry results and reconnect replay',
    () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final sockets = <WebSocket>[];
      final received = <Map<String, dynamic>>[];
      final connected = StreamController<void>.broadcast();
      final subscription = server.listen((request) async {
        expect(request.uri.path, '/ws/node/test-node');
        final socket = await WebSocketTransformer.upgrade(request);
        sockets.add(socket);
        socket.listen((raw) {
          final envelope = jsonDecode(raw as String) as Map<String, dynamic>;
          received.add(envelope);
          if (envelope['message_type'] == 'hello') {
            socket.add(
              jsonEncode({
                'message_type': 'hello_ack',
                'payload': {'connection_id': 'test-${sockets.length}'},
              }),
            );
          }
        });
      });
      final service = NodeConnectionService(
        statusProvider: () => {
          'recording': true,
          'app_version': 'flutter-node-v4-realtime-detection-v1',
        },
        onCommand: (_) async =>
            const NodeCommandExecutionResult(success: true, message: 'ok'),
        onStateChanged: (snapshot) {
          if (snapshot.status == NodeConnectionStatus.connected) {
            connected.add(null);
          }
        },
      );
      addTearDown(() async {
        await service.stop();
        for (final socket in sockets) {
          await socket.close();
        }
        await subscription.cancel();
        await server.close(force: true);
        await connected.close();
      });
      final base = 'http://127.0.0.1:${server.port}';
      service.configure(backendBaseUrl: base, deviceId: 'test-node');
      var ready = connected.stream.first.timeout(const Duration(seconds: 5));
      await service.start();
      await ready;
      final detections = <Map<String, dynamic>>[];
      Future<void> waitFor(int count) async {
        final deadline = DateTime.now().add(const Duration(seconds: 5));
        while (detections.length < count) {
          detections.clear();
          detections.addAll(
            received.where(
              (e) => (e['payload'] as Map).containsKey('detection_state'),
            ),
          );
          if (DateTime.now().isAfter(deadline)) {
            fail('No detection frame received');
          }
          await Future<void>.delayed(const Duration(milliseconds: 5));
        }
      }

      void report(bool active) => service.sendDetectionState(
        session: service.detectionState.session,
        active: active,
        observedAtMs: 123456,
        label: active ? 'Drone' : 'Car',
        confidence: active ? 0.87 : null,
      );
      report(true);
      await waitFor(1);
      report(false);
      await waitFor(2);
      final first = detections.first;
      expect(first['message_type'], 'status_update');
      expect(first['protocol_version'], 1);
      expect(first['device_id'], 'test-node');
      expect(first['message_id'], isA<String>());
      expect((first['payload'] as Map)['detection_state'], {
        'active': true,
        'sequence': 1,
        'observed_at_ms': 123456,
        'label': 'Drone',
        'confidence': 0.87,
      });
      expect(
        received.first['payload']['app_version'],
        'flutter-node-v4-realtime-detection-v1',
      );
      ready = connected.stream.first.timeout(const Duration(seconds: 5));
      await service.reconnect(backendBaseUrl: base, deviceId: 'test-node');
      await ready;
      await waitFor(3);
      expect(detections.last['payload']['detection_state']['sequence'], 3);
      expect(detections.last['payload']['detection_state']['active'], false);
      service.stopDetection();
      await waitFor(4);
      expect(detections.last['payload']['detection_state']['sequence'], 4);
      expect(detections.last['payload']['detection_state']['active'], false);
      expect(sockets.length, 2);
      final recreated = NodeConnectionService(
        statusProvider: () => {},
        onCommand: (_) async =>
            const NodeCommandExecutionResult(success: true, message: 'ok'),
        onStateChanged: (_) {},
      );
      recreated.sendDetectionState(
        session: recreated.detectionState.session,
        active: false,
        observedAtMs: 123457,
      );
      expect(recreated.detectionState.latest!['sequence'], 5);
    },
  );
}
