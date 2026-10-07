import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/ai_sound_classifier.dart';
import 'package:sound_detector_clean/classification_result.dart';

ClassificationResult classify(List<double> scores) {
  return ClassificationResult.fromFiveClassScores(
    modelId: 'v1_1_0_flower_drone_audio',
    modelVersion: '1.1.0',
    scores: scores,
  );
}

void main() {
  test('five-class index mapping is canonical and complete', () {
    final result = classify(<double>[0.03, 0.02, 0.92, 0.01, 0.02]);

    expect(result.classScores.keys, orderedEquals(canonicalSoundLabels));
    expect(result.classScores, <String, double>{
      'Airplane': 0.03,
      'Car': 0.02,
      'Drone': 0.92,
      'Electric_saw': 0.01,
      'Rainfall': 0.02,
    });
    expect(
      AiSoundClassifier.modelOptionForId(
        'v1_1_0_flower_drone_audio',
      ).classLabels,
      canonicalSoundLabels,
    );
  });

  test('Airplane maps to legacy aircraft target', () {
    final result = classify(<double>[0.70, 0.05, 0.10, 0.05, 0.10]);

    expect(result.canonicalLabel, 'Airplane');
    expect(result.operationalClass, 'aircraft');
    expect(result.label, 'aircraft');
    expect(result.isTarget, isTrue);
  });

  test('Drone maps to legacy drone target with no invented subtype', () {
    final result = classify(<double>[0.03, 0.02, 0.92, 0.01, 0.02]);

    expect(result.canonicalLabel, 'Drone');
    expect(result.operationalClass, 'drone');
    expect(result.isTarget, isTrue);
    expect(result.droneSubtype, isNull);
  });

  for (final entry in <String, List<double>>{
    'Car': <double>[0.05, 0.70, 0.10, 0.05, 0.10],
    'Electric_saw': <double>[0.05, 0.10, 0.10, 0.70, 0.05],
    'Rainfall': <double>[0.05, 0.10, 0.10, 0.05, 0.70],
  }.entries) {
    test('${entry.key} maps to legacy non_aircraft', () {
      final result = classify(entry.value);

      expect(result.canonicalLabel, entry.key);
      expect(result.operationalClass, 'non_aircraft');
      expect(result.label, 'non_aircraft');
      expect(result.isTarget, isFalse);
    });
  }

  test('aircraftProbability is Airplane plus Drone and confidence is top', () {
    final result = classify(<double>[0.24, 0.35, 0.31, 0.05, 0.05]);

    expect(result.canonicalLabel, 'Car');
    expect(result.confidence, 0.35);
    expect(result.aircraftProbability, closeTo(0.55, 1e-12));
    // This preserves the audited aggregate target threshold even when the
    // canonical top class is a non-target class.
    expect(result.operationalClass, 'drone');
    expect(result.isTarget, isTrue);
  });

  test('classification.v1 JSON round-trips without score changes', () {
    final original = classify(<double>[0.03, 0.02, 0.92, 0.01, 0.02]);
    final restored = ClassificationResult.fromJson(original.toJson());

    expect(restored.toJson(), original.toJson());
    expect(restored.modelId, 'v1_1_0_flower_drone_audio');
    expect(restored.modelVersion, '1.1.0');
    final legacy = AiInferenceResult.fromClassification(
      classification: restored,
      inferenceTimeMs: 42,
    );
    expect(legacy.label, 'drone');
    expect(legacy.aircraftProbability, restored.aircraftProbability);
    expect(legacy.confidence, restored.confidence);
  });
}
