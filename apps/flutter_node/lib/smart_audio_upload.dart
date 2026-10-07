import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:ffmpeg_kit_flutter_new_audio/ffmpeg_kit.dart';
import 'package:ffmpeg_kit_flutter_new_audio/return_code.dart';

const double tdoaClipPreSeconds = 1.0;
const double tdoaClipPostSeconds = 1.0;
const int mp3BitrateKbps = 64;

class WavAudioInfo {
  final String path;
  final int sampleRateHz;
  final int channelCount;
  final int bitsPerSample;
  final int dataOffset;
  final int dataSizeBytes;

  const WavAudioInfo({
    required this.path,
    required this.sampleRateHz,
    required this.channelCount,
    required this.bitsPerSample,
    required this.dataOffset,
    required this.dataSizeBytes,
  });

  int get bytesPerSample => bitsPerSample ~/ 8;
  int get bytesPerFrame => channelCount * bytesPerSample;
  int get totalFrames => dataSizeBytes ~/ bytesPerFrame;
  int get sourcePcmSizeBytes => totalFrames * bytesPerFrame;
}

class ParsedWavAudio {
  final WavAudioInfo info;
  final Uint8List bytes;

  const ParsedWavAudio({required this.info, required this.bytes});
}

class TdoaClipRange {
  final int startSample;
  final int endSample;
  final int peakSample;
  final int durationMs;
  final String source;

  const TdoaClipRange({
    required this.startSample,
    required this.endSample,
    required this.peakSample,
    required this.durationMs,
    required this.source,
  });
}

class TdoaClipResult {
  final String path;
  final String format;
  final int sizeBytes;
  final int startSample;
  final int endSample;
  final int peakSample;
  final int durationMs;
  final String source;

  const TdoaClipResult({
    required this.path,
    required this.format,
    required this.sizeBytes,
    required this.startSample,
    required this.endSample,
    required this.peakSample,
    required this.durationMs,
    required this.source,
  });
}

class PrimaryAudioResult {
  final String path;
  final String format;
  final int sizeBytes;
  final String encodingStatus;
  final int encodingMs;
  final String? warning;

  const PrimaryAudioResult({
    required this.path,
    required this.format,
    required this.sizeBytes,
    required this.encodingStatus,
    required this.encodingMs,
    this.warning,
  });

  bool get isMp3 => format == 'mp3';
}

class SmartAudioResult {
  final PrimaryAudioResult primaryAudio;
  final TdoaClipResult? tdoaClip;
  final int sourcePcmSizeBytes;
  final List<String> temporaryPaths;

  const SmartAudioResult({
    required this.primaryAudio,
    required this.tdoaClip,
    required this.sourcePcmSizeBytes,
    required this.temporaryPaths,
  });

  double? get savingPercent {
    if (sourcePcmSizeBytes <= 0 || primaryAudio.sizeBytes < 0) return null;
    return (1.0 - (primaryAudio.sizeBytes / sourcePcmSizeBytes)) * 100.0;
  }
}

class SmartAudioUploadService {
  Future<SmartAudioResult> prepare({
    required String wavPath,
    required String eventId,
  }) async {
    final wavFile = File(wavPath);
    final parsed = await readWavFile(wavFile);
    final temporaryPaths = <String>[];

    final primary = await encodePrimaryAudio(
      wavPath: wavPath,
      eventId: eventId,
    );

    if (!primary.isMp3) {
      throw StateError(primary.warning ?? 'mp3_encode_failed');
    }

    temporaryPaths.add(primary.path);

    return SmartAudioResult(
      primaryAudio: primary,
      tdoaClip: null,
      sourcePcmSizeBytes: parsed.info.sourcePcmSizeBytes,
      temporaryPaths: temporaryPaths,
    );
  }

  Future<ParsedWavAudio> readWavFile(File file) async {
    final bytes = await file.readAsBytes();
    final info = parseWavInfo(bytes, file.path);
    return ParsedWavAudio(info: info, bytes: bytes);
  }

