# V2.4 API、憑證與 Render 部署手冊

## 固定識別
- Backend 本機：C:/sound_backend；GitHub：https://github.com/vickuo2005-sys/sound_backend
- Backend 分支：feat/v2-4-dashboard-simulation
- V2.4 功能基準：d7aa87de16fcc72c225025a48f8ba0366c4465dc
- Flutter：C:/Users/vicku/sound_detector_clean；分支 feat/v2-4-bi2-motion-field-validation；commit e593007cfd9df9c969ff6cfdd89ff8c9c9288121
- Staging：https://sound-backend-staging.onrender.com
- Render 控制台：https://dashboard.render.com/web/srv-da6kdn61egvs7392r92g
- Render 服務：sound-backend-staging / srv-da6kdn61egvs7392r92g
- Production：https://sound-backend.onrender.com；歸檔不部署正式站。

## API 使用
讀取：GET /health、/runtime-status、/events?limit=100、/device-status、/tracks?limit=20&points_limit=100、/event-groups?limit=20、/device-locations/{device_id}。
Dashboard：GET /dashboard；舊版參考：GET /dashboard/legacy。
固定位置：PUT /device-locations/{device_id}，JSON 例：
```json
{"latitude":25.033,"longitude":121.5654,"location_source":"manual_map","accuracy_m":null}
```
location_source 只接受 manual_map 或 current_gps。地圖點選不得沿用手機 GPS 誤差作為人工點選精度。DELETE 同一路徑清除固定位置，恢復 GPS。
目前指定 staging 的位置 PUT/DELETE 不需授權碼；UI 輸入欄位也隱藏。其他 API 不適用這個豁免。
音訊播放：GET /events/{event_id}/audio-url；錄音需 GCS 正確設定與實際音檔，不要把 unavailable 當作前端錯誤。
完整 request schema：本機 main.py、app/protocol、services/classification.py，以及執行中的 /openapi.json。

## 憑證與帳號
實際本機值集中在相鄰 PRIVATE 包的 CREDENTIALS.json 與 credentials/ 目錄，可直接讀取，不需解密或還原工具。inventory.json 僅列名稱與來源。私密包不包含於一般 ZIP，不提交 GitHub。
涵蓋：DATABASE_URL（含資料庫密碼）、UPLOAD_TOKEN、DEVICE_TOKEN、DASHBOARD_ADMIN_TOKEN、GOOGLE_MAPS_API_KEY、GCS service-account JSON、其他既有 staging secrets 與 Flutter staging.local.json。各原始檔獨立保存，避免不同時期值互相覆蓋。
phase4_staging_secrets.local.env 是較後期本機快照；staging_secrets.local.env 是較早期快照。兩者不視為已驗證的當前 Render 設定。當前 Maps key 另存 current_staging_maps.local.env，來源為上線 dashboard。
GCS 本機即使有憑證，當前 runtime 仍 gcs_configured=false；歸檔沒有啟用 GCS。
Render/GitHub 帳號用 GitHub SSO（專案 GitHub 帳號 vickuo2005-sys、Render 工作區 VICKUO）。沒有可讀取的帳號登入密碼，也沒有本次取得的 Render API token。不要從瀏覽器取 cookie 或密碼來交接。既有私密檔是否仍有效，依正式服務確認，不能因有備份就假設可用。

## Google Maps
使用 Maps JavaScript API，由 GOOGLE_MAPS_API_KEY 載入。既有金鑰允許 staging 網域；localhost 曾回 RefererNotAllowedMapError。驗證請使用 staging，不要繞過網站限制。若下一版需要 localhost，應在 Google Cloud Credentials 正式設定允許來源後再測試。Maps 是瀏覽器金鑰，不能當後端管理憑證。

## 已驗證的 Render 部署方法
1. 檢查 git status；保留使用者未提交修改。完成適當測試。把預定提交 push 到 feat/v2-4-dashboard-simulation。
2. 用 Codex 內建瀏覽器開啟上方控制台網址；確認 service name、ID 與 GitHub branch 都正確。
3. 若跳到 Sign In to Render，選 GitHub，由使用者在「同一個 Codex 內建瀏覽器」登入，直到回到 Render 控制台。Chrome/其他瀏覽器登入不會自動同步；不要反覆新建登入頁。沒有 user input 時不可宣稱登入完成。
4. Manual Deploy → Deploy a specific commit → 選已測試 SHA → Deploy Commit。只有確認最新提交就是目標時才用 Deploy latest commit。
5. 等待 Deploy succeeded / Live。過去約 1–2 分鐘；以實際狀態為準。維持 30 秒左右的有界等待，不反覆輸出整份日誌。
6. GET /runtime-status，核對 build.render_git_commit 等於目標 SHA，不能只看 GitHub push 成功。
7. 重新整理 /dashboard；確認 Google 底圖、Backend／WebSocket 連線、分頁、模擬退出與位置點選。位置只按取消即可驗證畫面，不必改寫真節點。
8. 需要 rollback 時在正確 staging 的 Deploys 選已知成功 SHA；部署後仍核對 runtime SHA。

建置命令：pip install -r requirements.txt
啟動命令：uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1
健康檢查：/health；手動部署。現有 Render UI 是 Free，會休眠；render.staging.yaml 寫 starter，是 blueprint 意圖，不可誤當目前方案或直接套用升級。
資料庫遷移不是部署附帶動作；POSTGRES_SCHEMA_AUTO_INIT 等應按既有遷移文件及實際環境核對。

## 本機與測試
```powershell
cd C:/sound_backend
./venv/Scripts/python.exe -m pytest -q
node tests/js/test_dashboard_status.js
node tests/js/test_dashboard_simulation_prediction.js
node tests/js/test_dashboard_location_picker.js
```
V2.4 乾淨提交驗證：231 passed，2 個既有 Pydantic 警告；三個 JS suites 通過。
本機預覽曾在 127.0.0.1:8765，使用舊 staging 唯讀快照；它不是線上環境，也不能測試資料庫儲存。新一版請明確選擇真 backend 或唯讀 mock。
Flutter config 還原到私密位置後，依 tools/validate_flutter_config.ps1 驗證 staging hostname；建置沿用 Flutter 文件，APK 本次沒有重建。
