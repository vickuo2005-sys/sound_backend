from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


APP_MARKER = "[OBSERVATION_SHADOW_FIELD_JSON]"
APP_B64_MARKER = "[OBSERVATION_SHADOW_FIELD_JSON_B64]"
APP_B64_PATTERN = re.compile(
    r"observation_id=(?P<observation_id>\S+) "
    r"chunk=(?P<part>\d+)/(?P<total>\d+) data=(?P<data>\S+)"
)
FORBIDDEN_PRODUCTION_HOSTS = {"sound-backend.onrender.com"}


def read_app_samples(path: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    pending_chunks: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        marker_index = line.find(APP_MARKER)
        if marker_index >= 0:
            try:
                value = json.loads(line[marker_index + len(APP_MARKER) :].strip())
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                samples.append(value)
            continue

        marker_index = line.find(APP_B64_MARKER)
        if marker_index < 0:
            continue
        match = APP_B64_PATTERN.search(line[marker_index + len(APP_B64_MARKER) :])
        if not match:
            continue
        observation_id = unquote(match.group("observation_id"))
        part = int(match.group("part"))
        total = int(match.group("total"))
        if part < 1 or total < 1 or part > total:
            continue
        if part == 1:
            pending_chunks[observation_id] = {"total": total, "parts": {}}
        pending = pending_chunks.get(observation_id)
        if not pending or pending["total"] != total:
            continue
        pending["parts"][part] = match.group("data")
        if len(pending["parts"]) != total:
            continue
        try:
            encoded = "".join(pending["parts"][index] for index in range(1, total + 1))
            value = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
        except (KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            pending_chunks.pop(observation_id, None)
            continue
        pending_chunks.pop(observation_id, None)
        if isinstance(value, dict):
            samples.append(value)
    return samples


def read_snapshots(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        snapshots = payload.get("snapshots")
        if isinstance(snapshots, list):
            return [item for item in snapshots if isinstance(item, dict)]
        return [payload]
    raise ValueError("Backend metrics must be a JSON object or list")


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("evidence_kind") != "real_android_staging":
        errors.append("evidence_kind must be real_android_staging")
    if str(manifest.get("app_env") or "").lower() != "staging":
        errors.append("app_env must be staging")
    backend_url = str(manifest.get("backend_url") or "")
    parsed = urlparse(backend_url)
    if parsed.scheme != "https" or not parsed.hostname:
        errors.append("backend_url must be HTTPS")
    if (parsed.hostname or "").lower() in FORBIDDEN_PRODUCTION_HOSTS:
        errors.append("backend_url is a forbidden production host")
    if not manifest.get("android_devices"):
        errors.append("android_devices must describe at least one physical device")
    if float(manifest.get("duration_seconds") or 0) <= 0:
        errors.append("duration_seconds must be positive")
    return errors


def analyze_field_run(
    manifest: dict[str, Any],
    app_samples: list[dict[str, Any]],
    backend_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_errors = validate_manifest(manifest)
    if manifest_errors:
        return {
            "evidence_valid": False,
            "errors": manifest_errors,
            "result": None,
        }
    if not app_samples or not backend_snapshots:
        return {
            "evidence_valid": False,
            "errors": ["App samples and Backend metric snapshots are required"],
            "result": None,
        }

    final_backend = backend_snapshots[-1]
    backend_reconciliation = final_backend.get("reconciliation") or {}
    ingest = final_backend.get("ingest") or {}
    tracking = final_backend.get("shadow_tracking") or {}
    ordering = tracking.get("ordering") or {}
    mailbox = tracking.get("mailbox") or {}
    clock = final_backend.get("clock_quality") or {}

    app_totals = _app_reconciliation_totals(app_samples)
    app_queue = _app_queue_snapshot(app_samples)
    raw = int(app_totals.get("raw_valid_target_count") or 0)
    upload_success = int(app_totals.get("upload_success_count") or 0)
    backend_received = int(backend_reconciliation.get("backend_received_count") or 0)
    unique_observations = int(
        backend_reconciliation.get("unique_observation_count") or 0
    )
    tracking_measurements = int(
        backend_reconciliation.get("tracking_measurement_count") or 0
    )
    track_points = int(backend_reconciliation.get("track_point_count") or 0)
    alert_admitted = int(app_totals.get("alert_admitted_count") or 0)
    cooldown_rejected = int(app_totals.get("cooldown_rejected_count") or 0)

    duration_minutes = float(manifest["duration_seconds"]) / 60.0
    device_count = len(manifest["android_devices"])
    payload_values = [
        int(value)
        for sample in app_samples
        if (value := _nonnegative_number(sample.get("payload_bytes"))) is not None
    ]
    request_values = [
        int(value)
        for sample in app_samples
        if (value := _nonnegative_number(sample.get("estimated_request_bytes")))
        is not None
    ]
    requests_per_minute_device = (
        len(app_samples) / duration_minutes / device_count
        if duration_minutes > 0 and device_count
        else None
    )
    average_payload = sum(payload_values) / len(payload_values) if payload_values else None
    average_request = sum(request_values) / len(request_values) if request_values else None

    sequence_gap_count = int(ordering.get("sequence_gap_count") or 0)
    out_of_order_count = int(ordering.get("sequence_out_of_order_count") or 0)
    duplicate_count = int(ordering.get("sequence_duplicate_count") or 0)
    offered = int(ordering.get("offered") or 0)

    return {
        "evidence_valid": True,
        "errors": [],
        "result": {
            "manifest": {
                "scenario": manifest.get("scenario"),
                "duration_seconds": manifest["duration_seconds"],
                "device_count": device_count,
                "android_devices": manifest["android_devices"],
                "network": manifest.get("network"),
                "backend_host": urlparse(str(manifest["backend_url"])).hostname,
            },
            "reconciliation": {
                **app_totals,
                "backend_received_count": backend_received,
                "unique_observation_count": unique_observations,
                "tracking_measurement_count": tracking_measurements,
                "track_point_count": track_points,
                "raw_ai_to_backend_loss": _loss(raw, backend_received),
                "backend_to_tracking_loss": _loss(
                    unique_observations,
                    tracking_measurements,
                ),
                "overall_observation_delivery_percent": _ratio(
                    tracking_measurements,
                    raw,
                ),
                "app_upload_to_backend_loss": _loss(upload_success, backend_received),
            },
            "sequence": {
                "sequence_gap_count": sequence_gap_count,
                "sequence_gap_rate_percent": _ratio(sequence_gap_count, offered),
                "sequence_out_of_order_count": out_of_order_count,
                "out_of_order_rate_percent": _ratio(out_of_order_count, offered),
                "sequence_duplicate_count": duplicate_count,
                "duplicate_rate_percent": _ratio(duplicate_count, offered),
                "sequence_timeout_advance_count": int(
                    ordering.get("sequence_timeout_advance_count") or 0
                ),
            },
            "observation_queue": app_queue,
            "replay": {
                "live_count": int(ingest.get("replay_live_count") or 0),
                "late_recoverable_count": int(
                    ingest.get("replay_late_recoverable_count") or 0
                ),
                "historical_only_count": int(
                    ingest.get("replay_historical_only_count") or 0
                ),
                "expired_count": int(ingest.get("replay_expired_count") or 0),
                "tracking_eligible_count": int(
                    ingest.get("tracking_eligible_count") or 0
                ),
                "tracking_historical_suppressed_count": int(
                    ingest.get("tracking_historical_suppressed_count") or 0
                ),
                "tracking_expired_suppressed_count": int(
                    ingest.get("tracking_expired_suppressed_count") or 0
                ),
                "idempotency_tombstone_count": int(
                    ingest.get("idempotency_tombstone_count") or 0
                ),
            },
            "control_vs_shadow": {
                "alert_admitted_count": alert_admitted,
                "cooldown_rejected_count": cooldown_rejected,
                "shadow_observation_count": unique_observations,
                "track_point_count": track_points,
                "point_density_vs_alert_proxy": (
                    round(track_points / alert_admitted, 4)
                    if alert_admitted
                    else None
                ),
                "track_gap_p50_ms": tracking.get("median_point_interval_ms"),
                "track_gap_p95_ms": tracking.get("p95_point_interval_ms"),
                "track_gap_max_ms": tracking.get("maximum_track_gap_ms"),
                "continuity_ratio_percent": _ratio(track_points, unique_observations),
            },
            "fusion": {
                "fusion_revision_count": tracking.get("fusion_revision_count"),
                "fusion_late_attach_count": tracking.get("fusion_late_attach_count"),
                "fusion_late_drop_count": tracking.get("fusion_late_drop_count"),
            },
            "clock_quality": clock,
            "bandwidth": {
                "sample_count": len(payload_values),
                "json_payload_bytes": _summary(payload_values),
                "request_wire_estimate_bytes": _summary(request_values),
                "server_measured_payload_bytes_total": ingest.get(
                    "request_payload_bytes"
                ),
                "requests_per_minute_per_device": _round(
                    requests_per_minute_device
                ),
                "projections": _bandwidth_projections(
                    average_payload,
                    average_request,
                    requests_per_minute_device,
                ),
            },
            "memory": _memory_summary(backend_snapshots),
            "mailbox": mailbox,
            "restart_semantics": {
                "flutter_restart": (
                    "new process_session_id; old SQLite queue rows retain their "
                    "original process_session_id and sequence"
                ),
                "backend_restart": (
                    "bounded in-memory observations, sequence state, fusion buckets, "
                    "and shadow tracks are cleared; shadow delivery is best effort"
                ),
                "retry": (
                    "same observation_id is idempotent while the bounded Backend "
                    "tombstone TTL retains it"
                ),
            },
            "smoothing": "disabled",
        },
    }


def _app_reconciliation_totals(samples: list[dict[str, Any]]) -> dict[str, int]:
    final_by_process: dict[str, dict[str, Any]] = {}
    for sample in samples:
        key = f"{sample.get('device_id')}:{sample.get('process_session_id')}"
        reconciliation = sample.get("reconciliation")
        if isinstance(reconciliation, dict):
            final_by_process[key] = reconciliation
    fields = (
        "raw_valid_target_count",
        "observation_created_count",
        "upload_attempt_count",
        "upload_success_count",
        "observation_upload_failed_count",
        "alert_admitted_count",
        "cooldown_rejected_count",
    )
    return {
        field: sum(int(snapshot.get(field) or 0) for snapshot in final_by_process.values())
        for field in fields
    }


def _app_queue_snapshot(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "observation_queue_depth",
        "observation_queue_bytes",
        "observation_queued_total",
        "observation_upload_attempt_total",
        "observation_upload_success_total",
        "observation_upload_failure_total",
        "observation_retry_total",
        "observation_retry_success_total",
        "observation_retry_failure_total",
        "observation_expired_total",
        "observation_overflow_total",
        "observation_recovered_after_restart_total",
        "observation_failed_permanent_total",
        "oldest_pending_age_ms",
        "retry_delay_ms",
    )
    snapshots = [
        reconciliation
        for sample in samples
        if isinstance((reconciliation := sample.get("reconciliation")), dict)
    ]
    if not snapshots:
        return {field: None for field in fields}
    final = snapshots[-1]
    return {
        field: (
            max(int(snapshot.get(field) or 0) for snapshot in snapshots)
            if field.endswith("_total")
            else final.get(field)
        )
        for field in fields
    }


def _memory_summary(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    samples = []
    for snapshot in snapshots:
        ingest = snapshot.get("ingest") or {}
        tracking = snapshot.get("shadow_tracking") or {}
        ordering = tracking.get("ordering") or {}
        mailbox = tracking.get("mailbox") or {}
        samples.append(
            {
                "registry_entries": int(ingest.get("current_entries") or 0),
                "dedup_cache_size": int(ingest.get("dedup_cache_size") or 0),
                "sequence_gate_keys": int(ordering.get("current_keys") or 0),
                "mailbox_pending": int(mailbox.get("current_pending") or 0),
                "track_entries": int(tracking.get("current_track_entries") or 0),
            }
        )
    return {
        "sample_count": len(samples),
        "first": samples[0] if samples else None,
        "last": samples[-1] if samples else None,
        "max": {
            field: max((sample[field] for sample in samples), default=0)
            for field in (
                "registry_entries",
                "dedup_cache_size",
                "sequence_gate_keys",
                "mailbox_pending",
                "track_entries",
            )
        },
        "cleanup_count": int(
            ((snapshots[-1].get("ingest") or {}).get("cleanup_count") or 0)
        )
        if snapshots
        else 0,
        "field_plateau_conclusion": (
            "requires at least 30 minutes of periodic snapshots"
        ),
    }


def _bandwidth_projections(
    payload_bytes: float | None,
    request_bytes: float | None,
    requests_per_minute_device: float | None,
) -> dict[str, Any] | None:
    if (
        payload_bytes is None
        or request_bytes is None
        or requests_per_minute_device is None
    ):
        return None
    result: dict[str, Any] = {}
    for nodes in (1, 2, 4, 6):
        result[str(nodes)] = {}
        for hours in (1, 8, 24):
            request_count = requests_per_minute_device * 60 * hours * nodes
            result[str(nodes)][f"{hours}h"] = {
                "requests": round(request_count),
                "json_payload_bytes": round(request_count * payload_bytes),
                "request_wire_estimate_bytes": round(request_count * request_bytes),
            }
    return result


def _summary(values: Iterable[int]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "p50": _percentile(ordered, 0.50),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
        "max": max(ordered) if ordered else None,
    }


def _percentile(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    index = min(len(values) - 1, max(0, round((len(values) - 1) * quantile)))
    return values[index]


def _loss(source: int, destination: int) -> dict[str, Any]:
    count = max(0, source - destination)
    return {"count": count, "percent": _ratio(count, source)}


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator * 100.0 / denominator, 4) if denominator else None


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if numeric >= 0 else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--app-log", type=Path, required=True)
    parser.add_argument("--backend-metrics", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = analyze_field_run(
        manifest,
        read_app_samples(args.app_log),
        read_snapshots(args.backend_metrics),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["evidence_valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
