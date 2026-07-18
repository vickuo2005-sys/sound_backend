# Event Fusion Testing

測試腳本：

```powershell
python tools/test_event_fusion.py
```

測試內容：

1. A01 發送 aircraft event，建立 Group 1，`node_count=1`。
2. 1 秒後 A02 發送 aircraft event，加入 Group 1，`node_count=2`。
3. A03 在視窗內發送 aircraft event，加入 Group 1，`node_count=3`。
4. 同一 `event_id` 重複處理，不新增 observation。
5. 同一 device 在 3 秒內再次發送，可保留 observation，但 `node_count` 不增加。
6. 5 秒後新的 aircraft event 建立 Group 2。
7. 3 秒內不同 label 建立不同 Group。
8. Event Fusion 故意丟出例外時，`POST /events` 仍回 200，原始 event 仍保存。
9. `GET /event-groups` 的排序與 limit 可用。
10. `GET /event-groups/{id}` 可回傳 observations。

也建議執行：

```powershell
python -m compileall main.py services tools
uvicorn main:app --host 127.0.0.1 --port 8000
```

本機啟動後可檢查：

- `http://127.0.0.1:8000/dashboard`
- `http://127.0.0.1:8000/event-groups`
- `http://127.0.0.1:8000/events`