  WavAudioInfo parseWavInfo(Uint8List bytes, String path) {
    if (bytes.length < 44 ||
        _ascii(bytes, 0, 4) != 'RIFF' ||
        _ascii(bytes, 8, 4) != 'WAVE') {
      throw const FormatException('Not a RIFF/WAVE file');
    }

    final data = ByteData.sublistView(bytes);
    int offset = 12;
    int? sampleRateHz;
    int? channelCount;
    int? bitsPerSample;
    int? dataOffset;
    int? dataSizeBytes;

    while (offset + 8 <= bytes.length) {
      final chunkId = _ascii(bytes, offset, 4);
      final chunkSize = data.getUint32(offset + 4, Endian.little);
      final chunkDataOffset = offset + 8;
      final nextOffset =
          chunkDataOffset + chunkSize + (chunkSize.isOdd ? 1 : 0);

      if (chunkDataOffset + chunkSize > bytes.length) {
        throw const FormatException('Invalid WAV chunk size');
      }

      if (chunkId == 'fmt ') {
        if (chunkSize < 16) {
          throw const FormatException('Invalid WAV fmt chunk');
        }
        final audioFormat = data.getUint16(chunkDataOffset, Endian.little);
        if (audioFormat != 1) {
          throw FormatException('Only PCM WAV is supported, got $audioFormat');
        }
        channelCount = data.getUint16(chunkDataOffset + 2, Endian.little);
        sampleRateHz = data.getUint32(chunkDataOffset + 4, Endian.little);
        bitsPerSample = data.getUint16(chunkDataOffset + 14, Endian.little);
      } else if (chunkId == 'data') {
        dataOffset = chunkDataOffset;
        dataSizeBytes = chunkSize;
      }

      offset = nextOffset;
    }

    if (sampleRateHz == null ||
        channelCount == null ||
        bitsPerSample == null ||
        dataOffset == null ||
        dataSizeBytes == null) {
      throw const FormatException('Missing WAV fmt or data chunk');
    }
    if (sampleRateHz <= 0 || channelCount <= 0 || bitsPerSample != 16) {
      throw FormatException(
        'Unsupported WAV format: $sampleRateHz Hz, $channelCount ch, $bitsPerSample bit',
      );
    }

    final bytesPerFrame = channelCount * (bitsPerSample ~/ 8);
    if (bytesPerFrame <= 0 || dataSizeBytes < bytesPerFrame) {
      throw const FormatException('WAV has no PCM frames');
    }

    return WavAudioInfo(
      path: path,
      sampleRateHz: sampleRateHz,
      channelCount: channelCount,
      bitsPerSample: bitsPerSample,
      dataOffset: dataOffset,
      dataSizeBytes: dataSizeBytes,
    );
  }

  TdoaClipRange calculateTdoaClipRange({
    required int sampleRateHz,
    required int totalFrames,
    int? rmsPeakSample,
    int? eventStartSample,
    double preSeconds = tdoaClipPreSeconds,
    double postSeconds = tdoaClipPostSeconds,
  }) {
    if (sampleRateHz <= 0) {
      throw ArgumentError.value(sampleRateHz, 'sampleRateHz', 'must be > 0');
    }
    if (totalFrames <= 0) {
      throw ArgumentError.value(totalFrames, 'totalFrames', 'must be > 0');
    }

    int centerSample;
    String source;
    if (rmsPeakSample != null &&
        rmsPeakSample >= 0 &&
        rmsPeakSample < totalFrames) {
      centerSample = rmsPeakSample;
      source = 'RMS_PEAK';
    } else if (eventStartSample != null &&
        eventStartSample >= 0 &&
        eventStartSample < totalFrames) {
      centerSample = eventStartSample;
      source = 'EVENT_START_FALLBACK';
    } else {
      centerSample = totalFrames ~/ 2;
      source = 'EVENT_CENTER_FALLBACK';
    }

    final preFrames = (preSeconds * sampleRateHz).round();
    final postFrames = (postSeconds * sampleRateHz).round();
    final startSample = max(0, centerSample - preFrames);
    var endSample = min(totalFrames, centerSample + postFrames);
    if (endSample <= startSample) {
      endSample = min(totalFrames, startSample + 1);
    }

    return TdoaClipRange(
      startSample: startSample,
      endSample: endSample,
      peakSample: centerSample - startSample,
      durationMs: ((endSample - startSample) * 1000 / sampleRateHz).round(),
      source: source,
    );
  }

  Future<TdoaClipResult> writeTdoaClip({
    required ParsedWavAudio parsed,
    required String outputPath,
    int? rmsPeakSample,
    int? eventStartSample,
  }) async {
    final info = parsed.info;
    final range = calculateTdoaClipRange(
      sampleRateHz: info.sampleRateHz,
      totalFrames: info.totalFrames,
      rmsPeakSample: rmsPeakSample,
      eventStartSample: eventStartSample,
    );
    final startByte = info.dataOffset + range.startSample * info.bytesPerFrame;
    final endByte = info.dataOffset + range.endSample * info.bytesPerFrame;
    final pcmBytes = parsed.bytes.sublist(startByte, endByte);
    final wavBytes = buildPcm16WavBytes(
      pcmBytes: pcmBytes,
      sampleRateHz: info.sampleRateHz,
      channelCount: info.channelCount,
      bitsPerSample: info.bitsPerSample,
    );
    final file = File(outputPath);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(wavBytes, flush: true);
    final sizeBytes = await file.length();

    return TdoaClipResult(
      path: outputPath,
      format: 'wav',
      sizeBytes: sizeBytes,
      startSample: range.startSample,
      endSample: range.endSample,
      peakSample: range.peakSample,
      durationMs: range.durationMs,
      source: range.source,
    );
  }

