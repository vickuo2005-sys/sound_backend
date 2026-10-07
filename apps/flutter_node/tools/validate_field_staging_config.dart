import 'dart:convert';
import 'dart:io';

import 'package:sound_detector_clean/field_staging_validation.dart';

Future<void> main(List<String> arguments) async {
  if (arguments.length != 3 || arguments[1] != '--approved-host') {
    stderr.writeln(
      'Usage: dart run tools/validate_field_staging_config.dart '
      '<config.json> --approved-host <staging-hostname>',
    );
    exitCode = 2;
    return;
  }

  final file = File(arguments.first);
  final approvedHost = arguments[2].trim().toLowerCase();
  if (approvedHost.isEmpty || approvedHost.contains('://')) {
    stderr.writeln(
      jsonEncode(<String, dynamic>{
        'valid': false,
        'error': 'invalid_approved_host',
        'detail': 'Pass a hostname only, without scheme or path.',
      }),
    );
    exitCode = 2;
    return;
  }
  if (!await file.exists()) {
    stderr.writeln(
      jsonEncode(<String, dynamic>{'valid': false, 'error': 'missing_file'}),
    );
    exitCode = 2;
    return;
  }

  try {
    final decoded = jsonDecode(await file.readAsString());
    if (decoded is! Map) {
      throw const FormatException('root must be a JSON object');
    }
    final validation = validateFieldStagingConfig(
      Map<String, dynamic>.from(decoded),
      approvedStagingHosts: <String>{approvedHost},
    );
    stdout.writeln(jsonEncode(validation.toSafeJson()));
    if (!validation.valid) exitCode = 1;
  } on FormatException catch (error) {
    stderr.writeln(
      jsonEncode(<String, dynamic>{
        'valid': false,
        'error': 'invalid_json',
        'detail': error.message,
      }),
    );
    exitCode = 2;
  }
}
