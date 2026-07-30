"""Validate local integration target identity without touching cloud resources."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse


CURRENT_INTEGRATION_RENDER_HOST = "sound-backend.onrender.com"
CURRENT_INTEGRATION_GCS_BUCKET = "sound-detector"


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

    environment = str(data.get("environment", "")).strip().lower()
    if environment not in {"development", "integration", "staging"}:
        errors.append("environment must be development, integration, or staging")
    if data.get("backend_git_branch") != "staging":
        errors.append("backend_git_branch must be staging")
    if not str(data.get("flutter_application_id", "")).endswith(".staging"):
        errors.append("flutter_application_id must end with .staging")

    render_base_url = str(data.get("render_base_url", "")).strip()
    if render_base_url:
        parsed = urlparse(render_base_url)
        if parsed.scheme != "https":
            errors.append("render_base_url must use https")

    gcs_bucket = str(data.get("gcs_bucket", "")).strip()
    if gcs_bucket and gcs_bucket != CURRENT_INTEGRATION_GCS_BUCKET:
        print(f"warning: gcs_bucket differs from current integration bucket: {gcs_bucket}")

    gcs_prefix = str(data.get("gcs_prefix", "")).strip()
    if gcs_prefix and not gcs_prefix.endswith("/"):
        errors.append("gcs_prefix must end with /")

    database_host = str(data.get("database_host", "")).strip().lower()
    if database_host and "localhost" in database_host:
        errors.append("database_host should reference the existing integration Supabase database")

    joined = json.dumps(data, ensure_ascii=False).lower()
    if "test-token-123" in joined:
        errors.append("target file contains demo token")
    if "password" in joined or "private_key" in joined:
        errors.append("target file appears to contain a secret")

    if errors:
        for error in errors:
            print(f"- {error}")
        return 1

    if render_base_url and urlparse(render_base_url).netloc != CURRENT_INTEGRATION_RENDER_HOST:
        print("warning: render_base_url differs from current integration backend")

    print("ready: integration target identity is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
