package com.example.sound_detector_clean

import android.Manifest
import android.app.ActivityManager
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.SystemClock
import android.view.WindowManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.RandomAccessFile
import java.text.SimpleDateFormat
import java.util.ArrayDeque
import java.util.Date
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.concurrent.thread
import kotlin.math.roundToLong
import kotlin.math.sqrt

class MainActivity : FlutterActivity() {

    private val CHANNEL = "sound_channel"

    private var methodChannel: MethodChannel? = null
    private var audioRecord: AudioRecord? = null

    @Volatile
    private var isListening = false

    @Volatile
    private var isEventRecording = false

    @Volatile
    private var isLiveAudioStreaming = false

    @Volatile
    private var isDetectionEnabled = true

    private val sampleRate = 16000
    private val startThresholdRms = 1500.0
    private val continueThresholdRms = 900.0
    private val requiredStartBuffers = 2

    private val preBufferSeconds = 2
    private val silenceEndMs = 700
    private val maxEventMs = 4000

    private val bytesPerSample = 2
    private val channelCount = 1
    private val liveAudioFrameDurationMs = 40
    private val liveAudioFrameSamples = sampleRate * liveAudioFrameDurationMs / 1000
    private val slidingWindowMs = 3000
    // Keep 50% overlap between complete 3-second model windows. The archived
    // 500 ms hop overloaded WAV writes; 1.5 seconds retains overlap at one third
    // of that write rate.
    private val slidingHopMs = 1500
    private val slidingWindowSamples = sampleRate * slidingWindowMs / 1000
    private val slidingHopSamples = sampleRate * slidingHopMs / 1000

    private val preBuffer = ArrayDeque<Short>()
    private val slidingWindowBuffer = ShortArray(slidingWindowSamples)
    private val slidingWindowWriteExecutor: ExecutorService =
        Executors.newSingleThreadExecutor()
    private val liveAudioFrameLock = Any()
    private val liveAudioFrameBuffer = ShortArray(liveAudioFrameSamples)

    private var currentWavFile: RandomAccessFile? = null
    private var currentFilePath: String? = null
    private var currentEventTimeText: String? = null
    private var currentEventStartTimeMs: Long = 0L
    private var currentCaptureStartTimeMs: Long = 0L
    private var currentCaptureStartGlobalSample: Long = 0L
    private var currentEventStartSample: Long = 0L
    private var currentRmsPeakSample: Long? = null
    private var currentEventPeakRms: Double = 0.0
    private var currentEventPeakOffsetMs: Double? = null

    private var dataBytesWritten = 0
    private var silentSamples = 0
    private var eventSamplesWritten = 0
    private var listeningStartTimeMs = 0L
    private var totalSamplesRead = 0L
    private var slidingSamplesSeen = 0L
    private var nextSlidingWindowEndSample = slidingWindowSamples.toLong()
    private var slidingWindowSequence = 0L
    private var liveAudioFrameFill = 0
    private var liveAudioFrameStartGlobalSample = 0L
    private var loudBufferCount = 0

    private data class SlidingWindowSnapshot(
        val samples: ShortArray,
        val startGlobalSample: Long,
        val endGlobalSample: Long,
        val sequence: Long,
        val readyTimeMs: Long,
        val readyMonotonicMs: Long
    )

