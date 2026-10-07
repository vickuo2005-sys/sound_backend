import 'package:flutter_test/flutter_test.dart';
import 'package:sound_detector_clean/listening_elapsed_counter.dart';

void main() {
  test('elapsed starts at zero and advances only while listening', () {
    final elapsed = ListeningElapsedCounter();

    elapsed.start();
    expect(elapsed.seconds, 0);

    elapsed.tick(isListening: true);
    elapsed.tick(isListening: true);
    expect(elapsed.seconds, 2);

    elapsed.tick(isListening: false);
    expect(elapsed.seconds, 2);
  });

  test('stopping resets elapsed time to zero', () {
    final elapsed = ListeningElapsedCounter()..start();
    elapsed.tick(isListening: true);
    elapsed.tick(isListening: true);
    elapsed.tick(isListening: true);

    elapsed.stop();

    expect(elapsed.seconds, 0);
  });

  test('a new listening session starts from zero', () {
    final elapsed = ListeningElapsedCounter()..start();
    elapsed.tick(isListening: true);
    elapsed.stop();

    elapsed.start();

    expect(elapsed.seconds, 0);
  });
}
