from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
import websockets


CANONICAL_LABELS = (
    "Airplane",
    "Car",
    "Drone",
    "Electric_saw",
    "Rainfall",
)


def classification_payload() -> dict:
    return {
        "schema_version": "classification.v1",
        "model_id": "v1_1_0_flower_drone_audio",
        "model_version": "1.1.0",
        "model_label": "Drone",
        "confidence": 0.92,
        "class_scores": {
            "Airplane": 0.03,
            "Car": 0.02,
            "Drone": 0.92,
            "Electric_saw": 0.01,
            "Rainfall": 0.02,
        },
        # Deliberately inconsistent; the server must rebuild these fields.
        "operational_class": "aircraft",
        "aircraft_probability": 0.03,
        "is_target": False,
        "drone_subtype": None,
    }


def event_payload(event_id: str, *, classified: bool) -> dict:
    payload = {
        "event_id": event_id,
        "device_id": "bi15_api_node",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "label": "drone" if classified else "non_aircraft",
        "trace_id": event_id,
    }
    if classified:
        payload["classification"] = classification_payload()
    return payload


def observation_payload(
    observation_id: str,
    *,
    sequence: int,
    classified: bool,
) -> dict:
    now = datetime.now(timezone.utc)
    payload = {
        "message_type": "observation.v1",
        "schema_version": 1,
        "observation_id": observation_id,
        "device_id": "bi15_api_node",
        "observed_at": now.isoformat(),
        "event_time_ms": int(now.timestamp() * 1000),
        "sequence": sequence,
        "process_session_id": "bi15-api-session",
        "label": "drone",
        "confidence": 0.92,
        "aircraft_probability": 0.95,
        "rms_peak": 0.5,
        "avg_rms": 0.3,
        "estimated_peak_db": 78.0,
        "estimated_avg_db": 74.0,
        "location": {
            "source": "cached_device_gps",
            "latitude": 25.033,
            "longitude": 121.565,
            "accuracy_m": 8.0,
        },
        "model_id": "v1_1_0_flower_drone_audio",
        "model_name": "V1.1.0",
        "ai_inference_time_ms": 42,
        "window_duration_ms": 3000,
        "hop_duration_ms": 1500,
        "sample_rate_hz": 16000,
        "alert_candidate": True,
        "trace_id": observation_id,
    }
    if classified:
        payload["classification"] = classification_payload()
    return payload


def json_bytes(payload: dict) -> int:
    return len(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )


