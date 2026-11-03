import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';
import 'stats.dart';

class BenchmarkStore {
  final Database db;
  final http.Client Function() clientFactory;
  BenchmarkStore(this.db, {http.Client Function()? clientFactory})
    : clientFactory = clientFactory ?? http.Client.new;
  static const schema =
      'CREATE TABLE results(id TEXT PRIMARY KEY, session TEXT NOT NULL, batch TEXT NOT NULL, secret TEXT NOT NULL, uploaded INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0, next_attempt INTEGER NOT NULL DEFAULT 0)';
  static Future<BenchmarkStore> open() async {
    final db = await openDatabase(
      path.join(await getDatabasesPath(), 'benchmark_v1.db'),
      version: 1,
      onCreate: (d, _) => d.execute(schema),
    );
    return BenchmarkStore(db);
  }

  Future<void> save(
    Map<String, dynamic> session,
    Map<String, dynamic> batch,
    String secret,
  ) async {
    await db.transaction((txn) async {
      final existing = await txn.query(
        'results',
        where: 'id=?',
        whereArgs: [session['session_id']],
      );
      final usage = await txn.rawQuery(
        'SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(session)+LENGTH(batch)),0) AS bytes FROM results',
      );
      if (existing.isEmpty && (usage.first['n'] as int) >= 100) {
        throw StateError('本機已保存 100 次測試，請先匯出及清理 App 資料');
      }
      if ((usage.first['bytes'] as int) + jsonEncode(batch).length >
          50 * 1024 * 1024) {
        throw StateError('本機結果儲存空間已滿');
      }
      await txn.insert('results', {
        'id': session['session_id'],
        'session': jsonEncode(session),
        'batch': jsonEncode(batch),
        'secret': secret,
        'uploaded': 0,
        'attempts': 0,
        'next_attempt':
            batch['status'] == 'interrupted' && batch['reason'] == 'in_progress'
            ? 9223372036854775807
            : 0,
      }, conflictAlgorithm: ConflictAlgorithm.replace);
    });
  }

  Future<Map<String, Object?>?> latest() async {
    final rows = await db.query('results', orderBy: 'rowid DESC', limit: 1);
    return rows.isEmpty ? null : rows.first;
  }

  Future<void> recover() async {
    await db.transaction((txn) async {
      final rows = await txn.query(
        'results',
        where: 'next_attempt=9223372036854775807',
      );
      for (final row in rows) {
        final batch =
            jsonDecode(row['batch'] as String) as Map<String, dynamic>;
        batch['reason'] = 'process_interrupted';
        final runs = batch['runs'] as List;
        if (runs.isNotEmpty) {
          (runs.last['errors'] as List).add('process_interrupted');
        }
        await txn.update(
          'results',
          {'next_attempt': 0, 'batch': jsonEncode(batch)},
          where: 'id=?',
          whereArgs: [row['id']],
        );
      }
    });
  }

