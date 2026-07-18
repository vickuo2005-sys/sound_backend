import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("UPLOAD_TOKEN", "test-token-123")

import main  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_raises_http(fn, message: str) -> None:
    try:
        fn()
    except main.HTTPException:
        return
    raise AssertionError(message)


def run_tests() -> None:
    wav_header = b"RIFF\x24\x00\x00\x00WAVEfmt "
    mp3_id3_header = b"ID3\x04\x00\x00\x00\x00\x00\x21"
    mp3_frame_header = bytes([0xFF, 0xFB, 0x90, 0x64])

    assert_equal(
        main.detect_audio_upload_format(
            filename="event.wav",
            content_type="audio/wav",
            header=wav_header,
            declared_format="wav",
            allowed_formats={"wav", "mp3"},
        ),
        "wav",
        "WAV format detection",
    )
    assert_equal(
        main.detect_audio_upload_format(
            filename="event.mp3",
            content_type="audio/mpeg",
            header=mp3_id3_header,
            declared_format="mp3",
            allowed_formats={"wav", "mp3"},
        ),
        "mp3",
        "MP3 ID3 format detection",
    )
    assert_equal(
        main.detect_audio_upload_format(
            filename="event.mp3",
            content_type="audio/mpeg",
            header=mp3_frame_header,
            declared_format="mp3",
            allowed_formats={"wav", "mp3"},
        ),
        "mp3",
        "MP3 frame sync format detection",
    )

    assert_raises_http(
        lambda: main.detect_audio_upload_format(
            filename="event.wav",
            content_type="audio/wav",
            header=mp3_id3_header,
            declared_format="wav",
            allowed_formats={"wav", "mp3"},
        ),
        "Mismatched MP3/WAV metadata should fail",
    )

    primary_path = main.build_audio_path(
        device_id="node_A01",
        event_id="event_001",
        label="aircraft",
        audio_format="mp3",
    )
    if not primary_path.endswith("/event_001.mp3"):
        raise AssertionError(f"Primary MP3 path is wrong: {primary_path}")
    if not primary_path.startswith("audio/drone/node_A01/"):
        raise AssertionError(f"Primary MP3 category path is wrong: {primary_path}")

    clip_path = main.build_audio_path(
        device_id="node_A01",
        event_id="event_001",
        label="aircraft",
        audio_format="wav",
        role="tdoa_clip",
    )
    if not clip_path.endswith("/event_001_tdoa_clip.wav"):
        raise AssertionError(f"TDOA clip path is wrong: {clip_path}")

    invalid = main.SoundEvent(
        event_id="invalid_audio",
        device_id="node_A01",
        timestamp="2026-07-18T00:00:00+00:00",
        audio_format="flac",
        audio_size_bytes=-1,
        tdoa_clip_start_sample=200,
        tdoa_clip_end_sample=100,
    )
    main.sanitize_audio_metadata(invalid)
    assert_equal(invalid.audio_format, None, "Invalid audio_format should be cleared")
    assert_equal(invalid.audio_size_bytes, None, "Invalid audio size should be cleared")
    assert_equal(
        invalid.tdoa_clip_start_sample,
        None,
        "Invalid clip metadata should be cleared",
    )


def main_entry() -> None:
    run_tests()
    print("Smart audio upload tests passed")


if __name__ == "__main__":
    main_entry()