    private data class SlidingWindowStats(
        val avgRms: Double,
        val peakRms: Double,
        val peakSample: Long
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    override fun onDestroy() {
        slidingWindowWriteExecutor.shutdownNow()
        super.onDestroy()
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        methodChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)

        methodChannel?.setMethodCallHandler { call, result ->
            when (call.method) {
                "startListening" -> {
                    if (hasMicPermission()) {
                        startListening()
                    } else {
                        requestMicPermission()
                        sendToFlutter("permission_denied", null)
                    }

                    result.success(null)
                }

                "stopListening" -> {
                    stopListening()
                    result.success(null)
                }

                "startLiveAudio" -> {
                    resetLiveAudioFrameBuffer()
                    isLiveAudioStreaming = true
                    result.success(null)
                }

                "stopLiveAudio" -> {
                    isLiveAudioStreaming = false
                    resetLiveAudioFrameBuffer()
                    result.success(null)
                }

                "setDetectionEnabled" -> {
                    val enabled = call.arguments as? Boolean ?: true
                    setDetectionEnabled(enabled)
                    result.success(null)
                }

                "startForegroundNodeService" -> {
                    try {
                        SoundNodeForegroundService.start(this)
                        result.success(true)
                    } catch (error: Exception) {
                        result.error("foreground_service_failed", error.message, null)
                    }
                }

                "stopForegroundNodeService" -> {
                    try {
                        SoundNodeForegroundService.stop(this)
                        result.success(true)
                    } catch (error: Exception) {
                        result.error("foreground_service_stop_failed", error.message, null)
                    }
                }

                "enterKioskMode" -> {
                    result.success(enterKioskMode())
                }

                "exitKioskMode" -> {
                    result.success(exitKioskMode())
                }

                "isKioskModeAvailable" -> {
                    result.success(isKioskModeAvailable())
                }

                else -> result.notImplemented()
            }
        }
    }

    private fun isKioskModeAvailable(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) return false

