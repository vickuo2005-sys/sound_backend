from tools.analyze_phase4_field_shadow import analyze_field_run


def manifest() -> dict:
    return {
        "evidence_kind": "real_android_staging",
        "app_env": "staging",
        "backend_url": "https://sound-backend-staging.example.test",
        "android_devices": [{"device_id": "A01", "model": "Pixel"}],
        "duration_seconds": 300,
        "scenario": "one_node_sustained_5m",
        "network": "same_wifi",
    }


def app_sample(sequence: int, raw: int, uploaded: int) -> dict:
    return {
        "observation_id": f"obs-{sequence}",
        "device_id": "A01",
        "process_session_id": "s1",
        "sequence": sequence,
        "payload_bytes": 700,
        "estimated_request_bytes": 950,
        "reconciliation": {
            "raw_valid_target_count": raw,
            "observation_created_count": raw,
            "upload_attempt_count": raw,
            "upload_success_count": uploaded,
            "observation_upload_failed_count": raw - uploaded,
            "alert_admitted_count": 2,
            "cooldown_rejected_count": raw - 2,
            "observation_queue_depth": raw - uploaded,
            "observation_queue_bytes": (raw - uploaded) * 700,
            "observation_queued_total": raw,
            "observation_retry_total": max(0, raw - uploaded),
            "observation_retry_success_total": 0,
            "observation_retry_failure_total": max(0, raw - uploaded),
            "observation_expired_total": 0,
            "observation_overflow_total": 0,
            "observation_recovered_after_restart_total": 0,
        },
    }


def backend_snapshot() -> dict:
    return {
        "reconciliation": {
            "backend_received_count": 9,
            "unique_observation_count": 9,
            "tracking_measurement_count": 9,
            "track_point_count": 9,
        },
        "ingest": {
            "request_payload_bytes": 6300,
            "current_entries": 9,
            "dedup_cache_size": 9,
            "cleanup_count": 0,
        },
        "shadow_tracking": {
            "ordering": {
                "offered": 9,
                "sequence_gap_count": 1,
                "sequence_out_of_order_count": 1,
                "sequence_duplicate_count": 0,
                "sequence_timeout_advance_count": 0,
                "current_keys": 1,
            },
            "mailbox": {"current_pending": 0},
            "current_track_entries": 1,
            "median_point_interval_ms": 1500,
            "p95_point_interval_ms": 1500,
            "maximum_track_gap_ms": 3000,
            "fusion_revision_count": 0,
            "fusion_late_attach_count": 0,
            "fusion_late_drop_count": 0,
        },
        "clock_quality": {"clock_jump_count": 0},
    }


def test_field_analyzer_reconciles_counts_and_measured_bandwidth() -> None:
    result = analyze_field_run(
        manifest(),
        [app_sample(index, 10, 9) for index in range(1, 10)],
        [backend_snapshot()],
    )

    assert result["evidence_valid"] is True
    report = result["result"]
    assert report["reconciliation"]["raw_ai_to_backend_loss"]["percent"] == 10
    assert report["reconciliation"]["overall_observation_delivery_percent"] == 90
    assert report["bandwidth"]["json_payload_bytes"]["p50"] == 700
    assert report["bandwidth"]["projections"]["4"]["24h"]["requests"] > 0
    assert report["observation_queue"]["observation_queued_total"] == 10
    assert report["observation_queue"]["observation_queue_depth"] == 1


def test_field_analyzer_rejects_production_or_synthetic_manifest() -> None:
    invalid = manifest()
    invalid["evidence_kind"] = "synthetic"
    invalid["backend_url"] = "https://sound-backend.onrender.com"

    result = analyze_field_run(invalid, [app_sample(1, 1, 1)], [backend_snapshot()])

    assert result["evidence_valid"] is False
    assert result["result"] is None
    assert len(result["errors"]) == 2
