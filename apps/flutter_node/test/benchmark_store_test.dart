import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sound_detector_clean/benchmark/store.dart';

void main() {
  late Database db;
  setUpAll(() {
    sqfliteFfiInit();
  });
  setUp(() async {
    db = await databaseFactoryFfi.openDatabase(inMemoryDatabasePath);
    await db.execute(BenchmarkStore.schema);
  });
  tearDown(() => db.close());
  final session = <String, dynamic>{'session_id': 'own-session'};
  final batch = <String, dynamic>{
    'status': 'completed',
    'reason': 'completed',
    'runs': [],
  };
  test('offline failure preserves complete payload and uses backoff', () async {
    final store = BenchmarkStore(
      db,
      clientFactory: () => MockClient((_) async => throw Exception('offline')),
    );
    await store.save(session, batch, 'secret');
    await store.retry('https://test.invalid');
    final row = (await store.latest())!;
    expect(jsonDecode(row['batch'] as String), batch);
    expect(row['uploaded'], 0);
    expect(row['attempts'], 1);
    expect(
      row['next_attempt'] as int,
      greaterThan(DateTime.now().millisecondsSinceEpoch),
    );
    await store.retry('https://test.invalid');
    expect((await store.latest())!['attempts'], 1);
  });
  test(
    'storage acknowledgment required for both requests; redirects disabled',
    () async {
      var calls = 0;
      final store = BenchmarkStore(
        db,
        clientFactory: () => MockClient((request) async {
          calls++;
          expect(request.followRedirects, false);
          expect(request.headers['authorization'], 'Bearer secret');
          return http.Response(
            jsonEncode({'stored': true, 'session_id': 'own-session'}),
            200,
          );
        }),
      );
      await store.save(session, batch, 'secret');
      await store.retry('https://test.invalid');
      expect(calls, 2);
      expect((await store.latest())!['uploaded'], 1);
    },
  );
  test('HTTP 200 without stored true is not successful upload', () async {
    final store = BenchmarkStore(
      db,
      clientFactory: () => MockClient((_) async => http.Response('{}', 200)),
    );
    await store.save(session, batch, 'secret');
    await store.retry('https://test.invalid');
    expect((await store.latest())!['uploaded'], 0);
  });
  test(
    'unfinished checkpoint waits for recovery then remains exportable',
    () async {
      final store = BenchmarkStore(db);
      await store.save(session, {
        'status': 'interrupted',
        'reason': 'in_progress',
        'runs': [],
      }, 'secret');
      expect((await store.latest())!['next_attempt'], 9223372036854775807);
      await store.recover();
      expect(
        jsonDecode((await store.latest())!['batch'] as String)['reason'],
        'process_interrupted',
      );
      expect((await store.latest())!['next_attempt'], 0);
    },
  );
  test('bounded retries retain data and HTTP endpoints are refused', () async {
    var calls = 0;
    final store = BenchmarkStore(
      db,
      clientFactory: () => MockClient((_) async {
        calls++;
        throw Exception('offline');
      }),
    );
    await store.save(session, batch, 'secret');
    await store.retry('http://test.invalid');
    expect(calls, 0);
    await db.update('results', {'attempts': 10});
    await store.retry('https://test.invalid');
    expect(calls, 0);
    expect((await store.latest())!['batch'], jsonEncode(batch));
  });
}
