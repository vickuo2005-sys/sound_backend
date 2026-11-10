# 新 GCS 音訊儲存與 Google Maps

Core 事件、分類 metadata、節點、融合、軌跡、WebSocket、CSV 與 Simulation 可在無 GCS 下運行。Audio Evidence 需要獨立的 GCS 設定。即時 binary audio WebSocket 是另一條資料路徑。

## GCS

1. 在自己的 Google Cloud project 啟用 Cloud Storage API，建立私有 bucket 與專用 service account。
2. 在該 bucket 授予服務帳戶 `roles/storage.objectUser`，涵蓋寫入、讀取與重送同一物件的覆寫需求。若使用自訂角色，確認 `storage.objects.create`、`storage.objects.get` 及覆寫所需 `storage.objects.delete`。 [Cloud Storage IAM](https://docs.cloud.google.com/storage/docs/access-control/iam-roles)
3. 依組織政策建立該帳戶的 JSON key，在 host secret store 保存。既有程式以 `Credentials.from_service_account_info` 讀取 JSON。若組織禁止建立 key，audio 路徑需要另案接上組織允許的身份方式。現有實作只有 GCS client，S3／MinIO 或單獨 ADC 需要 adapter 或認證程式變更。
4. 注入 `GCS_BUCKET_NAME=<YOUR_GCS_BUCKET>`（純 bucket 名）與 `GOOGLE_APPLICATION_CREDENTIALS_JSON=<YOUR_SERVICE_ACCOUNT_JSON>`（JSON 全文）。不要傳 key file 路徑。用 `/runtime-status` 的 `gcs_configured` 確認兩個值存在，實際權限由下方上傳／讀取驗收確認。

## Evidence 路徑

先用 [First Event](FIRST_EVENT_GUIDE.md) 建立 event。`POST /upload-audio` 以 `x-upload-token` 授權，用 multipart `event_id`、`device_id`、`file`，可帶 `label`、`category`、`audio_format`。上傳小於 8 MiB 的有效 MP3／WAV 測試音訊，以便同時驗證 evidence read 上限。可在 Python venv 用以下範例執行。把它存為 `check_audio.py`，執行 `python check_audio.py BASE_URL EVENT_ID DEVICE_ID AUDIO_FILE`。

```python
from getpass import getpass
from pathlib import Path
import sys
from urllib.parse import quote

import httpx

base, event_id, device_id, filename = sys.argv[1:]
token = getpass("Your upload token: ")
path = Path(filename)
with httpx.Client(base_url=base, timeout=75, trust_env=False) as client, path.open("rb") as audio:
    result = client.post(
        "/upload-audio",
        headers={"x-upload-token": token},
        data={"event_id": event_id, "device_id": device_id, "label": "Drone"},
        files={"file": (path.name, audio)},
    )
    result.raise_for_status()
    assert result.json()["status"] == "success"
    endpoint = f"/events/{quote(event_id, safe='')}"
    evidence = client.get(f"{endpoint}/audio-content")
    evidence.raise_for_status()
    assert evidence.content and evidence.headers["Content-Type"].startswith("audio/")
    signed = client.get(f"{endpoint}/audio-url")
    signed.raise_for_status()
    signed_read = client.get(signed.json()["url"])
    assert signed_read.status_code == 200
    print("Audio uploaded, evidence and signed read OK")
```

物件路徑為 `audio/{drone|other}/{safe_device_id}/{YYYYMMDD_UTC}/{safe_event_id}.{mp3|wav}`。`/upload-tdoa-clip` 是另一路 WAV，檔名加 `_tdoa_clip`。primary upload 更新 `events.audio_path`、format 與 bytes。`/audio-content` 是 backend bounded read，`/audio-url` 提供 10 分鐘 GCS signed GET。確認 Dashboard 事件可播放，signed URL 僅作短期存取，不貼到報告或 Git。 [GCS signed URL](https://docs.cloud.google.com/storage/docs/access-control/signed-urls)

無音訊時 evidence 回 404，storage 不可用時 evidence 可回 503，過大為 413。上傳或簽名失敗可回 500。物件已寫入而 DB metadata 更新失敗時，保留原 event ID 重試並核對 DB 與 bucket。事件 ingest 與 dashboard 仍可運行。

## Google Maps

在自己的 Cloud project 啟用 Maps JavaScript API 與所需帳務，建立 browser key，限制到該 API 及實際 HTTP referrers，例如 `https://<YOUR_BACKEND_HOST>/*`，本機測試可加 `http://127.0.0.1:8786/*`。在 Backend 設定 `GOOGLE_MAPS_API_KEY` 並重啟。Renderer 把此 key 用於瀏覽器 script URL，權限由 referrer／API 限制保護。開 Dashboard 確認實際地理底圖與選點。空白或載入失敗時，有座標示意與 Simulation 相對座標圖可供 core 驗收。 [Google Maps API key 設定](https://developers.google.com/maps/documentation/javascript/get-api-key)
