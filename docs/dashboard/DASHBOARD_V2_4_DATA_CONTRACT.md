# Dashboard V2.4 data contract

Date: 2026-08-31

All new presentation fields are optional and additive. Legacy REST and
WebSocket fields remain unchanged.

| Panel | Source | Fields used | Missing-data behavior |
|---|---|---|---|
| Command bar | `/health`, `/runtime-status`, `/ws/dashboard` lifecycle | `status`, `build.render_git_commit`, connection state | Shows disconnected/connecting/no build telemetry |
| Nodes Online | `/device-status` | A01-A04 `device_id`, `status` | Counts canonical slots only; reports both online and reported counts |
| Listening Nodes | `/device-status`, node/location WS updates | `status`, `is_listening` | Counts only online canonical nodes that report listening=true |
| AI Status | `/device-status` | `ai_status` | `No telemetry`; never invents READY |
| Backend | `/health`, `/runtime-status` | `status`, `build` | Connected/offline with text and icon |
| Queue | `/device-status` | `last_upload_status`, `metadata_upload_status`, `audio_upload_status` | Count is always `-`; labelled Node-reported because no app queue depth contract exists |
| Live Detection | `/events`, `event_trigger` | event identity/time/node, `classification`, `dashboard_presentation` | Waiting state or Legacy event fallback |
| Class Scores | `classification.v1` | five canonical `class_scores` | All canonical rows render; unavailable scores show `-` |
| Recent Events | `/events`, `event_trigger`, `event_audio_update` | time, node, class, score, duration, audio/location state | Empty state; maximum eight rows on Dashboard |
| Events browser | `/events` plus incremental event messages | classification, timing, signal, location, upload/audio, raw IDs | Legacy and null-safe detail |
| Map nodes | `/device-status`, node/location WS updates | canonical A01-A04 marker/effective lat/lng, status, listening, GPS accuracy | No marker without coordinates; without a Maps key, real coordinates feed a labelled relative plot |
| Latest detection marker | `/events`, `event_trigger` | effective/display coordinates | No marker without coordinates |
| Target estimate | `/event-groups`, `event_group` | existing group center/uncertainty when available | No fabricated point or region |
| Historical tracks | `/tracks`, `track_update` | existing `points`, measured/filtered coordinates | No line with fewer than two points |
| Experimental Motion | `/tracks`, `track_update`, `/runtime-status` | Backend `last_speed_mps`, `last_heading_deg`, optional quality/uncertainty, motion flags | `尚未啟用` or `資料不足`; never computes motion in browser |
| Node Status rail | `/device-status` and existing WS node updates | state, listening, GPS, AI, upload, last seen/event | A01-A04 slots show `未回報` unless the Backend reports them |
| System Health | `/health`, `/runtime-status`, node state, WS lifecycle | DB initialization error, database type, AI/GPS presence | `No telemetry` instead of fabricated Healthy |
| Audio | `/runtime-status`, event `audio_path`, `/events/{id}/audio-url` | `gcs_configured`, signed URL response | Disabled with staging-specific explanation when unavailable |

## Optional presentation metadata

### Event

`serialize_event_for_dashboard()` preserves the full input event and adds:

```json
{
  "dashboard_presentation": {
    "classification_available": true,
    "transport_label": "drone",
    "model_label": "Drone",
    "name_zh": "無人機聲音",
    "icon": "drone",
    "model_score": 0.6087,
    "operational_class": "drone",
    "is_target": true,
    "class_scores": {
      "Airplane": 0.0002,
      "Car": 0.0,
      "Drone": 0.6087,
      "Electric_saw": 0.3665,
      "Rainfall": 0.0246
    },
    "audio_available": false,
    "location_available": true
  }
}
```

The five-score object is constructed in canonical transport order. The visual
layer may sort a copy for display. `is_target` is copied only when the Backend
classification supplies a boolean; no new target policy is calculated.

### Node

The additive node presentation object identifies queue semantics as
`node_reported`, keeps `queue_count=null`, and exposes only existing upload and
GPS availability fields.

### Track

The additive track presentation object always declares
`experimental=true`, `field_validated=false`, and copies Backend speed,
heading, and optional quality. It never supplies ETA, prediction, or future
path data.

## WebSocket compatibility

V2.4 adds no required WS message type. The old `event_trigger` remains valid
with only legacy fields. Classification and dashboard presentation are
optional. Unknown fields are ignored. A reconnect always triggers a REST
snapshot before the UI declares its recovered state complete.
