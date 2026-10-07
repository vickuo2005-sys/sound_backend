import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/services.dart' show rootBundle;
import 'package:image/image.dart' as img;
import 'package:tflite_flutter/tflite_flutter.dart' as tfl;

import 'classification_result.dart';

class AiInferenceResult {
  final bool success;
  final String label;
  final double? aircraftProbability;
  final double? confidence;
  final int inferenceTimeMs;
  final String status;
  final ClassificationResult? classification;

  const AiInferenceResult({
    required this.success,
    required this.label,
    required this.aircraftProbability,
    required this.confidence,
    required this.inferenceTimeMs,
    required this.status,
    this.classification,
  });

  factory AiInferenceResult.success({
    required double aircraftProbability,
    required double confidence,
    required int inferenceTimeMs,
    String? label,
  }) {
    return AiInferenceResult(
      success: true,
      label: label ?? (aircraftProbability > 0.5 ? "aircraft" : "non_aircraft"),
      aircraftProbability: aircraftProbability,
      confidence: confidence,
      inferenceTimeMs: inferenceTimeMs,
      status: "success",
    );
  }

  factory AiInferenceResult.failure({
    required String status,
    required int inferenceTimeMs,
  }) {
    return AiInferenceResult(
      success: false,
      label: "sound_event",
      aircraftProbability: null,
      confidence: null,
      inferenceTimeMs: inferenceTimeMs,
      status: status,
    );
  }

  factory AiInferenceResult.fromClassification({
    required ClassificationResult classification,
    required int inferenceTimeMs,
  }) {
    return AiInferenceResult(
      success: true,
      label: classification.operationalClass,
      aircraftProbability: classification.aircraftProbability,
      confidence: classification.confidence,
      inferenceTimeMs: inferenceTimeMs,
      status: "success",
      classification: classification,
    );
  }
}

class AiModelOption {
  final String id;
  final String name;
  final String assetPath;
  final String profileHint;
  final String outputKind;
  final String modelVersion;
  final String? labelsAssetPath;
  final double defaultThreshold;
  final List<String> classLabels;
  final List<int> targetClassIndices;
  final Map<int, String> targetOutputLabels;

  const AiModelOption({
    required this.id,
    required this.name,
    required this.assetPath,
    required this.profileHint,
    required this.outputKind,
    required this.modelVersion,
    this.labelsAssetPath,
    required this.defaultThreshold,
    this.classLabels = const ["non_aircraft", "aircraft"],
    this.targetClassIndices = const [1],
    this.targetOutputLabels = const {1: "aircraft"},
  });
}

class AiSoundClassifier {
  static const String preclassifierModelAssetPath =
      "assets/models/preclassifier_mobile.tflite";
  static const String preclassifierLabelsAssetPath =
      "assets/models/preclassifier_labels.json";
  static const String legacyModelAssetPath =
      "assets/models/mobile_audio_float16.tflite";
  static const String v110ModelAssetPath =
      "assets/models/v1_1_0_flower_drone_audio.tflite";
  static const String defaultModelId = "preclassifier";
  static const List<AiModelOption> supportedModels = [
    AiModelOption(
      id: "preclassifier",
      name: "預分類器 V1",
      assetPath: preclassifierModelAssetPath,
      profileHint: "preclassifier",
      outputKind: "logits",
      modelVersion: "1",
      labelsAssetPath: preclassifierLabelsAssetPath,
      defaultThreshold: preclassifierThresholdDefault,
    ),
    AiModelOption(
      id: "v1_1_0_flower_drone_audio",
      name: "V1.1.0 花收音 5 類模型",
      assetPath: v110ModelAssetPath,
      profileHint: "auto",
      outputKind: "probabilities",
      modelVersion: "1.1.0",
      defaultThreshold: 0.5,
      classLabels: ["Airplane", "Car", "Drone", "Electric_saw", "Rainfall"],
      targetClassIndices: [0, 2],
      targetOutputLabels: {0: "aircraft", 2: "drone"},
    ),
    AiModelOption(
      id: "mobile_audio_float16",
      name: "舊版 RGB 模型",
      assetPath: legacyModelAssetPath,
      profileHint: "legacy_rgb",
      outputKind: "logits",
      modelVersion: "legacy",
      defaultThreshold: 0.5,
    ),
  ];
  static const int targetSampleRate = 16000;
  static const int preclassifierNFft = 1024;
  static const int preclassifierWinLength = 1024;
  static const int preclassifierHopLength = 320;
  static const int preclassifierNMels = 128;
  static const int preclassifierTargetFrames = 256;
  static const double preclassifierAudioSec = 3.0;
  static const double preclassifierFMin = 20.0;
  static const double preclassifierThresholdDefault = 0.60;
  static const int legacyNFft = 2048;
  static const int legacyHopLength = 512;
  static const int legacyNMels = 128;
  static const int legacyInputSize = 224;
  static const double topDb = 80.0;

