PROTOCOL_VERSION = 1

NODE_TO_BACKEND_MESSAGE_TYPES = {
    "hello",
    "heartbeat",
    "status_update",
    "command_ack",
    "command_result",
    "stream_started",
    "stream_stopped",
    "protocol_error",
}

BACKEND_TO_NODE_MESSAGE_TYPES = {
    "hello_ack",
    "command",
    "start_stream",
    "stop_stream",
    "request_status",
    "ping",
    "protocol_error",
}

COMMAND_TYPES = {
    "START_DETECTION",
    "STOP_DETECTION",
    "START_RECORDING",
    "STOP_RECORDING",
    "START_LIVE_AUDIO",
    "STOP_LIVE_AUDIO",
    "REQUEST_STATUS",
    "SYNC_TIME",
    "UPDATE_CONFIG",
}

LEGACY_COMMAND_MAP = {
    "start_listening": "START_DETECTION",
    "stop_listening": "STOP_DETECTION",
    "start_recording": "START_RECORDING",
    "stop_recording": "STOP_RECORDING",
    "start_live_audio": "START_LIVE_AUDIO",
    "stop_live_audio": "STOP_LIVE_AUDIO",
    "request_status": "REQUEST_STATUS",
    "sync_time": "SYNC_TIME",
    "set_detection_mode": "UPDATE_CONFIG",
    "set_collection_mode": "UPDATE_CONFIG",
}

AUDIO_FRAME_MAGIC = b"SDAF"
AUDIO_CODEC_PCM16 = 1
AUDIO_CODEC_OPUS = 2
AUDIO_CODEC_NAMES = {
    AUDIO_CODEC_PCM16: "pcm16",
    AUDIO_CODEC_OPUS: "opus",
}

# !4sBBH16sQQIHBBI
# magic, protocol_version, flags, header_length, stream_uuid_bytes,
# sequence_number, capture_timestamp_us, sample_rate_hz, channel_count,
# codec_id, frame_duration_ms, payload_length
AUDIO_FRAME_STRUCT_FORMAT = "!4sBBH16sQQIHBBI"
AUDIO_FRAME_HEADER_LENGTH = 52
MAX_AUDIO_FRAME_BYTES = 64 * 1024
