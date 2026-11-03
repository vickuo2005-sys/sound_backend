package com.example.sound_detector_clean

/** Pure configuration guard used by the native AudioRecord pipeline. */
internal object BenchmarkHop {
    val allowed = listOf(1500, 1000, 750, 500, 350, 250, 200, 150, 100)
    fun canStart(hop: Int, listening: Boolean, captureAlive: Boolean, pending: Int): Boolean =
        hop in allowed && !listening && !captureAlive && pending == 0
    fun samples(hop: Int): Int {
        require(hop in allowed)
        return 16000 * hop / 1000
    }
}
