# 驗證紀錄 — 2026-09-16 / Asia-Taipei

環境：本機 FastAPI，http://127.0.0.1:8786，隔離 SQLite，無正式資料庫／GCS。

## 整合檢查

執行 `tools/smoke_local.py --data-dir C:/Users/vicku/Documents/Codex/2026-09-16/new-chat/work/runtime --hold-seconds 30`，exit 0。

實際結果：

```text
PASS: API, node hello/heartbeat/disconnect, event persistence + dashboard WebSocket, command delivery/ack/result
Synthetic event retained only in the local database: local-check-ff5bd228-3aef-4eee-82bd-16292ab0f4d7
```

額外檢查：REST 回傳 LOCAL_DEMO 監聽中；命令完成狀態有持久化；斷線後固定節點仍保留。初次檢查發現上傳 token 缺漏，已由 run_local.py 自動初始化解決。CHECK 字樣節點會被原有診斷過濾器排除，因此最終檢查使用 LOCAL_DEMO。

## 瀏覽器

- 開啟完整 `/dashboard`，HTTP API 與 Dashboard WebSocket 連線。
- 模擬初始三節點 → 點「新增一架並點圖設起點」：SVG activeNodes=0、alerts=0，三節點 class 都是 shape-circle；重要資訊顯示同時偵測節點 0。
- LOCAL_DEMO 連線時總覽顯示監聽中；程序結束後顯示離線並保留位置。
- 點最新事件 → 正確事件詳情，分類 Drone、模型分數 90%、回報節點 LOCAL_DEMO。
- 點節點 → 節點管理選取 LOCAL_DEMO；離線控制按鈕禁用。
- 390×844 viewport：scrollWidth=375，三張新卡片寬度 351.2px，沒有橫向溢出。
- 恢復桌面 viewport：innerWidth=1280、scrollWidth=1265；新增卡片文字與按鈕無重疊，登錄節點計數 0/2 與節點清單一致。
- 最終讀取瀏覽器 console error 為空。

Google Maps 外部底圖沒有在這個本機環境驗證；Google marker 形狀／離線色彩由 production function 測試覆蓋。沒有實體手機、真實音訊雲端上傳或飛行精度測試。
