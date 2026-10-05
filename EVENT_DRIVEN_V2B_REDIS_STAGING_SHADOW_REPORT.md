# Event-Driven V2-B staging shadow 驗證報告

驗證日期：2026-10-05。四台實機目前不可用；使用者已指示先交付已驗證結果。
本輪完成程式、完整回歸、staging OFF/ON 部署、managed Redis TLS/auth 連線、
獨立合成 transport 的 pending recovery。未完成四台 Android smoke/canary、
實機 Redis outage 測試或可比較的 shadow-OFF 效能基準。沒有開始 V2C。

## 版本與最終狀態

- V2A validated SHA：`a12a32b8b9dd38a8b3c58c2e9b291f1e508b0af6`。
- 分支：`feat/event-driven-redis-staging-shadow`。
- 實際部署與測試的程式 SHA：`ae2b81b07cddf32e9a2df7c88979696c591e06c1`。
- 初次 shadow-OFF SHA：`5c128c0c0c0724d647c55a9a9624157d769d41b1`。
- 最終 service：`sound-backend-staging / srv-da6kdn61egvs7392r92g`。
- 最終 deploy：`dep-db1mpoh7lnhs73dlpj50`，Render 顯示 Live。
- 最終 `REDIS_SHADOW_ENABLED=false`、`REDIS_SHADOW_TRANSPORT_PROBE=false`。
  連線 secret 與 staging namespace 設定保留，待實機測試再啟用。
- `EVENT_DRIVEN_PIPELINE_ENABLED=false`、`REDIS_REAL_TRAFFIC_ENABLED=false`。
- Auto-Deploy：Off。之後推送本報告不會自動部署另一個版本。
- DATABASE_URL、正式服務與正式資料庫均未修改；PR #5 仍 OPEN/Draft/unmerged。

既有 post-ingest/device workers 為 2/1；PG pool 為 1–20；uvicorn worker 為 1；
localization=false；Render backend 仍 Free，未升級或修改運算資源。

## 實際執行的驗證

| 類別 | 結果 | 限制與證據 |
|---|---|---|
| 完整 pytest（tests + tools，真實 loopback Redis） | 421 passed / 1 skipped / 0 failed | 422 cases；[JSON](outputs/redis_shadow_regression.json) |
| 獨立本機 PostgreSQL 17 | 3 passed / 0 failed | isolated loopback DB；[JSON](outputs/redis_shadow_postgres_regression.json)；不與上列加總為 unique tests |
| JavaScript | 21 個測試 script 全部 exit 0 | 沿用既有 `node tests/test_*.js` |
| Dashboard inline JS | 2 個 script 語法檢查 exit 0 | `node --check` |
| compile/static/diff | 通過 | compileall、consumer 無 domain mutation 的 AST 檢查、`git diff --check` |
| shadow OFF staging | 通過 | health/dashboard HTTP 200、WebSocket；[JSON](outputs/redis_shadow_off_validation.json) |
| shadow ON managed Redis | 通過 | connected=true、TLS/auth、queue/PEL/lag=0；[runtime JSON](outputs/redis_shadow_on_runtime_status.json) |
| managed pending recovery | 通過 | PEL 1 → 新 consumer connection claim/ACK → PEL 0；[JSON](outputs/redis_shadow_pending_recovery.json) |
| 最終 shadow OFF staging | 通過 | health/dashboard/tracks/event-groups HTTP 200，WS ping/pong；[JSON](outputs/redis_shadow_final_validation.json) |
| 四台真實 Android smoke / 30–50 canary | NOT RUN | 使用者確認四台不可用；live_node_ids=[]；沒有製造假實測數據 |

完整 pytest 的唯一 skip 是未設定 isolated PG DSN 的 PostgreSQL parameter；
該路徑已在獨立 PG 測試補驗。3 個既有 FastAPI/Pydantic deprecation warnings。
新增 shadow 測試 14 個、collector 測試 5 個。

開發期間修正：EventEnvelope 原有 secret guard 會拒絕 `observation_token`
metadata，改為 `observation_id`；未移除 guard。Oversize fixture 原本只有 received
資料超限，改為同時提供超限的 canonical saved_event，保留原有兩筆拒絕斷言。
重啟時若 Received 已 ACK、Persisted 尚 pending，重新 audit 不應誤報 phase order；
加入有界、唯讀的 ACK history reconstruction，並以真實 Redis 測試覆蓋。
未刪除測試或削弱既有斷言。

