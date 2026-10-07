import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/services/live_audio_stream_service.dart';

void main() {
  test('serializes PCM16 live audio frame header', () {
    final service = LiveAudioStreamService();
    final payload = Uint8List.fromList([1, 2, 3, 4]);
    final frame = service.buildPcm16Frame(
      streamId: '00112233-4455-6677-8899-aabbccddeeff',
      sequenceNumber: 7,
      captureTimestampUs: 123456789,
      sampleRateHz: 16000,
      channelCount: 1,
      frameDurationMs: 20,
      payload: payload,
    );

    final data = ByteData.sublistView(frame);
    expect(String.fromCharCodes(frame.sublist(0, 4)), 'SDAF');
    expect(data.getUint8(4), 1);
    expect(data.getUint16(6, Endian.big), 52);
    expect(data.getUint64(24, Endian.big), 7);
    expect(data.getUint64(32, Endian.big), 123456789);
    expect(data.getUint32(40, Endian.big), 16000);
    expect(data.getUint16(44, Endian.big), 1);
    expect(data.getUint8(46), 1);
    expect(data.getUint8(47), 20);
    expect(data.getUint32(48, Endian.big), payload.length);
    expect(frame.sublist(52), payload);
  });
}