  tfl.Interpreter? _interpreter;
  _ModelProfile _modelProfile = _ModelProfile.none;
  AiModelOption _activeModel = supportedModels.first;
  List<int> _inputShape = const [];
  List<int> _outputShape = const [];
  int _positiveClassIndex = 1;
  double _decisionThreshold = preclassifierThresholdDefault;

  bool get isLoaded => _interpreter != null;
  String get activeModelId => _activeModel.id;
  String get activeModelName => _activeModel.name;
  String get activeModelVersion => _activeModel.modelVersion;
  List<int> get inputShape => List<int>.unmodifiable(_inputShape);
  List<int> get outputShape => List<int>.unmodifiable(_outputShape);

  static AiModelOption modelOptionForId(String? id) {
    for (final option in supportedModels) {
      if (option.id == id) return option;
    }
    return supportedModels.first;
  }

  Future<void> load({String? modelId}) async {
    final requested = modelOptionForId(modelId);
    final fallbackOptions = <AiModelOption>[
      requested,
      modelOptionForId(defaultModelId),
      modelOptionForId("mobile_audio_float16"),
    ];
    final attemptedIds = <String>{};
    Object? lastError;

    for (final option in fallbackOptions) {
      if (!attemptedIds.add(option.id)) continue;
      try {
        await _loadModelOption(option);
        return;
      } catch (error) {
        lastError = error;
        close();
      }
    }

    throw lastError ?? Exception("ai_model_load_failed");
  }

  Future<void> _loadModelOption(AiModelOption option) async {
    close();

    _interpreter = await tfl.Interpreter.fromAsset(option.assetPath);
    _activeModel = option;
    _positiveClassIndex = 1;
    _decisionThreshold = option.defaultThreshold;

    _interpreter!.allocateTensors();
    _inputShape = List<int>.from(_interpreter!.getInputTensor(0).shape);
    _outputShape = List<int>.from(_interpreter!.getOutputTensor(0).shape);
    _modelProfile = _profileForInputShape(_inputShape, option.profileHint);

    if (_modelProfile == _ModelProfile.preclassifier) {
      await _loadPreclassifierMetadata(option.labelsAssetPath);
    }
  }

  void close() {
    _interpreter?.close();
    _interpreter = null;
    _modelProfile = _ModelProfile.none;
    _inputShape = const [];
    _outputShape = const [];
  }

  Future<AiInferenceResult> runOnWav(String wavPath) async {
    final stopwatch = Stopwatch()..start();

    try {
      final interpreter = _interpreter;
      if (interpreter == null) {
        return AiInferenceResult.failure(
          status: "model_not_loaded",
          inferenceTimeMs: stopwatch.elapsedMilliseconds,
        );
      }

      final input = await _buildInputTensorInBackground(wavPath);
      final output = _zeroTensorForShape(_outputShape);

      interpreter.run(input, output);

      final rawOutput = _flattenTensor(output);
      final probabilities = _probabilitiesFromOutput(
        rawOutput,
        _activeModel.outputKind,
      );
      if (_isCanonicalFiveClassModel(probabilities)) {
        final classification = ClassificationResult.fromFiveClassScores(
          modelId: _activeModel.id,
          modelVersion: _activeModel.modelVersion,
          scores: probabilities,
          targetThreshold: _decisionThreshold,
        );
        stopwatch.stop();
        return AiInferenceResult.fromClassification(
          classification: classification,
          inferenceTimeMs: stopwatch.elapsedMilliseconds,
        );
      }
      final aircraftProbability = _targetProbability(probabilities);
      final confidence = max(
        probabilities.reduce(max),
        0.0,
      ).clamp(0.0, 1.0).toDouble();
      final label = aircraftProbability > _decisionThreshold
          ? _targetLabelForProbabilities(probabilities)
          : "non_aircraft";
      stopwatch.stop();

      return AiInferenceResult.success(
        aircraftProbability: aircraftProbability,
        confidence: confidence,
        inferenceTimeMs: stopwatch.elapsedMilliseconds,
        label: label,
      );
    } catch (error) {
      stopwatch.stop();
      return AiInferenceResult.failure(
        status: "failed: $error",
        inferenceTimeMs: stopwatch.elapsedMilliseconds,
      );
    }
  }

