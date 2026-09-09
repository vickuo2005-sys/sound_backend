# V2.5 目前進度
後端與 staging 基準：d7aa87de16fcc72c225025a48f8ba0366c4465dc。
產品版號 V2.5；檔名 dashboard_v2_4 與分支 v2-4 是內部歷史名稱，歸檔不改動功能。

已完成：總覽左地圖右狀態、七個工作分頁、完整五類分數與歷史標示、V2.2 無人機 SVG、獨立模擬工作區與固定退出、Google Maps、點擊地圖／拖曳設定節點位置、staging 位置操作免授權碼。

位置免授權是刻意的開發設定：main.location_write_token_required 只對 service ID srv-da6kdn61egvs7392r92g 且 service name sound-backend-staging 免除。其他命令／上傳的權限保持既有規則。新 Render 服務 ID 不會自動繼承，需依下一版本環境設計明確處理。

尚未完成：精準定位、速度方向實地精度、正式警戒區與威脅分級、完整事件可信度、跨節點聲音證據。細節見會議八項需求核對及 runtime_snapshot。
沒有手機連線；GCS、localization、motion shadow、experimental motion 未啟用。模擬 ETA 不等於真實能力。

採集工具的 write-once 保護與相關測試仍是本機未提交修改，保存在 06_uncommitted_changes。README 與舊 NODE_CONTROL_FLOW 文件修改亦完整保留。不要直接用未提交 overlay 覆盖部署基準。

完整本機交接包：C:/Users/vicku/Documents/Codex/2026-09-07/new-chat/outputs/sound_detector_v2_5_handoff_2026-09-09_01
私密憑證另存相鄰 sound_detector_v2_5_PRIVATE_2026-09-09_01（不在 Git）。
