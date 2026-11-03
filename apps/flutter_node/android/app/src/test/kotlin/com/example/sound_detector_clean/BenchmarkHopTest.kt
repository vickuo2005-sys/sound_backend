package com.example.sound_detector_clean

import org.junit.Assert.*
import org.junit.Test

class BenchmarkHopTest {
    @Test fun everyHopUsesExactNativeSampleCount() {
        for (hop in BenchmarkHop.allowed) {
            assertEquals(hop * 16, BenchmarkHop.samples(hop))
            assertTrue(BenchmarkHop.canStart(hop, false, false, 0))
        }
        assertEquals(1600, BenchmarkHop.samples(100))
        assertEquals(24000, BenchmarkHop.samples(1500))
    }
    @Test fun rejectsChangesUntilCaptureAndWriterAreDrained() {
        assertFalse(BenchmarkHop.canStart(100, true, false, 0))
        assertFalse(BenchmarkHop.canStart(100, false, true, 0))
        assertFalse(BenchmarkHop.canStart(100, false, false, 1))
        assertFalse(BenchmarkHop.canStart(42, false, false, 0))
    }
    @Test(expected = IllegalArgumentException::class)
    fun unsupportedHopCannotBeConverted() { BenchmarkHop.samples(42) }
}
