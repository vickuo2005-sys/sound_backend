import 'dart:collection';

const String classificationV1SchemaVersion = 'classification.v1';
const List<String> canonicalSoundLabels = <String>[
  'Airplane',
  'Car',
  'Drone',
  'Electric_saw',
  'Rainfall',
];

/// One immutable interpretation of the five-class model output.
///
/// [confidence] and [classScores] are model scores. They are not asserted to
/// be statistically calibrated real-world probabilities.
class ClassificationResult {
  ClassificationResult._({
    required this.modelId,
    required this.modelVersion,
    required this.canonicalLabel,
    required this.confidence,
    required Map<String, double> classScores,
    required this.operationalClass,
    required this.aircraftProbability,
    required this.isTarget,
    required this.droneSubtype,
  }) : classScores = UnmodifiableMapView<String, double>(classScores);

  factory ClassificationResult.fromFiveClassScores({
    required String modelId,
    required String modelVersion,
    required List<double> scores,
    double targetThreshold = 0.5,
  }) {
    if (scores.length != canonicalSoundLabels.length) {
      throw ArgumentError.value(
        scores.length,
        'scores',
        'five canonical scores are required',
      );
    }

    final checkedScores = <double>[];
    for (final score in scores) {
      if (!score.isFinite || score < 0.0 || score > 1.0) {
        throw ArgumentError.value(score, 'scores', 'must be finite 0..1');
      }
      checkedScores.add(score);
    }

    var topIndex = 0;
    for (var index = 1; index < checkedScores.length; index += 1) {
      if (checkedScores[index] > checkedScores[topIndex]) {
        topIndex = index;
      }
    }

    final aircraftScore = checkedScores[0];
    final droneScore = checkedScores[2];
    final aircraftProbability = (aircraftScore + droneScore).clamp(0.0, 1.0);
    final isTarget = aircraftProbability > targetThreshold;
    final operationalClass = isTarget
        ? (droneScore > aircraftScore ? 'drone' : 'aircraft')
        : 'non_aircraft';

    return ClassificationResult._(
      modelId: modelId,
      modelVersion: modelVersion,
      canonicalLabel: canonicalSoundLabels[topIndex],
      confidence: checkedScores[topIndex],
      classScores: <String, double>{
        for (var index = 0; index < canonicalSoundLabels.length; index += 1)
          canonicalSoundLabels[index]: checkedScores[index],
      },
      operationalClass: operationalClass,
      aircraftProbability: aircraftProbability,
      isTarget: isTarget,
      droneSubtype: null,
    );
  }

  factory ClassificationResult.fromJson(Map<String, dynamic> json) {
    if (json['schema_version'] != classificationV1SchemaVersion) {
      throw const FormatException('unsupported classification schema');
    }
    final rawScores = json['class_scores'];
    if (rawScores is! Map) {
      throw const FormatException('classification class_scores is required');
    }
    final scoreKeys = rawScores.keys.map((key) => key.toString()).toSet();
    if (scoreKeys.length != canonicalSoundLabels.length ||
        !scoreKeys.containsAll(canonicalSoundLabels)) {
      throw const FormatException('classification score keys are invalid');
    }
    final scores = canonicalSoundLabels
        .map((label) {
          final value = rawScores[label];
          if (value is! num) {
            throw const FormatException('classification score must be numeric');
          }
          return value.toDouble();
        })
        .toList(growable: false);
    final rebuilt = ClassificationResult.fromFiveClassScores(
      modelId: json['model_id']?.toString() ?? '',
      modelVersion: json['model_version']?.toString() ?? '',
      scores: scores,
    );
    final confidence = json['confidence'];
    final aircraftProbability = json['aircraft_probability'];
    if (confidence is! num || aircraftProbability is! num) {
      throw const FormatException('classification summary scores are required');
    }
    final confidenceValue = confidence.toDouble();
    final aircraftProbabilityValue = aircraftProbability.toDouble();
    if (!confidenceValue.isFinite || !aircraftProbabilityValue.isFinite) {
      throw const FormatException('classification summary scores are invalid');
    }

    // Local persistence must round-trip the original decision exactly. The
    // payload was produced by this app, so inconsistent data is rejected
    // instead of silently changing event semantics after a restart.
    if (json['model_label']?.toString() != rebuilt.canonicalLabel ||
        json['operational_class']?.toString() != rebuilt.operationalClass ||
        json['is_target'] != rebuilt.isTarget ||
        json['drone_subtype'] != null ||
        (confidenceValue - rebuilt.confidence).abs() > 1e-9 ||
        (aircraftProbabilityValue - rebuilt.aircraftProbability).abs() > 1e-9) {
      throw const FormatException('classification decision is inconsistent');
    }
    return ClassificationResult._(
      modelId: json['model_id']?.toString() ?? '',
      modelVersion: json['model_version']?.toString() ?? '',
      canonicalLabel: json['model_label'].toString(),
      confidence: confidenceValue,
      classScores: <String, double>{
        for (var index = 0; index < canonicalSoundLabels.length; index += 1)
          canonicalSoundLabels[index]: scores[index],
      },
      operationalClass: json['operational_class'].toString(),
      aircraftProbability: aircraftProbabilityValue,
      isTarget: json['is_target'] as bool,
      droneSubtype: null,
    );
  }

  static ClassificationResult? fromJsonOrNull(dynamic value) {
    if (value is! Map) return null;
    try {
      return ClassificationResult.fromJson(Map<String, dynamic>.from(value));
    } on FormatException {
      return null;
    } on ArgumentError {
      return null;
    }
  }

  final String modelId;
  final String modelVersion;
  final String canonicalLabel;
  final double confidence;
  final Map<String, double> classScores;
  final String operationalClass;
  final double aircraftProbability;
  final bool isTarget;

  /// Reserved for a future subtype model. BI-1 never invents this value.
  final String? droneSubtype;

  /// Compatibility getter used by the existing alert and upload code.
  String get label => operationalClass;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'schema_version': classificationV1SchemaVersion,
    'model_id': modelId,
    'model_version': modelVersion,
    'model_label': canonicalLabel,
    'confidence': confidence,
    'class_scores': <String, double>{...classScores},
    'operational_class': operationalClass,
    'aircraft_probability': aircraftProbability,
    'is_target': isTarget,
    'drone_subtype': droneSubtype,
  };
}
