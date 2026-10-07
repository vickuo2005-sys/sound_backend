import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/smart_audio_upload.dart';

void main() {
  late SmartAudioUploadService service;

  setUp(() {
    service = SmartAudioUploadService();
  });

  test('clip range uses one second before and after middle peak', () {
    final range = service.calculateTdoaClipRange(
      sampleRateHz: 16000,
      totalFrames: 80000,
      rmsPeakSample: 40000,
    );

    expect(range.startSample, 24000);
    expect(range.endSample, 56000);
    expect(range.peakSample, 16000);
    expect(range.durationMs, 2000);
    expect(range.source, 'RMS_PEAK');
  });

  test('clip range clamps near start', () {
    final range = service.calculateTdoaClipRange(
      sampleRateHz: 16000,
      totalFrames: 80000,
      rmsPeakSample: 4000,
    );

    expect(range.startSample, 0);
    expect(range.endSample, 20000);
    expect(range.peakSample, 4000);
  });

  test('clip range clamps near end', () {
    final range = service.calculateTdoaClipRange(
      sampleRateHz: 16000,
      totalFrames: 80000,
      rmsPeakSample: 76000,
    );

    expect(range.startSample, 60000);
    expect(range.endSample, 80000);
    expect(range.peakSample, 16000);
  });

  test('writes PCM 16-bit WAV clip with original format', () async {
    final tempDir = await Directory.systemTemp.createTemp('smart_audio_test_');
    try {
      const sampleRate = 16000;
      const totalFrames = 80000;
      final pcm = Uint8List(totalFrames * 2);
      final pcmData = ByteData.sublistView(pcm);
      for (var frame = 0; frame < totalFrames; frame += 1) {
        pcmData.setInt16(frame * 2, frame % 32767, Endian.little);
      }

      final sourceBytes = service.buildPcm16WavBytes(
        pcmBytes: pcm,
        sampleRateHz: sampleRate,
        channelCount: 1,
        bitsPerSample: 16,
      );
      final sourceFile = File(
        '${tempDir.path}${Platform.pathSeparator}source.wav',
      );
      await sourceFile.writeAsBytes(sourceBytes);

      final parsed = await service.readWavFile(sourceFile);
      expect(parsed.info.sampleRateHz, sampleRate);
      expect(parsed.info.channelCount, 1);
      expect(parsed.info.bitsPerSample, 16);
      expect(parsed.info.totalFrames, totalFrames);

      final clip = await service.writeTdoaClip(
        parsed: parsed,
        outputPath: '${tempDir.path}${Platform.pathSeparator}clip.wav',
        rmsPeakSample: 40000,
      );

      expect(clip.startSample, 24000);
      expect(clip.endSample, 56000);
      expect(clip.peakSample, 16000);
      expect(clip.durationMs, 2000);
      expect(clip.sizeBytes, 64044);

      final clipParsed = await service.readWavFile(File(clip.path));
      expect(clipParsed.info.sampleRateHz, sampleRate);
      expect(clipParsed.info.channelCount, 1);
      expect(clipParsed.info.bitsPerSample, 16);
      expect(clipParsed.info.totalFrames, 32000);
    } finally {
      await tempDir.delete(recursive: true);
    }
  });

  test('MP3 header check rejects WAV header', () async {
    final tempDir = await Directory.systemTemp.createTemp('smart_audio_test_');
    try {
      final mp3File = File('${tempDir.path}${Platform.pathSeparator}fake.mp3');
      await mp3File.writeAsBytes(Uint8List.fromList('ID3fake'.codeUnits));
      expect(await service.looksLikeMp3File(mp3File), isTrue);

      final wavFile = File('${tempDir.path}${Platform.pathSeparator}fake.wav');
      await wavFile.writeAsBytes(Uint8List.fromList('RIFFxxxxWAVE'.codeUnits));
      expect(await service.looksLikeMp3File(wavFile), isFalse);
    } finally {
      await tempDir.delete(recursive: true);
    }
  });
}
