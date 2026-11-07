# Latency Optimization Phase 3.2

## Scope

This phase reduces redundant PostgreSQL checkouts while preserving the Fusion
advisory transaction and Tracking update lock. It does not change pool limits,
worker counts, localization/TDOA, Fusion grouping semantics, or tracking math.

## Previous lifecycle

One post-ingest event could open a connection for event load, another for the
Fusion transaction, several for Tracking source/track/point reads, and another
for final save. The Phase 3.1 four-node run observed 6–7 acquisitions per
event, pool-wait totals of roughly 0.86–4.06 s, and connection holds of roughly
0.2–3.9 s. Several helper acquisitions were reported as `unknown`.

## New lifecycle and invariants

Fusion now checks out one PostgreSQL connection for event load and the Fusion
transaction. The advisory lock, observation membership writes, group rollups,
and cleanup remain in that same transaction and retain their original ordering.
The connection is returned only after the transaction context exits.

Tracking lookup helpers accept an optional existing connection. The group-track
lookup and active-track list query therefore share one checkout; final track
save remains a separate transaction. Association calculations and result
semantics are unchanged. No unrelated asynchronous operation is forced into a
transaction.

Each acquisition now carries a semantic purpose (`fusion_event_load`,
`fusion_transaction`, `tracking_track_lookup`, `tracking_save`, or the actual
current context). Per-event traces retain bounded repeated acquisition and hold
entries, total/max pool wait, and transaction duration.

## Ordering restart baseline

The tracking ordering state machine now treats the first sequence for a newly
seen key as a baseline. A continuing Android process after backend restart no
longer creates fake gaps for all earlier sequence numbers. A later N+2 sample
still records one real gap, and duplicate/out-of-order handling remains tested.

## Validation and remaining work

The complete Python and JavaScript suites must pass before staging deployment.
The post-change four-node run must compare acquisitions/event, pool wait,
connection hold, Fusion residual, Tracking residual, and post-ingest total
against the Phase 3.1 baseline. Do not claim an improvement until that run is
captured. Pool internals are reported as bounded diagnostics; pool_max remains
unchanged.