首次 Render env 編輯對已遮蔽的 flag 未成功更新，第二次部署仍為 OFF。
確認後改為先顯示該非機密 flag、編輯並驗證值，第三次部署才啟用 ON。
完整部署歷程在 [redis_shadow_deploy.json](outputs/redis_shadow_deploy.json)。

## Managed Redis 與安全邊界

Render Key Value：`sound-backend-staging-shadow-v2b / red-db0vpj2d0e5s73debji0`，
Singapore、Free $0/月、25 MB、50 connections、noeviction、Persistence OFF。
Provider UI 顯示 Valkey 8.1.10；實際 INFO 回報 Redis compatibility version 7.2.4，
兩者分別記錄，不將 compatibility version 誤標為 provider 引擎版本。

使用 authenticated external `rediss` endpoint；實際 staging runtime TLS/auth
連線成功。redis-py 6.4 的 default SSL 設定要求 certificate validation 與 hostname
verification。未使用 private plaintext endpoint。
只有使用者批准的 `74.220.52.0/24`、`74.220.60.0/24` 加入此測試服務的 allowlist；
這是 Render 共用出口，不是 staging 獨占 IP，因此仍要求密碼與 TLS。
未修改 workspace 或 production networking。

URL 直接由 provider UI 傳入 staging Render secret，未寫入程式、報告或 Git。
targeted credential URL/private-key/provider-key regex 檢查無發現；這不是完整
secret scanner 的保證。Runtime diagnostics 沒有 DSN/Redis URL。
固定 scalar projection 不包含 WAV/base64/PCM；只保留 canonical fields 與 audio/object
references，EventEnvelope guard 拒絕 credential-bearing URL。

Free Redis 不具持久化；provider restart 可能丟失 stream、PEL 與 audit history。
此架構也不是 durable outbox：bounded queue 滿、publish failure、oversize 都可丟棄
shadow observation，並計數。Legacy 不等待 Redis，不因 shadow 失敗改變 HTTP success。
見 [retention](docs/redis_staging_shadow_retention.md)。本轮沒有 trim/delete managed entries。

## Managed recovery 的精確母體

測試 deployment：`dep-db1mo2ad0e5s738gel9g`。
`REDIS_SHADOW_TRANSPORT_PROBE=true` 在 primary audit 啟動前執行一次。
獨立 stream：`staging:shadow-probe:d5b0af0a600441519abcad6a97e0ce93`。
兩筆 synthetic observations 使用 synthetic_transport_probe device ID；
Received 已 ACK，Persisted 被讀取但未 ACK，隨後關閉 consumer connection。
新連線重建先前 ACK phase，claim 並 ACK Persisted，實際 PEL 1 → 0；
history_replayed=1、ordering_violations=0，兩笔訊息保留。

這證明 managed Redis abandoned-PEL recovery。沒有 kill OS process；
沒有 Android API 呼叫、domain DB write 或 WS broadcast。
使用獨立 sampler，不混入 primary Redis/legacy latency。
primary canary stream 沒有任何 Android observation，因此不能聲稱 Android 已 mirror。

## 30 項交付問題

| # | 問題 | 實際結論 |
|---|---|---|
| 1 | Exact deployed commit | ae2b81b07cddf32e9a2df7c88979696c591e06c1 |
| 2 | Staging service | sound-backend-staging / srv-da6kdn61egvs7392r92g |
| 3 | Provider/type | Render managed Key Value / Valkey |
| 4 | Region | Singapore |
| 5 | Version | UI Valkey 8.1.10；INFO compatibility 7.2.4 |
| 6 | TLS/auth/private | TLS+auth verified；external allowlisted endpoint；private plaintext 未使用 |
| 7 | Real Android events | 0 |
| 8 | Primary published | 0（独立 probe published 2，不併入） |
| 9 | Primary consumed | 0（probe consumed 2） |
| 10 | Primary ACKed | 0（probe total ACK 2，其中 recovery ACK 1） |
| 11 | Missing events | 真實事件母體為空，未判定；idle missing counter=0 |
| 12 | Duplicate | idle counter=0；真實事件未判定 |
| 13 | Ordering violations | primary idle=0；probe=0；真實事件未判定 |
| 14 | PEL peak/final | primary sampled 0/0；probe observed 1/0 |
| 15 | Stream backlog peak/final | primary sampled 0/0；未測事件高峰 |
| 16 | Local queue peak | primary 0；未測實機高峰 |
| 17 | XADD failures | primary 0；stream 無實機流量 |
| 18 | Reconnects | primary 0；未測實機故障 |
| 19 | Publish P50/P95/P99/max | 無實機樣本，null |
| 20 | Consumer lag P50/P95/P99/max | 無實機樣本，null |
| 21 | Shadow E2E P50/P95/P99/max | 無實機樣本，null |
| 22 | Legacy before P50/P95 | 無可比較四台 shadow-OFF baseline |
| 23 | Legacy with shadow P50/P95 | 無四台實機 canary |
| 24 | Legacy regression? | 未判定；不能據 idle run 宣稱安全 |
| 25 | Redis outage affected Android? | staging 實機 outage 未測；本機 exact HTTP parity 已通過 |
| 26 | Redis outage affected Fusion/Tracking? | staging 實機未測；code/test 無 consumer domain calls |
| 27 | Consumer crash recovery? | managed connection-abandon recovery PASS；OS-kill 未測 |
| 28 | Consumer staging DB writes? | NO；module/AST boundary、probe 與 runtime 宣告相符 |
| 29 | Duplicate Dashboard WS? | consumer 不 broadcast；實機端到端 duplicate reconciliation 未測 |
| 30 | Production change? | NO；PR #5 仍 Draft 未合併 |

