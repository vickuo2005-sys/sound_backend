"""Fail-closed validation of Phase 4 staging target identity."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse


PRODUCTION_RENDER_HOST = "sound-backend.onrender.com"
PRODUCTION_GCS_BUCKET = "sound-detector"
EXPECTED_RENDER_SERVICE = "sound-backend-staging"
EXPECTED_BACKEND_BRANCH = "feat/v2-3-phase4-field-shadow"


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
    if environment != "staging":
        errors.append("environment must be staging")
    if data.get("backend_git_branch") != EXPECTED_BACKEND_BRANCH:
        errors.append(f"backend_git_branch must be {EXPECTED_BACKEND_BRANCH}")
    if not str(data.get("flutter_application_id", "")).endswith(".staging"):
        errors.append("flutter_application_id must end with .staging")

    render_base_url = str(data.get("render_base_url", "")).strip()
    if not render_base_url:
        errors.append("render_base_url is required")
    else:
        parsed = urlparse(render_base_url)
        render_host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not render_host:
            errors.append("render_base_url must use https and include a hostname")
        if render_host == PRODUCTION_RENDER_HOST:
            errors.append("render_base_url points to the production host")
        if "staging" not in render_host:
            errors.append("render hostname must be explicitly staging-labelled")

    if data.get("render_service_name") != EXPECTED_RENDER_SERVICE:
        errors.append(f"render_service_name must be {EXPECTED_RENDER_SERVICE}")

    supabase_project_ref = str(data.get("supabase_project_ref", "")).strip()
    if not supabase_project_ref:
        errors.append("supabase_project_ref is required")

    gcs_bucket = str(data.get("gcs_bucket", "")).strip()
    if not gcs_bucket:
        errors.append("gcs_bucket is required for the Phase 4 /events audio path")
    elif gcs_bucket == PRODUCTION_GCS_BUCKET:
        errors.append("gcs_bucket points to the production bucket")
    elif "staging" not in gcs_bucket.lower():
        errors.append("gcs_bucket must be explicitly staging-labelled")

    if not str(data.get("gcs_project_id", "")).strip():
        errors.append("gcs_project_id is required")

    gcs_prefix = str(data.get("gcs_prefix", "")).strip()
    if gcs_prefix and not gcs_prefix.endswith("/"):
        errors.append("gcs_prefix must end with /")

    database_host = str(data.get("database_host", "")).strip().lower()
    if not database_host:
        errors.append("database_host is required")
    elif "localhost" in database_host:
        errors.append("database_host must not use localhost")
    elif not database_host.endswith("supabase.com"):
        errors.append("database_host must be a Supabase staging database host")

    joined = json.dumps(data, ensure_ascii=False).lower()
    if "test-token-123" in joined:
        errors.append("target file contains demo token")
    if "password" in joined or "private_key" in joined:
        errors.append("target file appears to contain a secret")

    if errors:
        for error in errors:
            print(f"- {error}")
        return 1

    print("ready: Phase 4 staging target shape is valid; verify identities against cloud dashboards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
