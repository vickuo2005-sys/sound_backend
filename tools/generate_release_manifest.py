import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"

EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    ".venv_release_validation",
    "venv",
    "__pycache__",
    "artifacts",
}
EXCLUDED_SUFFIXES = {
    ".db",
    ".pyc",
    ".pem",
    ".key",
    ".jks",
    ".keystore",
}
EXCLUDED_NAMES = {
    ".env",
}


def git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except Exception as exc:
        return f"UNAVAILABLE: {exc}"


def should_exclude(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    if path.name.startswith(".env."):
        return True
    if "service-account" in path.name.lower() or "credentials" in path.name.lower():
        return True
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_files() -> list[dict[str, object]]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or should_exclude(path):
            continue
        files.append(
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return sorted(files, key=lambda item: item["path"])


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    requirements = ROOT / "requirements.txt"
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "git": {
            "branch": git_output("branch", "--show-current"),
            "head": git_output("rev-parse", "HEAD"),
            "status_short": git_output("status", "--short"),
            "dirty": bool(git_output("status", "--short")),
        },
        "requirements_sha256": sha256_file(requirements) if requirements.exists() else None,
        "file_count": 0,
        "files": collect_files(),
    }
    manifest["file_count"] = len(manifest["files"])

    json_path = ARTIFACTS / "release_manifest.json"
    txt_path = ARTIFACTS / "release_manifest.txt"
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_lines = [
        f"generated_at: {manifest['generated_at']}",
        f"branch: {manifest['git']['branch']}",
        f"head: {manifest['git']['head']}",
        f"dirty: {manifest['git']['dirty']}",
        f"python_version: {manifest['python_version']}",
        f"requirements_sha256: {manifest['requirements_sha256']}",
        f"file_count: {manifest['file_count']}",
        "",
    ]
    txt_lines.extend(
        f"{item['sha256']}  {item['bytes']}  {item['path']}"
        for item in manifest["files"]
    )
    txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")


if __name__ == "__main__":
    main()