Runtime 的 PEL/backlog peaks 每秒抽樣，可能漏掉瞬時尖峰；probe 的 1/0 是直接 XPENDING
證據。空流量 counter=0 不等於有流量時 zero loss/duplicate 的證明。

## Flags

```text
LEGACY_PATH_PRESERVED=YES (code boundary, API parity, staging checks)
REAL_ANDROID_SHADOW_TESTED=NO
REDIS_STAGING_SHADOW_ACTIVE=NO (ON connection verified, final OFF)
REDIS_AUTHORITATIVE_PROCESSING=NO
REDIS_CONSUMER_DB_WRITES=NO
REDIS_CONSUMER_WS_BROADCAST=NO
REDIS_FAILURE_ISOLATED_FROM_LEGACY=NO (full staging Android outage gate not completed; local PASS)
REDIS_PENDING_RECOVERY_ON_STAGING=YES (connection-abandon rehearsal; not OS kill)
SHADOW_EVENT_LOSS=UNDETERMINED (no real-event population)
SHADOW_ORDERING_VIOLATIONS=UNDETERMINED (no real-event population; probe=0)
LEGACY_PERFORMANCE_REGRESSION=UNDETERMINED (no comparable real baseline/canary)
REDIS_SHADOW_PERFORMANCE_SAFE=NO (not established)
READY_FOR_V2C=NO
PRODUCTION_CHANGED=NO
```

對缺少實機母體的三個旗標沒有強填 YES/NO，以避免把「未測」誤報為「無問題」。
目前沒有可用的真實效能數據，不能判定新增瓶頸、legacy regression 或 throughput。
所有 percentile 母體須分開；不得加總 stage P95。
consumer lag 排除 T3 早於 XADD reply T2 的樣本並計數；不能跨 process monotonic clock
計算 E2E，也不能將其標為 legacy first-position、網路或畫面繪製 latency。

## 修改檔案與後續實機程序

程式：main.py、services/events/redis_shadow.py、services/events/redis_shadow_probe.py、
requirements-staging-shadow.txt；工具：tools/collect_redis_shadow.py；
測試：tests/test_redis_staging_shadow.py、tests/test_redis_shadow_collector.py。
另有本報告、runbook/retention 文件與 outputs/redis_shadow_* 證據檔。
正式 requirements、Fusion/Tracking/TDOA 演算法與 schema 均未更動。
原 checkout 的未追蹤 field artifacts 保留。

實機可用後按 [runbook](docs/redis_staging_shadow_runbook.md)：先同版本四台 shadow-OFF
30–50 unique events 建 baseline；啟用 shadow、10-event smoke 全部通過後收 30–50 canary。
用 read-only collector 保存 runtime snapshots 與 event/trace IDs；記錄時間、設備數、
網路與軟體版號，另保存 Render CPU/記憶體/DB pool。同步核對 legacy accepted/persisted/
position/optional track 與 Redis phases，排除 HTTP retries 重複計數。
若 correctness 有誤或 legacy P95 增加 >10% 或 >100 ms，立即 OFF，保留證據。
實機 Redis outage 測試另做，不能由本機或 probe 結果代替。
完成後由使用者 review V2-B，再決定 V2C；不得自動開始。
