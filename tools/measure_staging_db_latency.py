"""Collect a bounded Render-to-Supabase SELECT 1 RTT sample set."""

from __future__ import annotations

import argparse
import json

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--upload-token", required=True)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    if not 10 <= args.samples <= 50:
        parser.error("--samples must be between 10 and 50")
    with httpx.Client(timeout=args.timeout) as client:
        response = client.post(
                f"{args.base_url.rstrip('/')}/diagnostics/db-latency?samples={args.samples}",
                headers={"x-upload-token": args.upload_token},
            )
        response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