  Future<dynamic> _buildInputTensorInBackground(String wavPath) {
    final profileName = _modelProfile.name;
    final inputShape = List<int>.from(_inputShape);

    return Isolate.run(() async {
      final helper = AiSoundClassifier().._inputShape = inputShape;
      final wav = await helper._readWavFile(wavPath);
      final mono16k = helper._resampleLinear(
        wav.samples,
        wav.sampleRate,
        targetSampleRate,
      );

      return profileName == _ModelProfile.preclassifier.name
          ? helper._preclassifierInputTensor(mono16k)
          : helper._legacyRgbInputTensor(mono16k);
    });
  }

  _ModelProfile _profileForInputShape(List<int> shape, String profileHint) {
    if (shape.length == 4 &&
        shape[1] == 1 &&
        shape[2] == preclassifierNMels &&
        shape[3] == preclassifierTargetFrames) {
      return _ModelProfile.preclassifier;
    }

    if (shape.length == 4 &&
        shape[1] == preclassifierNMels &&
        shape[2] == preclassifierTargetFrames &&
        shape[3] == 1) {
      return _ModelProfile.preclassifier;
    }

    if (shape.length == 4 &&
        shape[1] == legacyInputSize &&
        shape[2] == legacyInputSize &&
        shape[3] == 3) {
      return _ModelProfile.legacyRgb;
    }

    if (profileHint == "preclassifier") {
      return _ModelProfile.preclassifier;
    }
    if (profileHint == "legacy_rgb") {
      return _ModelProfile.legacyRgb;
    }

    throw Exception("unsupported_model_input_shape_$shape");
  }

  Future<void> _loadPreclassifierMetadata(String? labelsAssetPath) async {
    if (labelsAssetPath == null || labelsAssetPath.isEmpty) {
      return;
    }

    try {
      final jsonText = await rootBundle.loadString(labelsAssetPath);
      final metadata = jsonDecode(jsonText) as Map<String, dynamic>;
      final positiveIndex = metadata["positive_class_index"];
      final threshold = metadata["threshold"];

      if (positiveIndex is num) {
        _positiveClassIndex = positiveIndex.toInt();
      }
      if (threshold is num) {
        _decisionThreshold = threshold.toDouble();
      }
    } catch (_) {
      _positiveClassIndex = 1;
      _decisionThreshold = preclassifierThresholdDefault;
    }
  }

  double _targetProbability(List<double> probabilities) {
    var total = 0.0;
    var hasValidTarget = false;
    final indices = _activeModel.targetClassIndices.isEmpty
        ? [_positiveClassIndex]
        : _activeModel.targetClassIndices;

    for (final index in indices) {
      if (index < 0 || index >= probabilities.length) continue;
      total += probabilities[index].clamp(0.0, 1.0).toDouble();
      hasValidTarget = true;
    }

    if (!hasValidTarget && probabilities.isNotEmpty) {
      final fallbackIndex = _positiveClassIndex.clamp(
        0,
        probabilities.length - 1,
      );
      total = probabilities[fallbackIndex].clamp(0.0, 1.0).toDouble();
    }

    return total.clamp(0.0, 1.0).toDouble();
  }

  String _targetLabelForProbabilities(List<double> probabilities) {
    final indices = _activeModel.targetClassIndices.isEmpty
        ? [_positiveClassIndex]
        : _activeModel.targetClassIndices;
    var bestTargetIndex = -1;
    var bestTargetProbability = -1.0;

    for (final index in indices) {
      if (index < 0 || index >= probabilities.length) continue;
      final probability = probabilities[index];
      if (probability > bestTargetProbability) {
        bestTargetProbability = probability;
        bestTargetIndex = index;
      }
    }

    if (bestTargetIndex >= 0) {
      return _activeModel.targetOutputLabels[bestTargetIndex] ?? "aircraft";
    }

    return _activeModel.targetOutputLabels[_positiveClassIndex] ?? "aircraft";
  }

