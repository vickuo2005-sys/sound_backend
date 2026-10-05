# V2-B staging shadow retention

No XTRIM, MAXLEN, XDEL or automatic destructive retention is enabled.
Keep the canary stream until evidence has been exported. ACK does not shrink
stream length; report retained length separately from lag + pending backlog.

The managed test instance is Render Key Value (Valkey 8.1.10), Singapore, Free,
25 MB RAM / 50 connections, noeviction, persistence OFF. A provider restart loses
all entries, including PEL. This is a short, disposable shadow experiment, not a
durability guarantee. Record restarts and abort/restart the canary population if
the stream or group disappears. [Free limitations](https://render.com/docs/free).

The audit process stores bounded contexts/dedupe keys (4,096 each) and 256 recent
observations. After a process restart it reads up to 4,096 retained entries before
the oldest pending entry (or last delivery cursor if no PEL) to restore prior phase
context. Those reads are not new consumption/ACK/latency samples. A possibly
truncated history is visible; do not claim complete lifecycle reconciliation then.

Future soak proposal: explicitly choose a replay horizon (initial proposal 24 h,
subject to memory inventory), alert at 60/75/85% memory, and stop shadow before
capacity exhaustion. Any future MINID cutoff must preserve pending and unread
entries for every group; coordinate group creation/replay. Approximate MAXLEN
alone is not pending-safe. Do not apply these proposals in this task.

Only after JSON evidence export, queue=0, PEL=0, lag=0, and explicit identification
of the disposable staging stream may an operator manually remove that stream and
its DLQ. Do not remove the Key Value instance or unrelated keys as part of cleanup.