        return try {
            val devicePolicyManager =
                getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
            devicePolicyManager.isLockTaskPermitted(packageName)
        } catch (_: Exception) {
            false
        }
    }

    private fun currentLockTaskState(): Int {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return 0

        return try {
            val activityManager = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
            activityManager.lockTaskModeState
        } catch (_: Exception) {
            0
        }
    }

    private fun enterKioskMode(): HashMap<String, Any> {
        val response = hashMapOf<String, Any>(
            "success" to false,
            "permitted" to isKioskModeAvailable(),
            "state" to currentLockTaskState()
        )

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) {
            response["message"] = "Lock Task requires Android 5.0+"
            return response
        }

        return try {
            startLockTask()
            response["success"] = true
            response["state"] = currentLockTaskState()
            response
        } catch (error: Exception) {
            response["message"] = error.message ?: "Lock Task failed"
            response
        }
    }

    private fun exitKioskMode(): HashMap<String, Any> {
        val response = hashMapOf<String, Any>(
            "success" to false,
            "state" to currentLockTaskState()
        )

        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) {
            response["message"] = "Lock Task requires Android 5.0+"
            return response
        }

        return try {
            stopLockTask()
            response["success"] = true
            response["state"] = currentLockTaskState()
            response
        } catch (error: Exception) {
            response["message"] = error.message ?: "Exit Lock Task failed"
            response
        }
    }

    private fun hasMicPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun requestMicPermission() {
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.RECORD_AUDIO),
            1001
        )
    }

    private fun startListening() {
        if (isListening) return

        val minBufferSize = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        if (minBufferSize <= 0) {
            sendToFlutter("audio_error", null)
            return
        }

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            minBufferSize
        )

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            audioRecord?.release()
            audioRecord = null
            sendToFlutter("audio_error", null)
            return
        }

        isListening = true
        isEventRecording = false
        isDetectionEnabled = true

        preBuffer.clear()
        silentSamples = 0
        loudBufferCount = 0
        eventSamplesWritten = 0
        dataBytesWritten = 0
        listeningStartTimeMs = 0L
        totalSamplesRead = 0L
        resetSlidingWindowRecorder()
        resetLiveAudioFrameBuffer()

        val buffer = ShortArray(minBufferSize)

        try {
            audioRecord?.startRecording()
            listeningStartTimeMs = System.currentTimeMillis()
        } catch (_: Exception) {
            sendToFlutter("audio_error", null)
            releaseAudioRecord()
            isListening = false
            return
        }

        thread {
            try {
                while (isListening) {
                    val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0

                    if (read > 0) {
                        val bufferStartGlobalSample = totalSamplesRead
                        processAudioBuffer(buffer, read, bufferStartGlobalSample)
                        totalSamplesRead += read.toLong()
                    }
                }
            } catch (error: Exception) {
                android.util.Log.e("SoundNodeAudio", "audio read/process failed", error)
                sendToFlutter("audio_error", null)
            } finally {
                releaseAudioRecord()
            }
        }
    }

    private fun stopListening() {
        isLiveAudioStreaming = false
        resetLiveAudioFrameBuffer()
        isDetectionEnabled = false
        loudBufferCount = 0
        isListening = false
    }

    private fun setDetectionEnabled(enabled: Boolean) {
        isDetectionEnabled = enabled
        if (!enabled) {
            loudBufferCount = 0
            resetSlidingWindowRecorder()
            sendToFlutter("silent", null)
        }
    }

    private fun processAudioBuffer(buffer: ShortArray, read: Int, bufferStartGlobalSample: Long) {
        val rms = calculateRms(buffer, read)

        sendToFlutter("rms_update", rms)
        emitLiveAudioFrame(buffer, read, bufferStartGlobalSample)

        if (!isDetectionEnabled) {
            loudBufferCount = 0
            sendToFlutter("silent", null)
            return
        }

        appendToSlidingWindow(buffer, read)
        emitReadySlidingWindows()
    }

    private fun calculateRms(buffer: ShortArray, read: Int): Double {
        var sum = 0.0

        for (i in 0 until read) {
            val sample = buffer[i].toDouble()
            sum += sample * sample
        }

        return sqrt(sum / read)
    }

    private fun appendToPreBuffer(buffer: ShortArray, read: Int) {
        val maxPreBufferSamples = sampleRate * preBufferSeconds

        for (i in 0 until read) {
            preBuffer.addLast(buffer[i])

            while (preBuffer.size > maxPreBufferSamples) {
                preBuffer.removeFirst()
            }
        }
    }

    private fun resetSlidingWindowRecorder() {
        java.util.Arrays.fill(slidingWindowBuffer, 0.toShort())
        slidingSamplesSeen = 0L
        nextSlidingWindowEndSample = slidingWindowSamples.toLong()
        slidingWindowSequence = 0L
    }

    private fun appendToSlidingWindow(buffer: ShortArray, read: Int) {
        for (i in 0 until read) {
            val index = (slidingSamplesSeen % slidingWindowSamples).toInt()
            slidingWindowBuffer[index] = buffer[i]
            slidingSamplesSeen += 1
        }
    }

    private fun emitReadySlidingWindows() {
        val snapshots = mutableListOf<SlidingWindowSnapshot>()

        while (slidingSamplesSeen >= nextSlidingWindowEndSample) {
            val endGlobalSample = nextSlidingWindowEndSample
            val startGlobalSample = endGlobalSample - slidingWindowSamples
            val samples = ShortArray(slidingWindowSamples)

            for (i in 0 until slidingWindowSamples) {
                val globalSample = startGlobalSample + i.toLong()
                val sourceIndex = (globalSample % slidingWindowSamples).toInt()
                samples[i] = slidingWindowBuffer[sourceIndex]
            }

            snapshots.add(
                SlidingWindowSnapshot(
                    samples = samples,
                    startGlobalSample = startGlobalSample,
                    endGlobalSample = endGlobalSample,
                    sequence = slidingWindowSequence,
                    readyTimeMs = System.currentTimeMillis(),
                    readyMonotonicMs = SystemClock.elapsedRealtime()
                )
            )
            slidingWindowSequence += 1
            nextSlidingWindowEndSample += slidingHopSamples.toLong()
        }

        snapshots.forEach { snapshot ->
            slidingWindowWriteExecutor.execute {
                saveSlidingWindowEvent(snapshot)
            }
        }
    }

    private fun saveSlidingWindowEvent(snapshot: SlidingWindowSnapshot) {
        val saveStartTimeMs = System.currentTimeMillis()
        val saveStartMonotonicMs = SystemClock.elapsedRealtime()
        try {
            val folder = File(
                getExternalFilesDir(Environment.DIRECTORY_MUSIC),
                "sound_events"
            )

            if (!folder.exists()) {
                folder.mkdirs()
            }

            val captureStartTimeMs = sampleTimeMs(
                listeningStartTimeMs,
                snapshot.startGlobalSample,
                sampleRate
            )
            val eventEndTimeMs = sampleTimeMs(
                listeningStartTimeMs,
                snapshot.endGlobalSample,
                sampleRate
            )
            val stats = calculateSlidingWindowStats(snapshot.samples)
            val peakTimeMs = sampleTimeMs(
                captureStartTimeMs,
                stats.peakSample,
                sampleRate
            )
            val fileTimestamp = SimpleDateFormat(
                "yyyyMMdd_HHmmss_SSS",
                Locale.getDefault()
            ).format(Date(captureStartTimeMs))
            val displayTimestamp = SimpleDateFormat(
                "yyyy/MM/dd HH:mm:ss",
                Locale.getDefault()
            ).format(Date(captureStartTimeMs))
            val file = File(
                folder,
                "window_${fileTimestamp}_${snapshot.sequence}.wav"
            )

            RandomAccessFile(file, "rw").use { wav ->
                wav.setLength(0)
                writeEmptyWavHeader(wav)
                writeShortArrayData(wav, snapshot.samples)
                updateWavHeader(wav, snapshot.samples.size * bytesPerSample)
            }

            val saveEndTimeMs = System.currentTimeMillis()
            val saveEndMonotonicMs = SystemClock.elapsedRealtime()
            val audioDurationMs = sampleOffsetMs(
                slidingWindowSamples.toLong(),
                sampleRate
            )
            val emitTimeMs = System.currentTimeMillis()
            val emitMonotonicMs = SystemClock.elapsedRealtime()
            val eventInfo = hashMapOf<String, Any>(
                "path" to file.absolutePath,
                "time" to displayTimestamp,
                "duration" to (slidingWindowMs.toDouble() / 1000.0),
                "event_start_time_ms" to captureStartTimeMs,
                "event_end_time_ms" to eventEndTimeMs,
                "device_event_time_ms" to captureStartTimeMs,
                "rms_peak_offset_ms" to sampleOffsetMs(stats.peakSample, sampleRate).toDouble(),
                "rms_avg" to stats.avgRms,
                "rms_peak" to stats.peakRms,
                "sample_rate" to sampleRate,
                "audio_duration_ms" to audioDurationMs,
                "timing_version" to 1,
                "timing_source" to "PCM_SLIDING_WINDOW",
                "capture_start_time_ms" to captureStartTimeMs,
                "event_start_sample" to 0,
                "event_end_sample" to slidingWindowSamples,
                "rms_peak_sample" to stats.peakSample,
                "sample_rate_hz" to sampleRate,
                "channel_count" to channelCount,
                "rms_peak_time_ms" to peakTimeMs,
                "window_sequence" to snapshot.sequence,
                "window_start_global_sample" to snapshot.startGlobalSample,
                "window_end_global_sample" to snapshot.endGlobalSample,
                "window_hop_ms" to slidingHopMs,
                "native_window_ready_time_ms" to snapshot.readyTimeMs,
                "native_save_start_time_ms" to saveStartTimeMs,
                "native_save_end_time_ms" to saveEndTimeMs,
                "native_flutter_emit_time_ms" to emitTimeMs,
                "native_queue_delay_ms" to (saveStartMonotonicMs - snapshot.readyMonotonicMs),
                "native_save_duration_ms" to (saveEndMonotonicMs - saveStartMonotonicMs),
                "native_emit_delay_ms" to (emitMonotonicMs - snapshot.readyMonotonicMs)
            )

            android.util.Log.d(
                "SoundTiming",
                "[SLIDING_WINDOW] seq=${snapshot.sequence} " +
                    "captureStartMs=$captureStartTimeMs peakSample=${stats.peakSample} " +
                    "sampleRate=$sampleRate durationMs=$audioDurationMs " +
                    "hopMs=$slidingHopMs queueDelayMs=${saveStartMonotonicMs - snapshot.readyMonotonicMs} " +
                    "saveMs=${saveEndMonotonicMs - saveStartMonotonicMs}"
            )

            sendToFlutter("event_saved", eventInfo)
        } catch (error: Exception) {
            android.util.Log.e("SoundNodeAudio", "sliding window save failed", error)
            sendToFlutter("audio_error", null)
        }
    }

    private fun calculateSlidingWindowStats(samples: ShortArray): SlidingWindowStats {
        if (samples.isEmpty()) {
            return SlidingWindowStats(0.0, 0.0, 0L)
        }

        var totalSum = 0.0
        var peakRms = 0.0
        var peakSample = 0L
        val frameSamples = maxOf(1, liveAudioFrameSamples)
        var index = 0

        while (index < samples.size) {
            val count = minOf(frameSamples, samples.size - index)
            var frameSum = 0.0

            for (i in 0 until count) {
                val sample = samples[index + i].toDouble()
                val squared = sample * sample
                frameSum += squared
                totalSum += squared
            }

            val frameRms = sqrt(frameSum / count.toDouble())
            if (frameRms > peakRms) {
                peakRms = frameRms
                peakSample = (index + count / 2).toLong()
            }

            index += count
        }

        val avgRms = sqrt(totalSum / samples.size.toDouble())
        return SlidingWindowStats(avgRms, peakRms, peakSample)
    }

    private fun handleSoundDetected(
        buffer: ShortArray,
        read: Int,
        rms: Double,
        bufferStartGlobalSample: Long
    ) {
        silentSamples = 0
        loudBufferCount = 0
        val wasRecording = isEventRecording

        if (!wasRecording) {
            startNewEvent(bufferStartGlobalSample, read)
            writePreBufferToEventFile()

            val eventInfo = hashMapOf<String, Any>(
                "time" to (currentEventTimeText ?: "unknown time"),
                "path" to (currentFilePath ?: "unknown path"),
                "event_start_time_ms" to currentEventStartTimeMs,
                "timing_version" to 1,
                "timing_source" to "PCM_SAMPLE_INDEX",
                "capture_start_time_ms" to currentCaptureStartTimeMs,
                "event_start_sample" to currentEventStartSample,
                "sample_rate" to sampleRate,
                "sample_rate_hz" to sampleRate,
                "channel_count" to channelCount
            )

            sendToFlutter("event_started", eventInfo)
        }

        val peakSampleIndex = if (wasRecording) eventSamplesWritten.toLong() else currentEventStartSample
        updatePeakTiming(rms, peakSampleIndex)
        writeShortArrayToEventFile(buffer, read)

        if (eventSamplesWritten >= samplesForMs(maxEventMs)) {
            finishCurrentEventIfNeeded()
            sendToFlutter("silent", null)
        }
    }

    private fun handleNoSound(buffer: ShortArray, read: Int) {
        if (isEventRecording) {
            val rms = calculateRms(buffer, read)
            updatePeakTiming(rms, eventSamplesWritten.toLong())
            writeShortArrayToEventFile(buffer, read)
            silentSamples += read

            if (silentSamples >= samplesForMs(silenceEndMs)) {
                finishCurrentEventIfNeeded()
                sendToFlutter("silent", null)
            }
        } else {
            sendToFlutter("silent", null)
        }
    }

    private fun samplesForMs(durationMs: Int): Int {
        return sampleRate * durationMs / 1000
    }

    private fun startNewEvent(bufferStartGlobalSample: Long, read: Int) {
        try {
            val folder = File(
                getExternalFilesDir(Environment.DIRECTORY_MUSIC),
                "sound_events"
            )

            if (!folder.exists()) {
                folder.mkdirs()
            }

            val fileTimestamp = SimpleDateFormat(
                "yyyyMMdd_HHmmss_SSS",
                Locale.getDefault()
            ).format(Date())

            val displayTimestamp = SimpleDateFormat(
                "yyyy/MM/dd HH:mm:ss",
                Locale.getDefault()
            ).format(Date())

            val file = File(folder, "event_$fileTimestamp.wav")

            currentFilePath = file.absolutePath
            currentEventTimeText = displayTimestamp
            currentCaptureStartGlobalSample =
                bufferStartGlobalSample + read.toLong() - preBuffer.size.toLong()
            currentCaptureStartTimeMs = sampleTimeMs(
                listeningStartTimeMs,
                currentCaptureStartGlobalSample,
                sampleRate
            )
            currentEventStartSample = maxOf(
                0L,
                bufferStartGlobalSample - currentCaptureStartGlobalSample
            )
            currentEventStartTimeMs = sampleTimeMs(
                currentCaptureStartTimeMs,
                currentEventStartSample,
                sampleRate
            )

            currentWavFile = RandomAccessFile(file, "rw")
            currentWavFile?.setLength(0)

            writeEmptyWavHeader(currentWavFile!!)

            dataBytesWritten = 0
            eventSamplesWritten = 0
            silentSamples = 0
            currentEventPeakRms = 0.0
            currentEventPeakOffsetMs = null
            currentRmsPeakSample = null

            isEventRecording = true
        } catch (_: Exception) {
            isEventRecording = false
            currentWavFile = null
            currentFilePath = null
            currentEventTimeText = null
            currentEventStartTimeMs = 0L
            currentCaptureStartTimeMs = 0L
            currentCaptureStartGlobalSample = 0L
            currentEventStartSample = 0L
            currentRmsPeakSample = null
            currentEventPeakRms = 0.0
            currentEventPeakOffsetMs = null
            sendToFlutter("audio_error", null)
        }
    }

    private fun updatePeakTiming(rms: Double, sampleIndexInWav: Long) {
        if (!isEventRecording) return
        if (rms <= currentEventPeakRms) return

        currentEventPeakRms = rms
        currentRmsPeakSample = sampleIndexInWav
        currentEventPeakOffsetMs = sampleOffsetMs(sampleIndexInWav, sampleRate).toDouble()
    }

    private fun writePreBufferToEventFile() {
        val snapshot = preBuffer.toList()

        for (sample in snapshot) {
            writeOneShort(sample)
        }
    }

    private fun writeShortArrayToEventFile(buffer: ShortArray, read: Int) {
        for (i in 0 until read) {
            writeOneShort(buffer[i])
        }
    }

    private fun writeShortArrayData(wav: RandomAccessFile, samples: ShortArray) {
        for (sample in samples) {
            wav.write(sample.toInt() and 0xFF)
            wav.write((sample.toInt() shr 8) and 0xFF)
        }
    }

    private fun writeOneShort(sample: Short) {
        val wav = currentWavFile ?: return

        try {
            wav.write(sample.toInt() and 0xFF)
            wav.write((sample.toInt() shr 8) and 0xFF)

            dataBytesWritten += 2
            eventSamplesWritten += 1
        } catch (_: Exception) {
            sendToFlutter("audio_error", null)
        }
    }

    private fun finishCurrentEventIfNeeded() {
        if (!isEventRecording) return

        try {
            val wav = currentWavFile

            if (wav != null) {
                updateWavHeader(wav, dataBytesWritten)
                wav.close()
            }

            val savedPath = currentFilePath
            val savedTime = currentEventTimeText ?: "unknown time"
            val savedStartTimeMs = currentEventStartTimeMs
            val savedCaptureStartTimeMs = currentCaptureStartTimeMs
            val savedEventStartSample = currentEventStartSample
            val savedEndSample = eventSamplesWritten.toLong()
            val savedPeakSample = currentRmsPeakSample ?: currentEventStartSample
            val savedEndTimeMs = sampleTimeMs(
                savedCaptureStartTimeMs,
                savedEndSample,
                sampleRate
            )
            val savedPeakTimeMs = sampleTimeMs(
                savedCaptureStartTimeMs,
                savedPeakSample,
                sampleRate
            )
            val savedPeakOffsetMs = currentEventPeakOffsetMs
            val durationSeconds = eventSamplesWritten.toDouble() / sampleRate.toDouble()
            val audioDurationMs = sampleOffsetMs(savedEndSample, sampleRate)

            isEventRecording = false
            currentWavFile = null
            currentFilePath = null
            currentEventTimeText = null
            currentEventStartTimeMs = 0L
            currentCaptureStartTimeMs = 0L
            currentCaptureStartGlobalSample = 0L
            currentEventStartSample = 0L
            currentRmsPeakSample = null
            currentEventPeakRms = 0.0
            currentEventPeakOffsetMs = null
            dataBytesWritten = 0
            silentSamples = 0
            eventSamplesWritten = 0

            if (savedPath != null) {
                val deviceEventTimeMs = sampleTimeMs(
                    savedCaptureStartTimeMs,
                    savedEventStartSample,
                    sampleRate
                )
                val eventInfo = hashMapOf<String, Any>(
                    "path" to savedPath,
                    "time" to savedTime,
                    "duration" to durationSeconds,
                    "event_start_time_ms" to savedStartTimeMs,
                    "event_end_time_ms" to savedEndTimeMs,
                    "device_event_time_ms" to deviceEventTimeMs,
                    "rms_peak_offset_ms" to (savedPeakOffsetMs ?: 0.0),
                    "sample_rate" to sampleRate,
                    "audio_duration_ms" to audioDurationMs,
                    "timing_version" to 1,
                    "timing_source" to "PCM_SAMPLE_INDEX",
                    "capture_start_time_ms" to savedCaptureStartTimeMs,
                    "event_start_sample" to savedEventStartSample,
                    "event_end_sample" to savedEndSample,
                    "rms_peak_sample" to savedPeakSample,
                    "sample_rate_hz" to sampleRate,
                    "channel_count" to channelCount,
                    "rms_peak_time_ms" to savedPeakTimeMs
                )

                android.util.Log.d(
                    "SoundTiming",
                    "[TIMING] source=PCM_SAMPLE_INDEX captureStartMs=$savedCaptureStartTimeMs " +
                        "eventStartSample=$savedEventStartSample peakSample=$savedPeakSample " +
                        "sampleRate=$sampleRate deviceEventTimeMs=$deviceEventTimeMs"
                )

                sendToFlutter("event_saved", eventInfo)
            }
        } catch (_: Exception) {
            sendToFlutter("audio_error", null)
        }
    }

    private fun releaseAudioRecord() {
        isLiveAudioStreaming = false
        try {
            audioRecord?.stop()
        } catch (_: Exception) {
        }

        try {
            audioRecord?.release()
        } catch (_: Exception) {
        }

        audioRecord = null
    }

    private fun writeEmptyWavHeader(wav: RandomAccessFile) {
        for (i in 0 until 44) {
            wav.write(0)
        }
    }

    private fun updateWavHeader(wav: RandomAccessFile, dataSize: Int) {
        val byteRate = sampleRate * channelCount * bytesPerSample
        val blockAlign = channelCount * bytesPerSample
        val totalDataLen = dataSize + 36

        wav.seek(0)

        wav.writeBytes("RIFF")
        writeIntLE(wav, totalDataLen)
        wav.writeBytes("WAVE")

        wav.writeBytes("fmt ")
        writeIntLE(wav, 16)
        writeShortLE(wav, 1.toShort())
        writeShortLE(wav, channelCount.toShort())
        writeIntLE(wav, sampleRate)
        writeIntLE(wav, byteRate)
        writeShortLE(wav, blockAlign.toShort())
        writeShortLE(wav, 16.toShort())

        wav.writeBytes("data")
        writeIntLE(wav, dataSize)
    }

    private fun sampleOffsetMs(sampleIndex: Long, sampleRateHz: Int): Long {
        return ((sampleIndex.toDouble() * 1000.0) / sampleRateHz.toDouble()).roundToLong()
    }

    private fun sampleTimeMs(baseTimeMs: Long, sampleIndex: Long, sampleRateHz: Int): Long {
        return baseTimeMs + sampleOffsetMs(sampleIndex, sampleRateHz)
    }

    private fun writeIntLE(wav: RandomAccessFile, value: Int) {
        wav.write(value and 0xFF)
        wav.write((value shr 8) and 0xFF)
        wav.write((value shr 16) and 0xFF)
        wav.write((value shr 24) and 0xFF)
    }

    private fun writeShortLE(wav: RandomAccessFile, value: Short) {
        val intValue = value.toInt()

        wav.write(intValue and 0xFF)
        wav.write((intValue shr 8) and 0xFF)
    }

    private fun sendToFlutter(method: String, argument: Any?) {
        runOnUiThread {
            methodChannel?.invokeMethod(method, argument)
        }
    }

    private fun resetLiveAudioFrameBuffer() {
        synchronized(liveAudioFrameLock) {
            liveAudioFrameFill = 0
            liveAudioFrameStartGlobalSample = 0L
        }
    }

    private fun emitLiveAudioFrame(
        buffer: ShortArray,
        read: Int,
        bufferStartGlobalSample: Long
    ) {
        if (!isLiveAudioStreaming || read <= 0) return

        val frames = mutableListOf<HashMap<String, Any>>()
        var inputIndex = 0

        synchronized(liveAudioFrameLock) {
            while (inputIndex < read && isLiveAudioStreaming) {
                if (liveAudioFrameFill == 0) {
                    liveAudioFrameStartGlobalSample = bufferStartGlobalSample + inputIndex
                }

                val copyCount = minOf(
                    read - inputIndex,
                    liveAudioFrameSamples - liveAudioFrameFill
                )
                System.arraycopy(
                    buffer,
                    inputIndex,
                    liveAudioFrameBuffer,
                    liveAudioFrameFill,
                    copyCount
                )

                inputIndex += copyCount
                liveAudioFrameFill += copyCount

                if (liveAudioFrameFill == liveAudioFrameSamples) {
                    frames.add(
                        buildLiveAudioFrame(
                            liveAudioFrameBuffer,
                            liveAudioFrameSamples,
                            liveAudioFrameStartGlobalSample
                        )
                    )
                    liveAudioFrameFill = 0
                    liveAudioFrameStartGlobalSample = bufferStartGlobalSample + inputIndex
                }
            }
        }

        frames.forEach { frame ->
            sendToFlutter("live_audio_frame", frame)
        }
    }

    private fun buildLiveAudioFrame(
        samples: ShortArray,
        sampleCount: Int,
        frameStartGlobalSample: Long
    ): HashMap<String, Any> {
        val bytes = ByteArray(sampleCount * bytesPerSample)
        var outputIndex = 0
        for (i in 0 until sampleCount) {
            val value = samples[i].toInt()
            bytes[outputIndex] = (value and 0xFF).toByte()
            bytes[outputIndex + 1] = ((value shr 8) and 0xFF).toByte()
            outputIndex += 2
        }

        val captureTimestampUs =
            sampleTimeMs(listeningStartTimeMs, frameStartGlobalSample, sampleRate) * 1000L
        return hashMapOf(
            "pcm_bytes" to bytes,
            "sample_rate_hz" to sampleRate,
            "channel_count" to channelCount,
            "capture_timestamp_us" to captureTimestampUs,
            "sample_count" to sampleCount
        )
    }
}
