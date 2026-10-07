class ListeningElapsedCounter {
  int _seconds = 0;

  int get seconds => _seconds;

  void start() {
    _seconds = 0;
  }

  void tick({required bool isListening}) {
    if (isListening) _seconds++;
  }

  void stop() {
    _seconds = 0;
  }
}
