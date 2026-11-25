from typing import Optional

import numpy as np


def gcc_phat_delay_seconds(
    reference: np.ndarray,
    target: np.ndarray,
    sample_rate_hz: int,
    max_tau_seconds: Optional[float] = None,
) -> dict:
    """Estimate target arrival delay relative to reference using GCC-PHAT."""
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive")
    if reference.size == 0 or target.size == 0:
        raise ValueError("signals must not be empty")

    ref = reference.astype(np.float64)
    tgt = target.astype(np.float64)
    ref = ref - np.mean(ref)
    tgt = tgt - np.mean(tgt)

    n = 1
    target_len = ref.size + tgt.size
    while n < target_len:
        n <<= 1

    ref_fft = np.fft.rfft(ref, n=n)
    tgt_fft = np.fft.rfft(tgt, n=n)
    cross_power = tgt_fft * np.conj(ref_fft)
    cross_power /= np.maximum(np.abs(cross_power), 1e-12)
    cc = np.fft.irfft(cross_power, n=n)

    max_shift = n // 2
    if max_tau_seconds is not None:
        max_shift = min(max_shift, int(round(max_tau_seconds * sample_rate_hz)))

    cc = np.concatenate((cc[-max_shift:], cc[: max_shift + 1]))
    shift_index = int(np.argmax(np.abs(cc)))
    shift = shift_index - max_shift
    lag_seconds = shift / float(sample_rate_hz)
    peak = float(np.abs(cc[shift_index]))

    sorted_peaks = np.sort(np.abs(cc))
    second_peak = float(sorted_peaks[-2]) if sorted_peaks.size >= 2 else 0.0
    peak_ratio = peak / max(second_peak, 1e-12)

    return {
        "lag_seconds": lag_seconds,
        "lag_samples": shift,
        "correlation_score": peak,
        "peak_ratio": peak_ratio,
    }