  List<double> _probabilitiesFromOutput(
    List<double> rawOutput,
    String outputKind,
  ) {
    if (outputKind == "probabilities") {
      return _validatedModelScores(rawOutput);
    }

    if (rawOutput.length == 1) {
      final value = rawOutput[0];
      final probability = value >= 0.0 && value <= 1.0
          ? value
          : 1.0 / (1.0 + exp(-value));
      return [1.0 - probability, probability];
    }

    return _softmax(rawOutput);
  }

  bool _isCanonicalFiveClassModel(List<double> scores) {
    return scores.length == canonicalSoundLabels.length &&
        _activeModel.classLabels.length == canonicalSoundLabels.length &&
        List<bool>.generate(
          canonicalSoundLabels.length,
          (index) =>
              _activeModel.classLabels[index] == canonicalSoundLabels[index],
        ).every((matches) => matches);
  }

  List<double> _validatedModelScores(List<double> scores) {
    for (final score in scores) {
      if (!score.isFinite || score < 0.0 || score > 1.0) {
        throw Exception("invalid_model_score");
      }
    }
    // The audited v1.1.0 graph ends in SOFTMAX. Preserve its output values
    // instead of renormalizing them and changing the recorded model scores.
    return List<double>.from(scores, growable: false);
  }

  dynamic _zeroTensorForShape(List<int> shape) {
    if (shape.isEmpty) {
      return List<double>.filled(1, 0.0);
    }

    dynamic build(int dimension) {
      if (dimension >= shape.length) {
        return 0.0;
      }

      final length = shape[dimension] < 1 ? 1 : shape[dimension];
      return List.generate(length, (_) => build(dimension + 1));
    }

    return build(0);
  }

  List<double> _flattenTensor(dynamic tensor) {
    final values = <double>[];

    void collect(dynamic value) {
      if (value is num) {
        values.add(value.toDouble());
        return;
      }
      if (value is Iterable) {
        for (final item in value) {
          collect(item);
        }
      }
    }

    collect(tensor);
    if (values.isEmpty) {
      throw Exception("empty_model_output");
    }
    return values;
  }

  List<double> _softmax(List<double> logits) {
    final maxLogit = logits.reduce(max);
    final expValues = logits.map((value) => exp(value - maxLogit)).toList();
    final sumExp = expValues.fold<double>(0.0, (sum, value) => sum + value);

    if (sumExp <= 0.0 || sumExp.isNaN || sumExp.isInfinite) {
      return List<double>.filled(logits.length, 1.0 / logits.length);
    }

    return expValues.map((value) => value / sumExp).toList();
  }

  Future<_WavAudio> _readWavFile(String wavPath) async {
    final file = File(wavPath);
    if (!await file.exists()) {
      throw Exception("wav_not_found");
    }

    final bytes = await file.readAsBytes();
    if (bytes.length < 44) {
      throw Exception("invalid_wav");
    }

    final data = ByteData.sublistView(bytes);
    if (_ascii(bytes, 0, 4) != "RIFF" || _ascii(bytes, 8, 4) != "WAVE") {
      throw Exception("not_riff_wave");
    }

    int? audioFormat;
    int? channels;
    int? sampleRate;
    int? bitsPerSample;
    int? dataOffset;
    int? dataSize;

    var offset = 12;
    while (offset + 8 <= bytes.length) {
      final chunkId = _ascii(bytes, offset, 4);
      final chunkSize = data.getUint32(offset + 4, Endian.little);
      final chunkDataOffset = offset + 8;

      if (chunkId == "fmt ") {
        audioFormat = data.getUint16(chunkDataOffset, Endian.little);
        channels = data.getUint16(chunkDataOffset + 2, Endian.little);
        sampleRate = data.getUint32(chunkDataOffset + 4, Endian.little);
        bitsPerSample = data.getUint16(chunkDataOffset + 14, Endian.little);
      } else if (chunkId == "data") {
        dataOffset = chunkDataOffset;
        dataSize = chunkSize;
      }

      offset = chunkDataOffset + chunkSize + (chunkSize.isOdd ? 1 : 0);
    }

    if (audioFormat == null ||
        channels == null ||
        sampleRate == null ||
        bitsPerSample == null ||
        dataOffset == null ||
        dataSize == null) {
      throw Exception("wav_missing_chunks");
    }

    if (channels <= 0) {
      throw Exception("invalid_channel_count");
    }

    final bytesPerSample = bitsPerSample ~/ 8;
    if (bytesPerSample <= 0) {
      throw Exception("invalid_bits_per_sample");
    }

    final frameSize = bytesPerSample * channels;
    final frameCount = dataSize ~/ frameSize;
    final samples = Float64List(frameCount);

    for (var frame = 0; frame < frameCount; frame++) {
      var sum = 0.0;
      final frameOffset = dataOffset + frame * frameSize;

      for (var channel = 0; channel < channels; channel++) {
        final sampleOffset = frameOffset + channel * bytesPerSample;
        sum += _readPcmSample(data, sampleOffset, audioFormat, bitsPerSample);
      }

      samples[frame] = sum / channels;
    }

    return _WavAudio(samples: samples, sampleRate: sampleRate);
  }

