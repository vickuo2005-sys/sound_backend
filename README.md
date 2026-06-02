# Sound Detector Backend

Sound Detector Backend 是一個 FastAPI 後端，第一階段用途是接收多台 Android 手機聲音偵測節點上傳的聲音事件資料。

目前使用 SQLite (`sound_events.db`) 作為測試用資料庫。這個資料庫檔案不應提交到 GitHub，之後可再改成 PostgreSQL。

## 專案結構

```text
sound_backend/
├─ main.py
├─ requirements.txt
├─ .gitignore
└─ README.md
```

本機執行後可能會產生 `sound_events.db`，這是測試資料庫，已透過 `.gitignore` 排除。

## 本機啟動方式

建議先建立並啟用虛擬環境：

```bash
python -m venv venv
venv\Scripts\activate
```

安裝套件：

```bash
pip install -r requirements.txt
```

啟動開發伺服器：

```bash
uvicorn main:app --reload
```

啟動後可開啟：

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/health
http://127.0.0.1:8000/events
```

## Render 部署方式

在 Render 建立 Web Service，連接此 GitHub repository。

Render 設定：

```text
Build Command:
pip install -r requirements.txt

Start Command:
uvicorn main:app --host 0.0.0.0 --port $PORT
```

環境變數建議設定：

```text
UPLOAD_TOKEN=你的上傳 token
```

如果沒有設定 `UPLOAD_TOKEN`，程式會暫時使用預設值：

```text
test-token-123
```

## API

### GET /

確認後端是否正常啟動。

回傳範例：

```json
{
  "status": "ok",
  "message": "Sound detector backend is running"
}
```

### GET /health

健康檢查。

回傳範例：

```json
{
  "status": "healthy",
  "time": "2026-06-02T03:00:00+00:00"
}
```

### POST /events

接收 Android APP 上傳的聲音事件資料，並寫入 SQLite。

Header 範例：

```text
x-upload-token: test-token-123
```

JSON 範例：

```json
{
  "event_id": "event-001",
  "device_id": "android-phone-01",
  "timestamp": "2026-06-02T11:30:00+08:00",
  "latitude": 25.033,
  "longitude": 121.5654,
  "duration_s": 1.25,
  "rms_peak": 0.82,
  "label": "loud_sound",
  "audio_file_name": null,
  "local_audio_path": null,
  "note": "first test event"
}
```

curl 測試：

```bash
curl -X POST "http://127.0.0.1:8000/events" \
  -H "Content-Type: application/json" \
  -H "x-upload-token: test-token-123" \
  -d '{
    "event_id": "event-001",
    "device_id": "android-phone-01",
    "timestamp": "2026-06-02T11:30:00+08:00",
    "latitude": 25.033,
    "longitude": 121.5654,
    "duration_s": 1.25,
    "rms_peak": 0.82,
    "label": "loud_sound",
    "audio_file_name": null,
    "local_audio_path": null,
    "note": "first test event"
  }'
```

成功回傳範例：

```json
{
  "status": "success",
  "message": "Event received",
  "event_id": "event-001",
  "db_id": 1
}
```

如果 token 錯誤，會回傳 `401 Unauthorized`。

### GET /events

取得 SQLite 中最近 50 筆事件，方便測試。

```bash
curl "http://127.0.0.1:8000/events"
```
