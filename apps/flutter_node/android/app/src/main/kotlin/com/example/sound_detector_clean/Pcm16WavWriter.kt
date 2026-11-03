package com.example.sound_detector_clean

import java.io.RandomAccessFile

/** Identical PCM16 little-endian payload, one bulk write per complete window. */
internal object Pcm16WavWriter {
    fun encode(samples: ShortArray): ByteArray {
        val bytes = ByteArray(samples.size * 2)
        for (i in samples.indices) {
            val value = samples[i].toInt()
            bytes[i * 2] = (value and 0xff).toByte()
            bytes[i * 2 + 1] = ((value shr 8) and 0xff).toByte()
        }
        return bytes
    }

    fun write(wav: RandomAccessFile, samples: ShortArray) {
        wav.write(encode(samples))
    }
}
