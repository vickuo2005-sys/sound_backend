import os
import sys

import numpy as np

os.environ["DATABASE_URL"] = ""

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.localization.gcc_phat import gcc_phat_delay_seconds  # noqa: E402


def main() -> None:
    sample_rate = 16000
    reference = np.zeros(sample_rate, dtype=np.float32)
    reference[3000] = 1.0
    target = np.zeros(sample_rate, dtype=np.float32)
    delay_samples = 80
    target[3000 + delay_samples] = 1.0

    result = gcc_phat_delay_seconds(
        reference,
        target,
        sample_rate_hz=sample_rate,
        max_tau_seconds=0.02,
    )
    assert abs(result["lag_samples"] - delay_samples) <= 1, result
    assert abs(result["lag_seconds"] - delay_samples / sample_rate) < 0.0002
    assert result["correlation_score"] > 0
    print("GCC-PHAT tests passed")


if __name__ == "__main__":
    main()
