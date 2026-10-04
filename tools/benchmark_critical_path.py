"""Local synthetic end-to-end Python path benchmark; no external DB or deploy.

Run with --output outputs/critical_path_before.json (or after.json).
Uses real ingestion, existing executors, Fusion, Tracking, SQLite persistence,
and in-memory send_json transport. Excludes HTTP network, browser and DB network.
"""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def summary(values):
    from services.latency_diagnostics import LatencyDiagnostics
    return {"n": len(values), "p50": LatencyDiagnostics._percentile(values, .5),
            "p95": LatencyDiagnostics._percentile(values, .95),
            "max": max(values) if values else None}


async def run(main, directory, iterations):
    from services.latency_diagnostics import LatencyDiagnostics
    results = {}
    class Sink:
        async def send_json(self, message):
            # Real manager await/send path; no network or browser is simulated.
            return None
    main.dashboard_manager.active_connections = [Sink()]
    connections=[]
    original_connect=main.get_sqlite_connection
    def tracked_connect():
        connection=original_connect()
        connections.append(connection)
        return connection
    main.get_sqlite_connection=tracked_connect
    for scenario in ("single_event", "2_node_burst", "4_node_burst", "repeated_same_group",
                     "new_group", "merge_case", "tracking_update"):
        rows = []
        for index in range(iterations):
            main.DB_NAME = str(Path(directory) / f"{scenario}-{index}.sqlite")
            main.init_sqlite_db()
            main.invalidate_device_fixed_location_cache()
            main.invalidate_tracks_cache()
            main.latency_diagnostics = LatencyDiagnostics()
            base = datetime.now(timezone.utc)
            async def submit(node, offset, suffix):
                t = base + timedelta(seconds=offset)
                event = main.SoundEvent(event_id=f"{scenario}-{index}-{suffix}",
                    device_id=f"node_{node}", timestamp=t.isoformat(),
                    device_event_time_ms=int(t.timestamp()*1000),
                    label="aircraft", latitude=25.0 + node*.0001,
                    longitude=121.0 + node*.0001, rms_peak=.8)
                await main.create_event(event, main.Response(), "local-benchmark")
                return event.event_id
            async def drain(count):
                for _ in range(2000):
                    snap=main.latency_diagnostics.snapshot()
                    if (len(snap["critical_path_traces"])>=count and
                        all(v==0 for v in snap["pending_jobs"].values()) and
                        snap["stages"].get("post_ingest_worker",{}).get("count",0)>=count and
                        snap["stages"].get("device_status_worker",{}).get("count",0)>=count):
                        # Pending counts mean queue only; wait for worker completion too.
                        await asyncio.sleep(.005)
                        return
                    await asyncio.sleep(.005)
                raise RuntimeError("local benchmark did not drain")
            seeds = []
            if scenario == "merge_case":
                seeds=[(1,0),(4,40)]
            elif scenario in {"repeated_same_group", "tracking_update"}:
                seeds=[(1,0),(2,.1)]
            elif scenario == "new_group":
                seeds=[(1,-90)]
            for si,(node,offset) in enumerate(seeds):
                await submit(node,offset,f"seed{si}")
                await drain(si+1)
            seed_count=len(seeds)
            nodes=2 if scenario=="2_node_burst" else 4 if scenario=="4_node_burst" else 1
            ids=await asyncio.gather(*(submit(n+1 if nodes>1 else 3,
                        20 if scenario=="merge_case" else 1+n*.05,
                        f"measured{n}") for n in range(nodes)))
            await drain(seed_count+nodes)
            snap=main.latency_diagnostics.snapshot()
            for trace in snap["critical_path_traces"]:
                if trace["event_id"] not in ids: continue
                times=trace["timestamps_ms"]
                def duration(start,end):
                    return times[end]-times[start] if start in times and end in times else None
                rows.append({"event_id":trace["event_id"],"outcome":trace["outcome"],
                    "sql":trace["sql_statement_count"],
                    "timestamps_ms":trace["timestamps_ms"],"stage_samples":trace["stage_samples"],
                    "first_position_backend_ms":duration("backend_event_received","websocket_event_group_sent"),
                    "fusion_to_position_ms":duration("fusion_started","websocket_event_group_sent"),
                    "queue_wait_ms":duration("post_ingest_enqueued","post_ingest_started"),
                    "tracking_followup_ms":duration("tracking_started","websocket_track_update_sent"),
                    "fusion_ms":sum(trace["stage_samples"].get("event_fusion",[])),
                    "tracking_ms":sum(sum(trace["stage_samples"].get(k,[])) for k in ("region_tracking","active_alert_tracking")),
                    "websocket_broadcast_ms":sum(trace["stage_samples"].get("websocket_broadcast",[])),
                    "pool_acquisition_ms":None,"advisory_lock_wait_ms":None})
            # SQLite context managers commit but do not close handles. Release outside timings.
            import gc
            connections.clear()
            gc.collect()
        metrics={key:summary([r[key] for r in rows if r[key] is not None]) for key in
            ("first_position_backend_ms","fusion_to_position_ms","queue_wait_ms","tracking_followup_ms",
             "fusion_ms","tracking_ms","websocket_broadcast_ms","pool_acquisition_ms","advisory_lock_wait_ms")}
        results[scenario]={"iterations":iterations,"measured_events":len(rows),"metrics":metrics,
            "sql_statement_count":{key:summary([r["sql"][key] for r in rows]) for key in ("total","fusion","tracking")},
            "samples":rows}
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True)
    parser.add_argument("--iterations",type=int,default=50)
    args=parser.parse_args()
    destination=Path(args.output).resolve()
    os.environ.pop("DATABASE_URL",None)
    os.environ.update(APP_ENV="staging",UPLOAD_TOKEN="local-benchmark",
        LOCALIZATION_ENABLED="false",TRACKING_REORDER_BUFFER_ENABLED="false")
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="critical-path-", ignore_cleanup_errors=True) as directory:
        previous=os.getcwd()
        try:
            os.chdir(directory)  # import-time SQLite init cannot touch repository DB
            import main as backend
            result=asyncio.run(run(backend,directory,args.iterations))
        finally:
            os.chdir(previous)
    payload={"environment":"LOCAL_SQLITE_IN_MEMORY_WEBSOCKET","synthetic":True,"field_sla":"INSUFFICIENT_SAMPLE",
        "transport":"real send_json call to memory sink, no HTTP/WebSocket network or browser paint",
        "database_network_latency_measured":False,"tracking_reorder_buffer":"disabled only in local harness",
        "metric_limits":"per-event Fusion/Tracking/WS samples obtained from correlated stages; pool/PG lock unavailable in SQLite",
        "scenarios":result}
    destination.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    print(json.dumps({k:{"n":v["measured_events"],"first_position":v["metrics"]["first_position_backend_ms"],
        "sql":v["sql_statement_count"]} for k,v in result.items()},indent=2))


if __name__=="__main__":
    main()