  String _ascii(Uint8List bytes, int offset, int length) {
    return String.fromCharCodes(bytes.sublist(offset, offset + length));
  }

  double _readPcmSample(
    ByteData data,
    int offset,
    int audioFormat,
    int bitsPerSample,
  ) {
    if (audioFormat == 3 && bitsPerSample == 32) {
      return data.getFloat32(offset, Endian.little).clamp(-1.0, 1.0);
    }

    if (audioFormat != 1) {
      throw Exception("unsupported_wav_format_$audioFormat");
    }

    switch (bitsPerSample) {
      case 8:
        return (data.getUint8(offset) - 128) / 128.0;
      case 16:
        return data.getInt16(offset, Endian.little) / 32768.0;
      case 24:
        var value =
            data.getUint8(offset) |
            (data.getUint8(offset + 1) << 8) |
            (data.getUint8(offset + 2) << 16);
        if ((value & 0x800000) != 0) {
          value |= 0xff000000;
        }
        return value.toSigned(32) / 8388608.0;
      case 32:
        return data.getInt32(offset, Endian.little) / 2147483648.0;
      default:
        throw Exception("unsupported_bits_per_sample_$bitsPerSample");
    }
  }

  Float64List _resampleLinear(
    Float64List samples,
    int sourceSampleRate,
    int targetRate,
  ) {
    if (sourceSampleRate == targetRate) {
      return samples;
    }

    final outputLength = max(
      1,
      (samples.length * targetRate / sourceSampleRate).round(),
    );
    final output = Float64List(outputLength);
    final ratio = sourceSampleRate / targetRate;

    for (var i = 0; i < outputLength; i++) {
      final sourceIndex = i * ratio;
      final left = sourceIndex.floor().clamp(0, samples.length - 1);
      final right = min(left + 1, samples.length - 1);
      final fraction = sourceIndex - left;
      output[i] = samples[left] * (1.0 - fraction) + samples[right] * fraction;
    }

    return output;
  }

  dynamic _preclassifierInputTensor(Float64List samples) {
    final fixed = _fitAudioDuration(samples, preclassifierAudioSec);
    var melSpec = _melSpectrogram(
      fixed,
      nFft: preclassifierNFft,
      hopLength: preclassifierHopLength,
      nMels: preclassifierNMels,
      fMin: preclassifierFMin,
      fMax: targetSampleRate / 2,
      reflectPad: true,
      normalizeFilters: false,
    );

    melSpec = _powerToDb(melSpec);
    melSpec = _resizeTimeFrames(melSpec, preclassifierTargetFrames);
    melSpec = _normalizeMeanStd(melSpec);

    return _preclassifierTensorForShape(melSpec);
  }

  dynamic _legacyRgbInputTensor(Float64List samples) {
    final melSpec = _melSpectrogram(
      samples,
      nFft: legacyNFft,
      hopLength: legacyHopLength,
      nMels: legacyNMels,
      fMin: 0,
      fMax: targetSampleRate / 2,
      reflectPad: false,
      normalizeFilters: true,
    );
    return _spectrogramToInputTensor(melSpec);
  }

