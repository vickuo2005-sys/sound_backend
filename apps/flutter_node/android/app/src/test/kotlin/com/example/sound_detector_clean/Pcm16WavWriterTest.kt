package com.example.sound_detector_clean

import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import org.junit.Assert.*
import org.junit.Test

class Pcm16WavWriterTest {
    @Test fun preservesEverySignedPcm16Value() {
        val samples = ShortArray(65536) { (it - 32768).toShort() }
        val expected = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (sample in samples) expected.putShort(sample)
        assertArrayEquals(expected.array(), Pcm16WavWriter.encode(samples))
    }

    @Test fun threeSecondWindowUsesOneBulkWriteAndNoSingleByteWrites() {
        val file = File.createTempFile("pcm16-writer", ".wav")
        try {
            val samples = ShortArray(48000) { ((it * 197) % 65536 - 32768).toShort() }
            val wav = object : RandomAccessFile(file, "rw") {
                var bulkCalls = 0
                var singleCalls = 0
                override fun write(bytes: ByteArray) { bulkCalls++; super.write(bytes) }
                override fun write(value: Int) { singleCalls++; super.write(value) }
            }
            wav.use {
                Pcm16WavWriter.write(it, samples)
                assertEquals(1, it.bulkCalls)
                assertEquals(0, it.singleCalls)
                assertEquals(96000L, it.length())
            }
            assertArrayEquals(Pcm16WavWriter.encode(samples), file.readBytes())
        } finally { file.delete() }
    }

    @Test fun emptyInputProducesEmptyPayload() {
        assertEquals(0, Pcm16WavWriter.encode(shortArrayOf()).size)
    }
}
