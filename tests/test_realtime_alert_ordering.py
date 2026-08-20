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
        observed_at + timedelta(seconds=main.NODE_ALERT_HOLD_SECONDS)
    ).isoformat()
    assert timing["is_live_alert"] is True


def test_delayed_event_is_history_only_after_alert_window() -> None:
    now = datetime(2026, 8, 20, 4, 0, 0, tzinfo=timezone.utc)
    observed_at = now - timedelta(seconds=main.NODE_ALERT_HOLD_SECONDS + 1)

    timing = main.realtime_alert_timing(
        {"device_event_time_ms": observed_at.timestamp() * 1000},
        now=now,
    )

    assert timing["is_live_alert"] is False
    assert main.parse_datetime(timing["alert_expires_at"]) < now


def test_fusion_group_expiry_uses_last_sound_not_late_backend_update() -> None:
    now = datetime(2026, 8, 20, 4, 0, 0, tzinfo=timezone.utc)
    sound_time = now - timedelta(seconds=main.NODE_ALERT_HOLD_SECONDS + 5)

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
    assert timing["is_live_alert"] is False


def test_dashboard_never_restarts_expired_websocket_alerts() -> None:
    response = main.dashboard_v4_clean()
    html = response.body.decode("utf-8")

    assert "latestLiveAlertOccurredAt" in html
    assert "function acceptLiveAlert" in html
    assert "activateAlertsForGroup(group, true)" not in html
    assert "alertUntil.set(data.device_id, Date.now() + alertDurationMs)" not in html


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