  Float64List _fitAudioDuration(Float64List samples, double seconds) {
    final targetLength = max(1, (targetSampleRate * seconds).round());

    if (samples.length == targetLength) {
      return samples;
    }

    final output = Float64List(targetLength);
    if (samples.length < targetLength) {
      for (var i = 0; i < samples.length; i++) {
        output[i] = samples[i];
      }
      return output;
    }

    final start = ((samples.length - targetLength) / 2).floor();
    for (var i = 0; i < targetLength; i++) {
      output[i] = samples[start + i];
    }
    return output;
  }

  List<Float64List> _melSpectrogram(
    Float64List samples, {
    required int nFft,
    required int hopLength,
    required int nMels,
    required double fMin,
    required double fMax,
    required bool reflectPad,
    required bool normalizeFilters,
  }) {
    final window = _hannWindow(nFft);
    final melFilterBank = _melFilterBank(
      nFft: nFft,
      nMels: nMels,
      fMin: fMin,
      fMax: fMax,
      normalizeFilters: normalizeFilters,
    );
    final pad = nFft ~/ 2;
    final padded = Float64List(samples.length + pad * 2);

    for (var i = 0; i < padded.length; i++) {
      final sourceIndex = i - pad;
      if (sourceIndex >= 0 && sourceIndex < samples.length) {
        padded[i] = samples[sourceIndex];
      } else if (reflectPad && samples.length > 1) {
        padded[i] = samples[_reflectIndex(sourceIndex, samples.length)];
      }
    }

    final frameCount = max(1, 1 + ((padded.length - nFft) ~/ hopLength));
    final melSpec = List.generate(nMels, (_) => Float64List(frameCount));
    final real = Float64List(nFft);
    final imag = Float64List(nFft);
    final power = Float64List((nFft ~/ 2) + 1);

    for (var frame = 0; frame < frameCount; frame++) {
      final start = frame * hopLength;

      for (var i = 0; i < nFft; i++) {
        real[i] = padded[start + i] * window[i];
        imag[i] = 0.0;
      }

      _fft(real, imag);

      for (var bin = 0; bin < power.length; bin++) {
        power[bin] = real[bin] * real[bin] + imag[bin] * imag[bin];
      }

      for (var mel = 0; mel < nMels; mel++) {
        var sum = 0.0;
        final weights = melFilterBank[mel];
        for (var bin = 0; bin < power.length; bin++) {
          sum += power[bin] * weights[bin];
        }
        melSpec[mel][frame] = sum;
      }
    }

    return melSpec;
  }

  int _reflectIndex(int index, int length) {
    if (length <= 1) {
      return 0;
    }

    var reflected = index;
    while (reflected < 0 || reflected >= length) {
      if (reflected < 0) {
        reflected = -reflected;
      }
      if (reflected >= length) {
        reflected = 2 * length - reflected - 2;
      }
    }
    return reflected;
  }

  List<Float64List> _powerToDb(List<Float64List> melSpec) {
    var maxDb = -double.infinity;
    final dbSpec = List.generate(
      melSpec.length,
      (mel) => Float64List(melSpec[mel].length),
    );

    for (var mel = 0; mel < melSpec.length; mel++) {
      for (var frame = 0; frame < melSpec[mel].length; frame++) {
        final power = max(1e-10, melSpec[mel][frame]);
        final db = 10.0 * log(power) / ln10;
        dbSpec[mel][frame] = db;
        if (db > maxDb) {
          maxDb = db;
        }
      }
    }

    final minDb = maxDb - topDb;
    for (var mel = 0; mel < dbSpec.length; mel++) {
      for (var frame = 0; frame < dbSpec[mel].length; frame++) {
        dbSpec[mel][frame] = dbSpec[mel][frame].clamp(minDb, maxDb);
      }
    }

    return dbSpec;
  }

  List<Float64List> _resizeTimeFrames(
    List<Float64List> spec,
    int targetFrames,
  ) {
    final sourceFrames = spec.first.length;
    if (sourceFrames == targetFrames) {
      return spec;
    }

    final output = List.generate(spec.length, (_) => Float64List(targetFrames));

    if (targetFrames == 1) {
      for (var mel = 0; mel < spec.length; mel++) {
        output[mel][0] = spec[mel][sourceFrames ~/ 2];
      }
      return output;
    }

    for (var mel = 0; mel < spec.length; mel++) {
      for (var frame = 0; frame < targetFrames; frame++) {
        final sourcePosition =
            frame * (sourceFrames - 1) / max(1, targetFrames - 1);
        final left = sourcePosition.floor().clamp(0, sourceFrames - 1);
        final right = min(left + 1, sourceFrames - 1);
        final fraction = sourcePosition - left;
        output[mel][frame] =
            spec[mel][left] * (1.0 - fraction) + spec[mel][right] * fraction;
      }
    }

    return output;
  }

