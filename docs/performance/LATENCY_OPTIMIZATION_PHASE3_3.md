# Latency Optimization Phase 3.3

## Scope

This phase adds transaction-active versus transaction-hold diagnostics and
keeps the Phase 3.2 connection reuse and ordering-baseline changes. It does
not raise workers or pool limits, change Fusion grouping, change tracking
mathematics, or enable localization/TDOA.

## Fusion transaction accounting

The Fusion connection is still held for the atomic event/group mutation. The
advisory transaction lock, observation membership writes, group rollups, and
stale-group cleanup remain in one transaction because splitting them could
create duplicate groups or lose membership under concurrent nodes.

Each correlated trace now reports SQL-like child time, lock wait, Python
compute, transaction context-exit/commit time, and transaction idle residual:
`fusion_transaction_sql_ms`, `fusion_transaction_lock_ms`,
`fusion_transaction_python_ms`, `fusion_transaction_commit_ms`, and
`fusion_transaction_idle_ms`. These are non-overlapping accounting spans; they
do not claim a query plan or change transaction semantics.

## Region Tracking accounting

Region Tracking keeps its existing association thresholds and persistence
semantics. Its source/lookup/save/point-load stages are retained, and the
trace now exposes `region_tracking_unaccounted_ms` when the top-level region
span is longer than those child stages. The lookup connection is reused for
the logically related track reads; the final save remains a short atomic
transaction.

## Field comparison

Phase 3.2 reduced acquisitions from roughly 6–7/event to P50 4/P95 5 and
reduced Fusion residual P50/P95 from roughly 3563/5890 ms to 983/2930 ms. A
Phase 3.3 deployment must be benchmarked with the same four-node procedure
before claiming further improvement. The current pool diagnostic is a
point-in-time view of psycopg2's `_used` and idle lists: peak checked-out is a
historical high-water mark, while checked-out/idle/total are instantaneous.
The pool is not intentionally resized by this instrumentation; a total of one
with zero idle means one connection is currently checked out at snapshot time.

## Remaining risks

The Fusion residual may still include helper work outside the named child
spans, and the small active-alert sample cannot establish a Tracking P95.
Repeat the four-node run after deployment, review connection purpose labels for
`unknown`, and keep the node clock-quality blocker separate from all
non-localization latency conclusions.