  Uint8List buildPcm16WavBytes({
    required Uint8List pcmBytes,
    required int sampleRateHz,
    required int channelCount,
    required int bitsPerSample,
  }) {
    if (sampleRateHz <= 0 || channelCount <= 0 || bitsPerSample != 16) {
      throw ArgumentError('Only PCM 16-bit WAV output is supported');
    }

    final blockAlign = channelCount * (bitsPerSample ~/ 8);
    final byteRate = sampleRateHz * blockAlign;
    final builder = BytesBuilder(copy: false);
    final header = ByteData(44);

    _writeAscii(header, 0, 'RIFF');
    header.setUint32(4, 36 + pcmBytes.length, Endian.little);
    _writeAscii(header, 8, 'WAVE');
    _writeAscii(header, 12, 'fmt ');
    header.setUint32(16, 16, Endian.little);
    header.setUint16(20, 1, Endian.little);
    header.setUint16(22, channelCount, Endian.little);
    header.setUint32(24, sampleRateHz, Endian.little);
    header.setUint32(28, byteRate, Endian.little);
    header.setUint16(32, blockAlign, Endian.little);
    header.setUint16(34, bitsPerSample, Endian.little);
    _writeAscii(header, 36, 'data');
    header.setUint32(40, pcmBytes.length, Endian.little);

    builder.add(header.buffer.asUint8List());
    builder.add(pcmBytes);
    return builder.takeBytes();
  }

  Future<PrimaryAudioResult> encodePrimaryAudio({
    required String wavPath,
    required String eventId,
    int bitrateKbps = mp3BitrateKbps,
  }) async {
    final sourceFile = File(wavPath);
    final fallbackSize = await sourceFile.length();
    final mp3Path = _sidecarPath(wavPath, '$eventId.mp3');
    final stopwatch = Stopwatch()..start();

    try {
      final command = [
        '-hide_banner',
        '-loglevel error',
        '-y',
        '-i ${_ffmpegArg(wavPath)}',
        '-vn',
        '-ac 1',
        '-codec:a libmp3lame',
        '-b:a ${bitrateKbps}k',
        _ffmpegArg(mp3Path),
      ].join(' ');

      final session = await FFmpegKit.execute(command);
      final returnCode = await session.getReturnCode();
      final mp3File = File(mp3Path);
      final mp3Exists = await mp3File.exists();
      final mp3Size = mp3Exists ? await mp3File.length() : 0;

      if (ReturnCode.isSuccess(returnCode) &&
          mp3Exists &&
          mp3Size > 0 &&
          await looksLikeMp3File(mp3File) &&
          await canDecodeAudio(mp3Path)) {
        stopwatch.stop();
        return PrimaryAudioResult(
          path: mp3Path,
          format: 'mp3',
          sizeBytes: mp3Size,
          encodingStatus: 'MP3_SUCCESS',
          encodingMs: stopwatch.elapsedMilliseconds,
        );
      }

      if (mp3Exists) {
        await mp3File.delete();
      }
      stopwatch.stop();
      return PrimaryAudioResult(
        path: wavPath,
        format: 'wav',
        sizeBytes: fallbackSize,
        encodingStatus: 'WAV_FALLBACK',
        encodingMs: stopwatch.elapsedMilliseconds,
        warning: 'mp3_encode_failed',
      );
    } catch (error) {
      stopwatch.stop();
      return PrimaryAudioResult(
        path: wavPath,
        format: 'wav',
        sizeBytes: fallbackSize,
        encodingStatus: 'WAV_FALLBACK',
        encodingMs: stopwatch.elapsedMilliseconds,
        warning: 'mp3_encode_error=$error',
      );
    }
  }

  Future<bool> looksLikeMp3File(File file) async {
    final access = await file.open();
    try {
      final length = await access.length();
      if (length < 3) return false;
      final head = await access.read(min(16, length));
      if (head.length >= 4 && _ascii(head, 0, 4) == 'RIFF') return false;
      if (head.length >= 3 && _ascii(head, 0, 3) == 'ID3') return true;
      return head.length >= 2 && head[0] == 0xFF && (head[1] & 0xE0) == 0xE0;
    } finally {
      await access.close();
    }
  }

  Future<bool> canDecodeAudio(String path) async {
    final command = [
      '-hide_banner',
      '-loglevel error',
      '-i ${_ffmpegArg(path)}',
      '-f null',
      '-',
    ].join(' ');
    final session = await FFmpegKit.execute(command);
    final returnCode = await session.getReturnCode();
    return ReturnCode.isSuccess(returnCode);
  }

  Future<void> cleanupUploadedTemporaryFiles(
    Iterable<String> paths, {
    required String originalWavPath,
  }) async {
    for (final path in paths) {
      if (path == originalWavPath) continue;
      try {
        final file = File(path);
        if (await file.exists()) {
          await file.delete();
        }
      } catch (_) {
        // Best-effort cleanup only.
      }
    }
  }

  String _sidecarPath(String sourcePath, String filename) {
    final source = File(sourcePath);
    return '${source.parent.path}${Platform.pathSeparator}$filename';
  }

  String _ffmpegArg(String value) {
    return '"${value.replaceAll('"', r'\"')}"';
  }

  String _ascii(List<int> bytes, int offset, int length) {
    if (offset + length > bytes.length) return '';
    return String.fromCharCodes(bytes.sublist(offset, offset + length));
  }

  void _writeAscii(ByteData data, int offset, String value) {
    for (var index = 0; index < value.length; index += 1) {
      data.setUint8(offset + index, value.codeUnitAt(index));
    }
  }
}