  List<Float64List> _normalizeMeanStd(List<Float64List> spec) {
    var sum = 0.0;
    var count = 0;

    for (final row in spec) {
      for (final value in row) {
        sum += value;
        count++;
      }
    }

    final mean = count == 0 ? 0.0 : sum / count;
    var varianceSum = 0.0;

    for (final row in spec) {
      for (final value in row) {
        final delta = value - mean;
        varianceSum += delta * delta;
      }
    }

    final std = sqrt(varianceSum / max(1, count)).clamp(1e-5, double.infinity);
    final output = List.generate(
      spec.length,
      (_) => Float64List(spec.first.length),
    );

    for (var mel = 0; mel < spec.length; mel++) {
      for (var frame = 0; frame < spec[mel].length; frame++) {
        output[mel][frame] = (spec[mel][frame] - mean) / std;
      }
    }

    return output;
  }

  dynamic _preclassifierTensorForShape(List<Float64List> melSpec) {
    final nMels = melSpec.length;
    final frameCount = melSpec.first.length;

    if (_inputShape.length == 4 &&
        _inputShape[1] == 1 &&
        _inputShape[2] == nMels &&
        _inputShape[3] == frameCount) {
      return [
        [
          List.generate(nMels, (mel) {
            return List.generate(frameCount, (frame) => melSpec[mel][frame]);
          }),
        ],
      ];
    }

    if (_inputShape.length == 4 &&
        _inputShape[1] == nMels &&
        _inputShape[2] == frameCount &&
        _inputShape[3] == 1) {
      return [
        List.generate(nMels, (mel) {
          return List.generate(frameCount, (frame) => [melSpec[mel][frame]]);
        }),
      ];
    }

    throw Exception("unsupported_preclassifier_input_shape_$_inputShape");
  }

  Float64List _hannWindow(int length) {
    final window = Float64List(length);
    for (var i = 0; i < length; i++) {
      window[i] = 0.5 - 0.5 * cos(2.0 * pi * i / (length - 1));
    }
    return window;
  }

  List<Float64List> _melFilterBank({
    required int nFft,
    required int nMels,
    required double fMin,
    required double fMax,
    required bool normalizeFilters,
  }) {
    final fftBins = (nFft ~/ 2) + 1;
    final minMel = _hzToMel(fMin);
    final maxMel = _hzToMel(fMax);
    final melPoints = List<double>.generate(nMels + 2, (index) {
      return minMel + (maxMel - minMel) * index / (nMels + 1);
    });
    final hzPoints = melPoints.map(_melToHz).toList();
    final binPoints = hzPoints.map((hz) {
      return ((nFft + 1) * hz / targetSampleRate).floor().clamp(0, fftBins - 1);
    }).toList();

    final filters = List.generate(nMels, (_) => Float64List(fftBins));

    for (var mel = 0; mel < nMels; mel++) {
      final left = binPoints[mel];
      final center = binPoints[mel + 1];
      final right = binPoints[mel + 2];

      for (var bin = left; bin < center; bin++) {
        final denominator = max(1, center - left);
        filters[mel][bin] = (bin - left) / denominator;
      }

      for (var bin = center; bin < right; bin++) {
        final denominator = max(1, right - center);
        filters[mel][bin] = (right - bin) / denominator;
      }

      if (normalizeFilters) {
        final enorm = 2.0 / max(1e-12, hzPoints[mel + 2] - hzPoints[mel]);
        for (var bin = 0; bin < fftBins; bin++) {
          filters[mel][bin] *= enorm;
        }
      }
    }

    return filters;
  }

  double _hzToMel(num hz) => 2595.0 * log(1.0 + hz / 700.0) / ln10;

  double _melToHz(num mel) => 700.0 * (pow(10.0, mel / 2595.0) - 1.0);

