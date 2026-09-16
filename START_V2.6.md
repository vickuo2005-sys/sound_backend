# Sound Detector V2.6 — 2026-09-16 會議修改

本版延續 V2.5 backend 提交 `64318467bc45b835a12680ed5c41dd5a52a2ac54`，工作分支 `feat/v2-6-monitor-overview`。原 V2.5 封存未修改。本目錄是完整後端與 Dashboard 原始碼；Flutter／既有 APK 沿用 V2.5 封存，此次沒有重建手機 APK。

## 本次完成

- 統一節點為圓形：Google Maps、相對座標圖、模擬地圖、節點清單及圖例。維持白色在線、灰色離線、橘色參與估測。
- 修正新增無人機尚未放置起點時，全節點一起警示：未知位置或失聯目標不產生偵測節點；放置後依在線狀態、啟用設定與半徑判定。
- 監控總覽新增資料連線狀態、近 60 秒無人機聲音紀錄數、節點健康、最近 5 筆事件及跳轉操作。紀錄數不是無人機架數。總節點數依已登錄節點計算。
- API 資料過期、讀取失敗與 HTTP 200 的 degraded 回應不當作零事件；保留舊紀錄並標記資料待確認。
- 有目標資訊時仍顯示系統監控狀態；獨立模擬工作區不寫入真實 API。
- 新增完整本機啟動與 API／WebSocket 整合檢查工具，使用隔離 SQLite、自動建立本機上傳 token。

## 直接查看

本次啟動的網址：<http://127.0.0.1:8786/dashboard>。

這是實際 FastAPI 服務，不是靜態頁面或 fixture。畫面中的 LOCAL_DEMO／LOCAL_CHECK 與事件為本機整合測試資料，不是實際無人機偵測。測試程序結束後節點會離線；固定位置與事件仍保留。

## 啟動方式

在此目錄使用已有依賴的 Python 執行：

```powershell
python tools/run_local.py
```

本機預設網址 `http://127.0.0.1:8786/dashboard`，資料存於 `.local-runtime/`，Ctrl+C 停止。入口只允許本機回環位址，不繼承正式資料庫或 GCS 設定。

新環境安裝：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.venv\Scripts\python.exe tools/run_local.py
```

目前這台電腦可直接使用的 Python：

```powershell
& 'C:/Users/vicku/Documents/Codex/2026-09-09/new-chat/.venv-dashboard/Scripts/python.exe' tools/run_local.py
```

本次執行中的服務另以 `--data-dir C:/Users/vicku/Documents/Codex/2026-09-16/new-chat/work/runtime` 儲存測試資料，避免將資料庫與 token 包進交付目錄。若 8786 已被這個服務使用，不必重開第二份。

## 驗證

```powershell
python -m pytest -q -p no:cacheprovider
Get-ChildItem tests/js/test_*.js | ForEach-Object { node $_.FullName; if ($LASTEXITCODE -ne 0) { throw "JS test failed" } }
python tools/smoke_local.py
```

`smoke_local.py` 僅連線 `127.0.0.1`，會建立 LOCAL_DEMO 固定節點與合成事件，驗證節點握手／心跳、事件寫入及 REST 讀回、Dashboard WebSocket 推送、命令送達／ack／完成結果、節點斷線後固定位置保留。若服務使用自訂資料目錄，smoke 工具需傳相同 `--data-dir`。

驗證紀錄見 `verification/`。瀏覽器已檢查：新增目標未定位時 0 節點警示、3 個圓形節點、總覽節點在線／離線、事件與節點跳轉、390px 窄螢幕無橫向溢出、前端無 console error。

## 現階段界線與下一階段

本版完成本機核心資料流與總覽第一版，尚未部署至 Render。Google Maps 金鑰未加入本機啟動設定時使用相對座標圖；本次沒有驗證真實 Google 底圖的視覺效果。音訊雲端上傳／播放需既有 GCS 設定，本機 smoke 不宣稱已驗收這條流程。

下一階段將此版本部署到原 staging，使用實際手機驗證持續收音、分類、音訊上傳、節點控制與斷線重連。ETA／精準定位仍沿用 V2.5 的未實地驗證實作，此次沒有聲稱完成實機定位、ETA 精度或多目標配對驗收。
