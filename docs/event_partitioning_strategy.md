# Partitioning: V1 parity, future isolation

derive_partition_key uses event_fusion.normalize_label on payload/metadata label,
including existing UAV/drone and plane/aircraft aliases. It does not replace the
label advisory lock, change windows, assign site IDs or affect real processing.
V1 stores the normalized label as metadata for behavioral parity only.

| Candidate | Benefit | Current obstacle |
|---|---|---|
| label | Matches current lock conflict domain | All aircraft/drone activity shares one hot key |
| device_id | Distributes ingest | Multi-device observations for one group would split |
| group_id | Serializes known group | Unknown before Fusion; groups can merge |
| site_id/region_id | Isolates independent deployment areas | Not consistently present in current inputs |
| acoustic episode key | Groups same real acoustic incident | Must prove candidate overlap, late arrivals and merge ordering |

Label-only partitioning cannot parallelize same-label events across 100 devices.
Device-only partitioning would incorrectly imply independent Fusion state.
Future site/region + candidate episode key requires explicit assignment/versioning,
an overlapping-candidate ownership rule, cross-group merge serialization, and retry tests.
Do not invent spatial partition boundaries or change the grouping algorithm in V1.

Memory bus is global FIFO with one dispatcher; retries remain in place. This is stricter
than the legacy executor and applies only to observation/tests. Redis stream IDs establish
stream insertion order, not event-time order; multiple consumers and pending recovery can
reorder same-label messages. The optional adapter does NOT implement distributed partition
ownership. Integration tests use a single dispatcher; they do not prove multi-consumer
per-partition order. Before canary, require one fenced owner per partition, monotonic
sequence/late-event policy and claim/recovery ordering tests. Keep the PG advisory lock.
