# Simulation Lab 固定據點 ETA 穩定化（2026-09-18）

## 範圍與結論

本次只修改隔離的 Dashboard「模擬工作區」。它沒有變更正式事件 API、資料庫、Android 上傳格式、production 功能旗標或即時監控資料流。數值仍是模擬工程結果，尚未經實地校正。

原本的 ETA 會把最新一筆估測位置當作現在位置，再用最後兩筆估測位置的差分當速度。位置雜訊因此同時改變起點與速度，而且兩者不是同一個運動模型的狀態；接近切線時，一個雜訊點就可能讓圓交會從有解跳成無解。畫面也沒有時間平滑、短暫無效保留或持續遠離確認，所以 ETA 容易在數字、空白之間閃動。

現在的位置與速度都由同一段有限歷史的線性回歸軌跡取得，再沿用既有 constant-velocity 與直線／圓交會公式。估算器只讀取當下或過去的藍色估測點；紫色模擬真值只計算評估誤差，不會回饋估算器。

## 實際執行路徑

- `static/dashboard_simulation_lab.js` 是側邊導覽「模擬工作區」的主狀態與 UI。
- `static/dashboard_simulation_eta.js` 是新的純函式 ETA 模組，處理歷史清理、回歸運動、CPA、圓交會、RawPrediction、顯示穩定器與真值評估。
- `services/dashboard_v2_4.py` 在啟用模擬功能時，先載入 ETA 模組，再載入工作區。
- `static/dashboard_simulation_prediction.js` 是較早的固定展示情境引擎，保留其相容用途；這次的互動式 Simulation Lab 不再透過它計算 ETA。

## 演算法

每一幀以模擬時間 `referenceTimeMs` 為唯一時間基準：

1. 只保留 `measurementTime <= referenceTime` 的估測觀測，排除 future sample、無效、拒絕、重複時間戳與不合理跳點。
2. 取最近 6 秒且最多 20 點，檢查最少點數、時間跨度、最大間隔與最新點時效。
3. 分別對 `x(t)`、`y(t)` 做最小平方法直線回歸，依殘差做一次 robust 篩除，再重新擬合。
4. 在相同的 `referenceTimeMs` 評估回歸位置 `(x, y)`，回歸斜率同時給出 `(vx, vy)`。因此現在位置與速度屬於同一條擬合軌跡。
5. 以相對據點的位置和速度計算 closing speed、CPA 距離／時間，再求直線與警戒圓的第一個非負交點。這不是 `distance / speed` 捷徑。
6. 殘差 RMSE 轉成軌跡不確定度。CPA 加減不確定度後，結果分成 `LIKELY_INTERSECTS`、`LIKELY_MISSES` 與 `INTERSECTION_UNCERTAIN`。
7. `RawPrediction` 保留每幀原始 ETA、絕對進入時間、運動品質、CPA、不確定度、交會狀態與 reason。
8. 顯示層對「絕對進入時間」做 EMA，再用目前模擬時間倒數。短暫無效最多保留 2000 ms 並繼續倒數；持續遠離 1000 ms 後提早清除。單一微小負 closing speed 不會立即清除。
9. 時間軸往回時，穩定器先完整 reset，避免未來狀態污染較早的回放畫面。

手動搬移目標會開始新的 `motionSegment`，舊路徑仍可回放，但不會與新位置混在同一個運動回歸視窗。

## 工程預設值

| 參數 | 預設值 | 用途 |
|---|---:|---|
| `motionWindowSize` | 20 點 | 回歸最大樣本數 |
| `motionWindowMs` | 6000 ms | 回歸歷史長度 |
| `minimumMotionSamples` | 4 點 | 最少運動樣本 |
| `minimumMotionSpanMs` | 600 ms | 最短樣本跨度 |
| `maximumMotionGapMs` | 1600 ms | 最大相鄰觀測間隔 |
| `maximumObservationAgeMs` | 1200 ms | 最新觀測允許時效 |
| `maximumSegmentSpeedMps` | 150 m/s | 不合理跳點門檻 |
| `minimumSpeedMps` | 0.1 m/s | 低速無 ETA 門檻 |
| `entryTimeEmaAlpha` | 0.25 | 絕對進入時間 EMA |
| `etaHoldMs` | 2000 ms | 短暫 miss／uncertain 保留 |
| `departingConfirmMs` | 1000 ms | 持續遠離清除確認 |
| closing speed 門檻 | ±0.15 m/s | 接近／遠離遲滯帶 |
| `trajectoryUncertaintyMultiplier` | 2 × RMSE | CPA 容忍帶 |
| `minimumTrajectoryUncertaintyM` | 3 m | 最小不確定度 |
| `predictionHorizonSeconds` | 3600 s | 模擬最大預測範圍 |

這些數值是模擬工程預設值，不是實地校正參數。右側「ETA 工程資訊」可查看 Raw ETA、Display ETA、絕對進入時間、回歸位置、速度、樣本數、跨度、最大間隔、RMSE、closing speed、CPA、不確定度、穩定器狀態、reason、真值 ETA 與誤差。

## 前後對照

以下是測試使用的固定 20 m/s 接近軌跡，加上同一組決定性位置雜訊。欄位都是預測的絕對進入時間 `T+秒`：

| 模擬時間 | 舊：最新點＋兩點差分 | 新 Raw 回歸 | 新 Display EMA |
|---:|---:|---:|---:|
| 4 s | 12.1 s | 18.7 s | 21.0 s |
| 5 s | 無交會 | 20.1 s | 20.8 s |
| 7 s | 43.8 s | 20.1 s | 20.4 s |
| 9 s | 39.2 s | 19.8 s | 20.2 s |
| 12 s | 18.1 s | 20.0 s | 20.1 s |

這個案例的理想進入時間是 `T+20 s`。它用來驗證穩定性，不代表真實場域精度。

## 測試覆蓋

`tests/js/test_dashboard_simulation_eta.js` 固定覆蓋：A 直線接近、B 有雜訊接近、C 單幀 miss、D 持續 miss、E 轉向遠離、F tangent／near-tangent、G 已在區內、H 靜止、I 相同時間線重播一致、J 往回 seek reset、K future sample 不影響現在、L 回歸位置與速度來自同一模型。另驗證排序、去重、拒絕點、不合理跳點和真值隔離。

既有 `test_dashboard_simulation_lab.js` 與 `test_dashboard_simulation_lab_controls.js` 繼續覆蓋警戒、節點偵測、加入未定位無人機不會觸發所有節點、清除／重建、多目標與回放相容性。

## 已知限制

- 模擬定位仍是依節點距離權重合成的展示值，不是 TDOA 解算結果。
- constant velocity 不理解轉彎意圖、加速度、風場、障礙物或飛行控制計畫；真正轉向需要累積足夠新觀測後才會反映。
- 線性回歸與 RMSE 容忍帶只處理短期軌跡雜訊，不能替代感測器時間同步、定位品質模型與現地標定。
- 「抵達據點」使用較小的 20 m 圓，仍是軌跡與圓的交會，不保證飛到中心。
- 實機 ETA 上線前仍需用有時間戳、定位真值與事件標記的飛測資料校正窗口、門檻和誤差分布。
