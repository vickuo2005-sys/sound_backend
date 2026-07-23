"""Validate local staging target identity without touching cloud resources."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse


PRODUCTION_RENDER_HOST = "sound-backend.onrender.com"
PRODUCTION_GCS_BUCKET = "sound-detector"


def fail(message: str) -> int:
    print(f"not_ready: {message}")
    return 1


def main() -> int:
    path = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path("config/staging_targets.local.json")
    )
    if not path.exists():
        return fail(f"target file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []

    if data.get("environment") != "staging":
        errors.append("environment must be staging")
    if data.get("backend_git_branch") != "staging":
        errors.append("backend_git_branch must be staging")
    if not str(data.get("flutter_application_id", "")).endswith(".staging"):
        errors.append("flutter_application_id must end with .staging")

    render_base_url = str(data.get("render_base_url", "")).strip()
    if render_base_url:
        parsed = urlparse(render_base_url)
        if parsed.scheme != "https":
            errors.append("render_base_url must use https")
        if parsed.netloc == PRODUCTION_RENDER_HOST:
            errors.append("render_base_url points to production")

    gcs_bucket = str(data.get("gcs_bucket", "")).strip()
    if gcs_bucket == PRODUCTION_GCS_BUCKET:
        errors.append("gcs_bucket must not be production bucket")

    gcs_prefix = str(data.get("gcs_prefix", "")).strip()
    if gcs_prefix and not gcs_prefix.endswith("/"):
        errors.append("gcs_prefix must end with /")
    if gcs_prefix and gcs_prefix == "audio/":
        errors.append("gcs_prefix must not reuse production audio prefix")

    database_host = str(data.get("database_host", "")).strip().lower()
    if database_host and "prod" in database_host:
        errors.append("database_host appears to reference production")

    joined = json.dumps(data, ensure_ascii=False).lower()
    if "test-token-123" in joined:
        errors.append("target file contains demo token")
    if "password" in joined or "private_key" in joined:
        errors.append("target file appears to contain a secret")

    if errors:
        for error in errors:
            print(f"- {error}")
        return 1

    print("ready: staging target identity is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
