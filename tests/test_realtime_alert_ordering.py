from datetime import datetime, timedelta, timezone

import main


def test_event_alert_timing_uses_phone_observation_time() -> None:
    now = datetime(2026, 8, 20, 4, 0, 0, tzinfo=timezone.utc)
    observed_at = now - timedelta(seconds=5)

    timing = main.realtime_alert_timing(
        {
            "rms_peak_time_ms": observed_at.timestamp() * 1000,
            "timestamp": now.isoformat(),
            "created_at": now.isoformat(),
        },
        now=now,
    )

    assert timing["alert_sequence_ms"] == int(observed_at.timestamp() * 1000)
    assert timing["alert_occurred_at"] == observed_at.isoformat()
    assert timing["alert_expires_at"] == (
        now + timedelta(seconds=main.NODE_ALERT_HOLD_SECONDS)
    ).isoformat()
    assert timing["alert_accepted_in_time"] is True
    assert timing["is_live_alert"] is True


def test_delayed_event_is_history_only_after_alert_window() -> None:
    now = datetime(2026, 8, 20, 4, 0, 0, tzinfo=timezone.utc)
    observed_at = now - timedelta(seconds=main.NODE_ALERT_MAX_LATENESS_SECONDS + 1)

    timing = main.realtime_alert_timing(
        {
            "device_event_time_ms": observed_at.timestamp() * 1000,
            "created_at": now.isoformat(),
        },
        now=now,
    )

    assert timing["alert_accepted_in_time"] is False
    assert timing["is_live_alert"] is False
    assert main.parse_datetime(timing["alert_expires_at"]) > now


def test_event_arriving_near_deadline_still_displays_for_full_hold() -> None:
    now = datetime(2026, 8, 20, 4, 0, 0, tzinfo=timezone.utc)
    observed_at = now - timedelta(seconds=main.NODE_ALERT_MAX_LATENESS_SECONDS - 1)

    timing = main.realtime_alert_timing(
        {
            "rms_peak_time_ms": observed_at.timestamp() * 1000,
            "created_at": now.isoformat(),
        },
        now=now,
    )

    assert timing["alert_accepted_in_time"] is True
    assert timing["alert_expires_at"] == (
        now + timedelta(seconds=main.NODE_ALERT_HOLD_SECONDS)
    ).isoformat()
    assert timing["is_live_alert"] is True


def test_fusion_group_expiry_uses_last_sound_not_late_backend_update() -> None:
    now = datetime(2026, 8, 20, 4, 0, 0, tzinfo=timezone.utc)
    sound_time = now - timedelta(seconds=main.NODE_ALERT_MAX_LATENESS_SECONDS + 5)

    timing = main.realtime_alert_timing(
        {
            "last_event_time": sound_time.isoformat(),
            "region_updated_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_at": now.isoformat(),
        },
        now=now,
    )

    assert timing["alert_occurred_at"] == sound_time.isoformat()
    assert timing["alert_accepted_in_time"] is False
    assert timing["is_live_alert"] is False


def test_fusion_group_display_uses_latest_backend_update_time() -> None:
    now = datetime(2026, 8, 20, 4, 0, 0, tzinfo=timezone.utc)
    sound_time = now - timedelta(seconds=5)
    created_at = now - timedelta(seconds=12)

    timing = main.realtime_alert_timing(
        {
            "last_event_time": sound_time.isoformat(),
            "created_at": created_at.isoformat(),
            "updated_at": now.isoformat(),
        },
        now=now,
    )

    assert timing["alert_received_at"] == now.isoformat()
    assert timing["alert_expires_at"] == (
        now + timedelta(seconds=main.NODE_ALERT_HOLD_SECONDS)
    ).isoformat()
    assert timing["alert_accepted_in_time"] is True
    assert timing["is_live_alert"] is True


def test_duplicate_event_metadata_keeps_first_receipt_time(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "event_receipt_time.db"
    monkeypatch.setattr(main, "DB_NAME", str(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main.init_sqlite_db()

    event = main.SoundEvent(
        event_id="evt-receipt",
        device_id="node_A01",
        timestamp="2026-08-20T04:00:00+00:00",
        label="aircraft",
    )
    first_received = "2026-08-20T04:00:01+00:00"
    audio_refresh = "2026-08-20T04:00:12+00:00"

    first_id, first_inserted = main.upsert_event_sqlite_with_inserted(
        event, first_received
    )
    event.audio_path = "events/evt-receipt.mp3"
    second_id, second_inserted = main.upsert_event_sqlite_with_inserted(
        event, audio_refresh
    )

    with main.get_sqlite_connection() as connection:
        row = connection.execute(
            "SELECT created_at, audio_path FROM events WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()

    assert first_inserted is True
    assert second_inserted is False
    assert second_id == first_id
    assert row["created_at"] == first_received
    assert row["audio_path"] == "events/evt-receipt.mp3"


def test_dashboard_never_restarts_expired_websocket_alerts() -> None:
    response = main.dashboard_v4_clean()
    html = response.body.decode("utf-8")

    assert "latestLiveAlertOccurredAt" in html
    assert "function acceptLiveAlert" in html
    assert "activateAlertsForGroup(group, true)" not in html
    assert "alertUntil.set(data.device_id, Date.now() + alertDurationMs)" not in html


def test_dashboard_enforces_listening_and_latest_alert_batch_order() -> None:
    html = main.dashboard_v4_clean().body.decode("utf-8")

    assert "device?.is_listening === true" in html
    assert "const alertOccurredAt = new Map();" in html
    assert "function advanceLiveAlertWatermark" in html
    assert "const alertOrderingToleranceMs = 1500;" in html
    assert "function latestGroupDeviceIds" in html
    assert "item.relativeMs + alertOrderingToleranceMs >= latestRelativeMs" in html
    assert "acceptLiveAlert(data, true)" not in html


def test_events_api_includes_realtime_alert_contract(monkeypatch) -> None:
    event_time = datetime(2026, 8, 20, 4, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        main,
        "list_recent_events",
        lambda limit: [
            {
                "event_id": "evt-contract",
                "device_id": "node_A01",
                "label": "aircraft",
                "device_event_time_ms": event_time.timestamp() * 1000,
                "created_at": event_time.isoformat(),
            }
        ],
    )

    response = main.list_events(limit=20)
    event = response["events"][0]

    assert event["alert_occurred_at"] == event_time.isoformat()
    assert event["alert_sequence_ms"] == int(event_time.timestamp() * 1000)
    assert "alert_expires_at" in event
    assert "is_live_alert" in event