  void _fft(Float64List real, Float64List imag) {
    final n = real.length;
    var j = 0;

    for (var i = 1; i < n; i++) {
      var bit = n >> 1;
      while ((j & bit) != 0) {
        j ^= bit;
        bit >>= 1;
      }
      j ^= bit;

      if (i < j) {
        final tempReal = real[i];
        final tempImag = imag[i];
        real[i] = real[j];
        imag[i] = imag[j];
        real[j] = tempReal;
        imag[j] = tempImag;
      }
    }

    for (var length = 2; length <= n; length <<= 1) {
      final angle = -2.0 * pi / length;
      final wLengthReal = cos(angle);
      final wLengthImag = sin(angle);

      for (var i = 0; i < n; i += length) {
        var wReal = 1.0;
        var wImag = 0.0;

        for (var k = 0; k < length ~/ 2; k++) {
          final even = i + k;
          final odd = even + length ~/ 2;
          final oddReal = real[odd] * wReal - imag[odd] * wImag;
          final oddImag = real[odd] * wImag + imag[odd] * wReal;

          real[odd] = real[even] - oddReal;
          imag[odd] = imag[even] - oddImag;
          real[even] += oddReal;
          imag[even] += oddImag;

          final nextWReal = wReal * wLengthReal - wImag * wLengthImag;
          final nextWImag = wReal * wLengthImag + wImag * wLengthReal;
          wReal = nextWReal;
          wImag = nextWImag;
        }
      }
    }
  }

  List<List<List<List<double>>>> _spectrogramToInputTensor(
    List<Float64List> melSpec,
  ) {
    var maxPower = 1e-10;
    for (final row in melSpec) {
      for (final value in row) {
        if (value > maxPower) {
          maxPower = value;
        }
      }
    }

    final frameCount = melSpec.first.length;
    final sourceImage = img.Image(width: frameCount, height: legacyNMels);
    final referenceDb = 10.0 * log(maxPower) / ln10;

    for (var y = 0; y < legacyNMels; y++) {
      final melIndex = legacyNMels - 1 - y;
      for (var x = 0; x < frameCount; x++) {
        final power = max(1e-10, melSpec[melIndex][x]);
        final db = (10.0 * log(power) / ln10 - referenceDb).clamp(-topDb, 0.0);
        final normalized = ((db + topDb) / topDb).clamp(0.0, 1.0);
        final color = _magmaColor(normalized);
        sourceImage.setPixelRgb(x, y, color[0], color[1], color[2]);
      }
    }

    final resized = img.copyResize(
      sourceImage,
      width: legacyInputSize,
      height: legacyInputSize,
      interpolation: img.Interpolation.linear,
    );

    return [
      List.generate(legacyInputSize, (y) {
        return List.generate(legacyInputSize, (x) {
          final pixel = resized.getPixel(x, y);
          return [
            pixel.r.toDouble() / 255.0,
            pixel.g.toDouble() / 255.0,
            pixel.b.toDouble() / 255.0,
          ];
        });
      }),
    ];
  }

  List<int> _magmaColor(double value) {
    const colors = [
      [0.001462, 0.000466, 0.013866],
      [0.078815, 0.054184, 0.211667],
      [0.232077, 0.059889, 0.437695],
      [0.390384, 0.100379, 0.501864],
      [0.550287, 0.161158, 0.505719],
      [0.716387, 0.214982, 0.475290],
      [0.868793, 0.287728, 0.409303],
      [0.967671, 0.439703, 0.359810],
      [0.994738, 0.624350, 0.427397],
      [0.995680, 0.812706, 0.572645],
      [0.987053, 0.991438, 0.749504],
    ];

    final scaled = value.clamp(0.0, 1.0) * (colors.length - 1);
    final lower = scaled.floor().clamp(0, colors.length - 1);
    final upper = min(lower + 1, colors.length - 1);
    final fraction = scaled - lower;

    return List.generate(3, (channel) {
      final mixed =
          colors[lower][channel] * (1.0 - fraction) +
          colors[upper][channel] * fraction;
      return (mixed * 255.0).round().clamp(0, 255);
    });
  }
}

class _WavAudio {
  final Float64List samples;
  final int sampleRate;

  const _WavAudio({required this.samples, required this.sampleRate});
}

enum _ModelProfile { none, preclassifier, legacyRgb }