def classification_equal(left: object, right: object) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    numeric_fields = {"confidence", "aircraft_probability"}
    if set(left) != set(right):
        return False
    for key in left:
        if key == "class_scores":
            left_scores = left[key]
            right_scores = right[key]
            if not isinstance(left_scores, dict) or not isinstance(right_scores, dict):
                return False
            if set(left_scores) != set(right_scores):
                return False
            if any(
                not math.isclose(
                    float(left_scores[label]),
                    float(right_scores[label]),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                for label in left_scores
            ):
                return False
        elif key in numeric_fields:
            if not math.isclose(
                float(left[key]), float(right[key]), rel_tol=0.0, abs_tol=1e-9
            ):
                return False
        elif left[key] != right[key]:
            return False
    return True


async def wait_for_dashboard_event(ws_url: str, event_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    async with websockets.connect(ws_url, open_timeout=timeout) as websocket:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"dashboard event not received: {event_id}")
            message = json.loads(
                await asyncio.wait_for(websocket.recv(), timeout=remaining)
            )
            if message.get("type") == "event_trigger" and message.get(
                "event_id"
            ) == event_id:
                return message


def find_event(events_payload: dict, event_id: str) -> dict | None:
    return next(
        (
            event
            for event in events_payload.get("events", [])
            if event.get("event_id") == event_id
        ),
        None,
    )


async def run(base_url: str, upload_token: str, timeout: float) -> dict:
    run_id = uuid.uuid4().hex[:12]
    parsed = urlparse(base_url)
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{ws_scheme}://{parsed.netloc}/ws/dashboard"
    headers = {"x-upload-token": upload_token}
    legacy_event_id = f"bi15-legacy-{run_id}"
    classified_event_id = f"bi15-classified-{run_id}"
    legacy_observation_id = f"bi15-legacy-observation-{run_id}"
    classified_observation_id = f"bi15-classified-observation-{run_id}"
    replay_observation_id = f"bi15-replay-observation-{run_id}"
    legacy_event = event_payload(legacy_event_id, classified=False)
    classified_event = event_payload(classified_event_id, classified=True)
    legacy_observation = observation_payload(
        legacy_observation_id,
        sequence=1,
        classified=False,
    )
    classified_observation = observation_payload(
        classified_observation_id,
        sequence=2,
        classified=True,
    )
    replay_observation = observation_payload(
        replay_observation_id,
        sequence=3,
        classified=True,
    )

    report: dict = {
        "run_id": run_id,
        "base_url": base_url,
        "ids": {
            "legacy_event_id": legacy_event_id,
            "classified_event_id": classified_event_id,
            "legacy_observation_id": legacy_observation_id,
            "classified_observation_id": classified_observation_id,
            "replay_observation_id": replay_observation_id,
        },
        "payload_sizes": {
            "legacy_event_bytes": json_bytes(legacy_event),
            "classification_event_bytes": json_bytes(classified_event),
            "legacy_observation_bytes": json_bytes(legacy_observation),
            "classification_observation_bytes": json_bytes(
                classified_observation
            ),
        },
    }

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        metrics_before = await client.get(
            f"{base_url}/observations/shadow/metrics", headers=headers
        )
        legacy_event_response = await client.post(
            f"{base_url}/events", headers=headers, json=legacy_event
        )

        websocket_task = asyncio.create_task(
            wait_for_dashboard_event(ws_url, classified_event_id, timeout)
        )
        await asyncio.sleep(0.25)
        classified_event_response = await client.post(
            f"{base_url}/events", headers=headers, json=classified_event
        )
        websocket_payload = await websocket_task

        events_response = await client.get(f"{base_url}/events", params={"limit": 100})
        persisted_before_refresh = find_event(
            events_response.json(), classified_event_id
        )
        legacy_refresh_response = await client.post(
            f"{base_url}/events",
            headers=headers,
            json=event_payload(classified_event_id, classified=False),
        )
        refreshed_events_response = await client.get(
            f"{base_url}/events", params={"limit": 100}
        )
        persisted_after_refresh = find_event(
            refreshed_events_response.json(), classified_event_id
        )

        legacy_observation_response = await client.post(
            f"{base_url}/observations/shadow",
            headers=headers,
            json=legacy_observation,
        )
        classified_observation_response = await client.post(
            f"{base_url}/observations/shadow",
            headers=headers,
            json=classified_observation,
        )
        replay_responses = [
            await client.post(
                f"{base_url}/observations/shadow",
                headers=headers,
                json=replay_observation,
            )
            for _ in range(5)
        ]
        await asyncio.sleep(0.4)
        metrics_after = await client.get(
            f"{base_url}/observations/shadow/metrics", headers=headers
        )

        invalid_cases: dict[str, dict] = {}
        base_invalid = event_payload(f"bi15-invalid-{run_id}", classified=True)
        mutations: dict[str, object] = {}
        partial = copy.deepcopy(base_invalid)
        partial["classification"].pop("model_version")
        mutations["partial_classification"] = partial
        unknown_schema = copy.deepcopy(base_invalid)
        unknown_schema["classification"]["schema_version"] = "classification.v999"
        mutations["unknown_schema_version"] = unknown_schema
        unknown_label = copy.deepcopy(base_invalid)
        unknown_label["classification"]["model_label"] = "Helicopter"
        mutations["unknown_label"] = unknown_label
        missing_score = copy.deepcopy(base_invalid)
        missing_score["classification"]["class_scores"].pop("Rainfall")
        mutations["missing_class_score"] = missing_score
        wrong_type = copy.deepcopy(base_invalid)
        wrong_type["classification"]["confidence"] = "high"
        mutations["wrong_type"] = wrong_type
        non_null_subtype = copy.deepcopy(base_invalid)
        non_null_subtype["classification"]["drone_subtype"] = "quadrotor"
        mutations["unexpected_drone_subtype"] = non_null_subtype

        for name, payload in mutations.items():
            payload["event_id"] = f"bi15-invalid-{name}-{run_id}"
            response = await client.post(
                f"{base_url}/events", headers=headers, json=payload
            )
            invalid_cases[name] = {
                "status_code": response.status_code,
                "safe": response.status_code < 500,
            }

        for name, value in (("nan_score", "NaN"), ("infinite_score", "Infinity")):
            raw_payload = copy.deepcopy(base_invalid)
            raw_payload["event_id"] = f"bi15-invalid-{name}-{run_id}"
            encoded = json.dumps(raw_payload, separators=(",", ":"))
            encoded = encoded.replace('"Drone":0.92', f'"Drone":{value}')
            response = await client.post(
                f"{base_url}/events",
                headers={**headers, "content-type": "application/json"},
                content=encoded,
            )
            invalid_cases[name] = {
                "status_code": response.status_code,
                "safe": response.status_code < 500,
            }

    normalized = classified_event_response.json().get("classification")
    db_before = (persisted_before_refresh or {}).get("classification")
    db_after = (persisted_after_refresh or {}).get("classification")
    ws_classification = websocket_payload.get("classification")
    metrics_before_json = metrics_before.json()
    metrics_after_json = metrics_after.json()
    replay_json = [response.json() for response in replay_responses]

    report.update(
        {
            "events": {
                "legacy_status": legacy_event_response.status_code,
                "classified_status": classified_event_response.status_code,
                "legacy_refresh_status": legacy_refresh_response.status_code,
                "server_timing": classified_event_response.headers.get(
                    "server-timing"
                ),
                "normalized_classification": normalized,
            },
            "observations": {
                "legacy_status": legacy_observation_response.status_code,
                "classified_status": classified_observation_response.status_code,
                "classified_identity": {
                    "observation_id": classified_observation_response.json().get(
                        "observation_id"
                    ),
                    "sequence": classified_observation_response.json().get(
                        "sequence"
                    ),
                    "event_time_ms": classified_observation_response.json().get(
                        "event_time_ms"
                    ),
                },
                "replay_statuses": [response.status_code for response in replay_responses],
                "replay_duplicate_flags": [
                    item.get("duplicate") for item in replay_json
                ],
            },
            "database": {
                "found_before_refresh": persisted_before_refresh is not None,
                "found_after_refresh": persisted_after_refresh is not None,
                "classification_before_refresh": db_before,
                "classification_after_refresh": db_after,
                "legacy_refresh_preserved_classification": db_before == db_after
                and db_before is not None,
            },
            "websocket": {
                "type": websocket_payload.get("type"),
                "event_id": websocket_payload.get("event_id"),
                "legacy_label": websocket_payload.get("label"),
                "classification": ws_classification,
            },
            "invalid_cases": invalid_cases,
            "metrics": {
                "before": {
                    "observation_uploaded_count": metrics_before_json["ingest"].get(
                        "observation_uploaded_count"
                    ),
                    "duplicate_observation_count": metrics_before_json["ingest"].get(
                        "duplicate_observation_count"
                    ),
                    "tracking_measurement_count": metrics_before_json[
                        "shadow_tracking"
                    ].get("tracking_measurement_count"),
                },
                "after": {
                    "observation_uploaded_count": metrics_after_json["ingest"].get(
                        "observation_uploaded_count"
                    ),
                    "duplicate_observation_count": metrics_after_json["ingest"].get(
                        "duplicate_observation_count"
                    ),
                    "tracking_measurement_count": metrics_after_json[
                        "shadow_tracking"
                    ].get("tracking_measurement_count"),
                },
            },
        }
    )

    checks = {
        "legacy_event": legacy_event_response.status_code == 200,
        "classified_event": classified_event_response.status_code == 200,
        "legacy_observation": legacy_observation_response.status_code == 202,
        "classified_observation": classified_observation_response.status_code == 202,
        "server_normalization": bool(
            normalized
            and normalized.get("operational_class") == "drone"
            and abs(normalized.get("aircraft_probability", 0) - 0.95) < 1e-6
            and normalized.get("is_target") is True
            and normalized.get("drone_subtype") is None
            and set(normalized.get("class_scores", {})) == set(CANONICAL_LABELS)
        ),
        "db_roundtrip": classification_equal(db_before, normalized),
        "legacy_refresh_preserved": db_before == db_after and db_before is not None,
        "websocket_roundtrip": classification_equal(ws_classification, normalized)
        and websocket_payload.get("label") == "drone",
        "duplicate_replay": [item.get("duplicate") for item in replay_json]
        == [False, True, True, True, True],
        "invalid_cases_safe": all(
            item["safe"] and item["status_code"] in {400, 422}
            for item in invalid_cases.values()
        ),
    }
    report["checks"] = checks
    report["passed"] = all(checks.values())
    return report


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    upload_token = os.environ.get("BI15_UPLOAD_TOKEN", "")
    if not upload_token:
        raise SystemExit("BI15_UPLOAD_TOKEN is required")
    report = await run(args.base_url.rstrip("/"), upload_token, args.timeout)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
