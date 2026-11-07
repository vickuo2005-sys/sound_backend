"""Read-only collector. Isolation approval is an operator attestation, not discovery."""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Refusing redirect away from the verified service URL")


def validate_runtime(payload, expected_commit):
    if payload.get("build", {}).get("render_git_commit") != expected_commit:
        raise ValueError("Deployed commit does not match expected full SHA")
    diagnostics = payload["latency_diagnostics"]
    if diagnostics["sample_window"] != 256:
        raise ValueError("Unexpected sample window")
    for stage in diagnostics["stages"].values():
        if type(stage["count"]) is not int or not 1 <= stage["count"] <= 256:
            raise ValueError("Invalid sample count")
        for key in ("p50_ms", "p95_ms", "p99_ms", "mean_ms", "max_ms", "last_ms"):
            value = stage[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid duration")
        if not stage["p50_ms"] <= stage["p95_ms"] <= stage["p99_ms"] <= stage["max_ms"]:
            raise ValueError("Invalid percentile ordering")
    for key in ("pending_jobs", "peak_pending_jobs"):
        if any(type(value) is not int or value < 0 for value in diagnostics[key].values()):
            raise ValueError("Invalid queue count")
    return diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--isolation-confirmed", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args()
    url = urlsplit(args.base_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        parser.error("Use the verified HTTPS staging origin without credentials, path or query")
    if len(args.expected_commit) != 40 or any(c not in "0123456789abcdef" for c in args.expected_commit):
        parser.error("Expected commit must be the full lowercase SHA")
    if args.samples < 1 or not math.isfinite(args.interval) or args.interval < 1:
        parser.error("Use samples >= 1 and finite interval >= 1 second")
    opener = build_opener(NoRedirects())
    origin = args.base_url.rstrip("/")
    def get(path):
        with opener.open(origin + path, timeout=15) as response:
            return json.load(response)
    health = get("/health")
    if health.get("status") != "healthy" or health.get("database_init_error"):
        raise ValueError("Health check failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        for index in range(args.samples):
            started = time.monotonic()
            payload = get("/runtime-status")
            diagnostics = validate_runtime(payload, args.expected_commit)
            row = {"collected_at_utc": datetime.now(timezone.utc).isoformat(),
                   "server_time": payload.get("time"), "build": payload["build"],
                   "collector_http_ms": (time.monotonic() - started) * 1000,
                   "latency_diagnostics": diagnostics}
            output.write(json.dumps(row, allow_nan=False) + "\n")
            output.flush()
            if index + 1 < args.samples:
                time.sleep(max(0, args.interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