  bool _uploading = false;
  Future<void> retry(String base) async {
    if (_uploading || base.isEmpty) return;
    final uri = Uri.tryParse(base);
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty) {
      return;
    }
    _uploading = true;
    try {
      final now = DateTime.now().millisecondsSinceEpoch;
      final rows = await db.query(
        'results',
        where: 'uploaded=0 AND attempts<10 AND next_attempt<=?',
        whereArgs: [now],
        limit: 5,
      );
      for (final row in rows) {
        final attempts = (row['attempts'] as int) + 1;
        await db.update(
          'results',
          {
            'attempts': attempts,
            'next_attempt':
                now + min(21600000, 30000 * pow(2, attempts).toInt()),
          },
          where: 'id=?',
          whereArgs: [row['id']],
        );
        try {
          final headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ${row['secret']}',
          };
          Future<void> post(String route, String body) async {
            final client = clientFactory();
            try {
              final request =
                  http.Request(
                      'POST',
                      Uri.parse('${base.replaceAll(RegExp(r'/+$'), '')}$route'),
                    )
                    ..followRedirects = false
                    ..headers.addAll(headers)
                    ..body = body;
              final streamed = await client
                  .send(request)
                  .timeout(const Duration(seconds: 20));
              final response = await http.Response.fromStream(
                streamed,
              ).timeout(const Duration(seconds: 20));
              if (response.statusCode != 200) {
                throw HttpException('HTTP ${response.statusCode}');
              }
              final data = jsonDecode(response.body) as Map<String, dynamic>;
              if (data['stored'] != true || data['session_id'] != row['id']) {
                throw const FormatException('missing storage acknowledgment');
              }
            } finally {
              client.close();
            }
          }

          await post('/benchmark/sessions', row['session'] as String);
          await post('/benchmark/results/batch', row['batch'] as String);
          await db.update(
            'results',
            {'uploaded': 1},
            where: 'id=?',
            whereArgs: [row['id']],
          );
        } catch (_) {
          /* Never delete a result because upload failed. */
        }
      }
    } finally {
      _uploading = false;
    }
  }

  Future<List<String>> export(
    Map<String, dynamic> session,
    Map<String, dynamic> batch,
  ) async {
    final dir = Directory(
      path.join(
        (await getApplicationDocumentsDirectory()).path,
        'benchmark_exports',
      ),
    );
    await dir.create(recursive: true);
    for (final f in dir.listSync().whereType<File>()) {
      await f.delete();
    }
    // Include all local sessions so previous completed results remain accessible.
    final records = await db.query('results', orderBy: 'rowid');
    final results = [
      for (final row in records)
        <String, dynamic>{
          'session': jsonDecode(row['session'] as String),
          'batch': jsonDecode(row['batch'] as String),
        },
    ];
    if (results.isEmpty) results.add({'session': session, 'batch': batch});
    for (final record in results) {
      final runs = (record['batch']['runs'] as List)
          .cast<Map<String, dynamic>>();
      record['decisions'] = decide(runs);
      record['statistics'] = [
        for (final r in runs) {'run_id': r['run_id'], ...runStatistics(r)},
      ];
    }
    final stem = path.join(dir.path, session['session_id'] as String);
    final json = File('$stem.json');
    await json.writeAsString(
      const JsonEncoder.withIndent('  ').convert({'results': results}),
      flush: true,
    );
    final rows = <List<Object?>>[
      [
        'session_id',
        'model_id',
        'model_sha256',
        'hop_ms',
        'phase',
        'sequence',
        'ready_native_ms',
        ...timingMetrics,
        'success',
        'generated',
        'processed',
        'dropped',
        'passed',
        'reasons',
      ],
    ];
    for (final record in results) {
      final s = record['session'];
      final runs = (record['batch']['runs'] as List)
          .cast<Map<String, dynamic>>();
      if (runs.isEmpty) {
        rows.add([
          s['session_id'],
          s['model_id'],
          s['model_sha256'],
          ...List.filled(16, ''),
          record['batch']['reason'],
        ]);
      }
      for (final r in runs) {
        final e = evaluateRun(r);
        final samples = r['samples'] as List;
        for (final sample
            in samples.isEmpty ? [<String, dynamic>{}] : samples) {
          rows.add([
            s['session_id'],
            s['model_id'],
            s['model_sha256'],
            r['hop_ms'],
            r['phase'],
            sample['sequence'],
            sample['ready_native_ms'],
            ...timingMetrics.map((k) => sample[k]),
            sample['success'],
            r['generated'],
            r['processed'],
            r['dropped'],
            e['passed'],
            (e['reasons'] as List).join(';'),
          ]);
        }
      }
    }
    final csv = File('$stem.csv');
    await csv.writeAsString(
      '\ufeff${rows.map((r) => r.map(csvCell).join(',')).join('\r\n')}',
      flush: true,
    );
    return [json.path, csv.path];
  }
}
