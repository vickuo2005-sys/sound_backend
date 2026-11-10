# Research status｜2026-11-07

正式 Demo 是穩定工程展示 baseline，不是無人機聲學定位準確度的研究結案。狀態以 [baseline](DEMO_BASELINE_2026-11-07.md) 與 source 為準；合成資料、unit tests、瀏覽器動畫或手機連線測試不可替代 field validation。

## Implemented

| 工程功能 | 已存在的實作 | 能主張的範圍 |
|---|---|---|
| 事件／狀態／位置 | FastAPI、PostgreSQL、node／Dashboard WSS、固定節點位置 | Backend／介面工程能力，不是目標真值定位 |
| 分類結果／證據 | Classification metadata、可用 GCS 音訊、CSV | 接收／驗證／呈現分類結果；不主張 MCU 模型實地效能 |
| 事件群組／歷史 track | fusion、節點幾何區域、Alpha-Beta tracking、replay | 粗略偵測區域與歷史估測，不等於真實 UAV 軌跡 |
| Gateway test | 授權 JSON echo，無 DB 寫入 | 連通性，不是正式 Wi-SUN ingest 完成 |
| 研究原型 | Timestamp-TDOA、GCC-PHAT、時序／排序／shadow tooling | 有程式與測試，不代表已通過真實硬體／聲學驗證 |

## Simulation-only

- 自訂節點／據點、偵測半徑、多目標、失聯、情境、清除／重置、動畫回顧。
- Ground Truth 合成 proxy 量測；frontend `localize()` 是模擬 oracle／權重推估，不是 TDOA。
- Alpha-Beta 的位置／速度送入 prediction、ETA／Approach／Alert。Kalman CV 同步讀 proxy 量測，但 state／trail 獨立，僅 comparison/shadow。
- Constant-velocity prediction、警戒圈交會、ETA 平滑／品質資訊是工程演示。真值可供誤差評估，不作實際 estimator 的可用量測。
- Kalman 在特定合成直線／noise 測試中的 RMSE 改善不保證所有機動場景更平滑、更準、無 lag，也不構成實地 tuning。

Source：[`../static/dashboard_simulation_lab.js`](../static/dashboard_simulation_lab.js)、[`../static/dashboard_simulation_tracker.js`](../static/dashboard_simulation_tracker.js)、[`../static/dashboard_simulation_kalman.js`](../static/dashboard_simulation_kalman.js)、[`../static/dashboard_simulation_eta.js`](../static/dashboard_simulation_eta.js)。

## Not field validated

1. 多節點高精度時間同步／hardware capture timestamps 與聲學延遲校正。
2. 真正 acoustic TDOA 的完整取樣、同步、delay estimation、定位鏈路。
3. 實際無人機位置定位與絕對誤差分布。
4. Kalman CV 以真實量測的調參／穩定性／outlier／lag 驗證。
5. 真實 trajectory prediction、ETA、approach／departure 的準確度與失效界限。
6. MCU → Wi-SUN → Gateway 的完整 field contract、持久重送與故障恢復。

**「TDOA 尚未實作」在此是指尚未完成可用且經驗證的實際聲學定位系統。** repo 並非完全沒有 TDOA 程式：[`../services/localization/timestamp_tdoa.py`](../services/localization/timestamp_tdoa.py)、[`../services/localization/gcc_phat.py`](../services/localization/gcc_phat.py)、相關測試與 migration 已存在。這些原型不能被刪除或誤寫成正式完成能力；production／staging runtime 目前 `LOCALIZATION_ENABLED=false`。

目前正式警示／ETA 的演算法來源仍是既有 Alpha-Beta；`DEMO_STABLE_MODE=true` 與 experimental motion off 不應被文件改為 Kalman authoritative。能展示的 UI 及已實作的公式，也不等於正式提供經 field validation 的 ETA。

## Future work

```text
多節點聲音 → 時間同步／capture timestamp → acoustic TDOA
→ 位置估測＋品質／誤差 → Kalman tracking → 位置＋速度
→ Trajectory prediction → ETA／Approach → 警戒
```

每階段先在隔離 staging 定義可測量 acceptance：共同時間基準、真值記錄、node geometry、聲學環境、outlier／missing／reordered 資料、位置誤差、速度誤差、lag、prediction error、ETA calibration、false alert／missed alert。保留 source SHA、flags、資料集與測量方法，再決定是否晉級下一階段。

下一個可執行工作是先與 Gateway vendor 固定 contract、ACK 層級、event ID 與 timing 語義；完成錄製／對時／真值 protocol，再做 TDOA／Kalman 評估。不要先把 Kalman 接上正式 ETA，也不要用場景動畫取代研究數據。
