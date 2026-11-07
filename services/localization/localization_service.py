from typing import Callable, Optional

from .gcc_phat import gcc_phat_delay_seconds
from .geo import haversine_m, parse_float
from .timestamp_tdoa import estimate_timestamp_tdoa, fallback_result
from .wav_loader import load_pcm_wav_bytes


ClipLoader = Callable[[dict], Optional[bytes]]


def corrected_clip_start_ms(observation: dict) -> Optional[float]:
    capture_start = parse_float(observation.get("capture_start_time_ms"))
    offset = parse_float(observation.get("time_sync_offset_ms"))
    start_sample = parse_float(observation.get("tdoa_clip_start_sample"))
    sample_rate = parse_float(observation.get("sample_rate_hz"))
    if (
        capture_start is None
        or offset is None
        or start_sample is None
        or sample_rate is None
        or sample_rate <= 0
    ):
        return None
    return capture_start + offset + (start_sample / sample_rate * 1000.0)


def try_gcc_refinement(
    observations: list[dict],
    clip_loader: Optional[ClipLoader],
    *,
    sound_speed_mps: float,
    min_correlation_score: float,
) -> dict:
    if clip_loader is None:
        return {"status": "skipped", "reason": "clip_loader_missing", "pairs": []}

    waveforms = {}
    failures = []
    for observation in observations:
        if not observation.get("tdoa_clip_path"):
            failures.append({"device_id": observation.get("device_id"), "reason": "missing_clip_path"})
            continue
        try:
            data = clip_loader(observation)
            if not data:
                failures.append({"device_id": observation.get("device_id"), "reason": "clip_not_available"})
                continue
            waveforms[str(observation["device_id"])] = load_pcm_wav_bytes(data)
        except Exception as exc:
            failures.append(
                {
                    "device_id": observation.get("device_id"),
                    "reason": "clip_load_failed",
                    "error": str(exc),
                }
            )

    if len(waveforms) < 3:
        return {"status": "insufficient_clips", "failures": failures, "pairs": []}

    reference = min(
        observations,
        key=lambda item: parse_float(item.get("corrected_arrival_time_ms")) or float("inf"),
    )
    reference_id = str(reference.get("device_id"))
    reference_wave = waveforms.get(reference_id)
    reference_start_ms = corrected_clip_start_ms(reference)
    if reference_wave is None or reference_start_ms is None:
        return {
            "status": "reference_unavailable",
            "reference_device_id": reference_id,
            "failures": failures,
            "pairs": [],
        }

    refined = []
    pairs = []
    for observation in observations:
        device_id = str(observation.get("device_id"))
        waveform = waveforms.get(device_id)
        start_ms = corrected_clip_start_ms(observation)
        if waveform is None or start_ms is None:
            continue
        if waveform.sample_rate_hz != reference_wave.sample_rate_hz:
            failures.append({"device_id": device_id, "reason": "sample_rate_mismatch"})
            continue

        distance_m = haversine_m(
            float(reference["latitude"]),
            float(reference["longitude"]),
            float(observation["latitude"]),
            float(observation["longitude"]),
        )
        max_tau = distance_m / sound_speed_mps + 0.02
        pair = gcc_phat_delay_seconds(
            reference_wave.samples,
            waveform.samples,
            waveform.sample_rate_hz,
            max_tau_seconds=max_tau,
        )
        pair.update(
            {
                "reference_device_id": reference_id,
                "device_id": device_id,
                "distance_m": distance_m,
            }
        )
        pairs.append(pair)
        if pair["correlation_score"] < min_correlation_score:
            continue

        if device_id == reference_id:
            refined_time = reference_start_ms
        else:
            refined_time = reference_start_ms + pair["lag_seconds"] * 1000.0
        refined.append({**observation, "corrected_arrival_time_ms": refined_time})

    if len(refined) < 3:
        return {"status": "insufficient_valid_pairs", "failures": failures, "pairs": pairs}

    return {
        "status": "success",
        "reference_device_id": reference_id,
        "observations": refined,
        "failures": failures,
        "pairs": pairs,
    }


def localize_observations(
    observations: list[dict],
    *,
    clip_loader: Optional[ClipLoader] = None,
    gcc_enabled: bool = False,
    sound_speed_mps: float = 343.0,
    max_rtt_ms: float = 200.0,
    max_sync_age_ms: float = 120_000.0,
    min_correlation_score: float = 0.04,
) -> dict:
    timestamp_result = estimate_timestamp_tdoa(
        observations,
        sound_speed_mps=sound_speed_mps,
        max_rtt_ms=max_rtt_ms,
        max_sync_age_ms=max_sync_age_ms,
    )

    if not gcc_enabled:
        return timestamp_result

    gcc_result = try_gcc_refinement(
        observations,
        clip_loader,
        sound_speed_mps=sound_speed_mps,
        min_correlation_score=min_correlation_score,
    )
    if gcc_result.get("status") != "success":
        timestamp_result["diagnostics"] = {
            **(timestamp_result.get("diagnostics") or {}),
            "gcc_phat": gcc_result,
        }
        return timestamp_result

    hybrid_result = estimate_timestamp_tdoa(
        gcc_result["observations"],
        sound_speed_mps=sound_speed_mps,
        max_rtt_ms=max_rtt_ms,
        max_sync_age_ms=max_sync_age_ms,
        version="v3.4-hybrid-localization",
    )
    hybrid_result["diagnostics"] = {
        **(hybrid_result.get("diagnostics") or {}),
        "gcc_phat": gcc_result,
        "timestamp_result": timestamp_result,
    }

    if hybrid_result.get("status") == "SUCCESS":
        hybrid_result["method"] = "hybrid_tdoa"
        return hybrid_result

    if timestamp_result.get("status") == "SUCCESS":
        timestamp_result["diagnostics"] = {
            **(timestamp_result.get("diagnostics") or {}),
            "gcc_phat": gcc_result,
            "hybrid_failure": hybrid_result,
        }
        return timestamp_result

    return fallback_result(
        observations,
        "hybrid_and_timestamp_failed",
        "v3.4-hybrid-localization",
        diagnostics={
            "gcc_phat": gcc_result,
            "timestamp_result": timestamp_result,
            "hybrid_result": hybrid_result,
        },
    )
