# 會議八項需求核對 — 2026-09-08

核對基準：staging 0033904bd1a3154fc5d4a908830ee7c380ca71a8、目前後端程式與既有驗證報告。程式存在不代表已啟用或已通過實地驗證。

| 需求 | 核對結果 | 已有內容 | 主要缺口 |
|---|---|---|---|
| 1. 事件時間 | 部分完成 | 事件 timestamp、片段 duration_s；事件群組 first_event_time、last_event_time、updated_at | UI 未整合群組首次偵測、最後偵測與更新時間；片段長度不可直接當作目標持續出現時間 |
| 2. 目標位置 | 區域估測已有，精準定位未就緒 | 事件回報座標、群組中心、region_geojson；定位服務有 TDOA/GCC 與誤差估計程式 | staging localization_enabled=false；目前群組走 multi_node_region，定位信心值清空。回報節點座標不等於聲源真實座標；未完成實測誤差校正 |
| 3. 移動狀態 | 歷史功能已有，運動估計仍實驗 | 軌跡列表、地圖回放；後端已有 heading、speed、motion_quality | staging 運動展示與 motion shadow 關閉；方向與速度缺多節點實地精度驗證，不能把模擬當成真實追蹤驗收 |
| 4. AI 判定 | 基本完成 | classification.v1 五類含 Drone、confidence、完整 class_scores、模型 ID/版本與目標政策 | 模型分數不等於校準後正確機率；尚無無人機機型分類欄位／模型 |
| 5. 節點資訊 | 基本完成，呈現分散 | GPS、固定座標、連線、監聽、AI、上傳狀態；群組 devices/reporting_device_ids | 參與事件的節點尚未與全部 GPS／健康資訊整合在同一事件頁；無手機可做本次真機操作驗證 |
| 6. 事件證據 | 部分完成 | 音訊上傳與播放 URL API、UI 播放器、RMS/peak dB；群組 device_relative_times；接收與時鐘診斷欄位 | staging gcs_configured=false，現有紀錄不可播放；未提供頻譜／聲譜等特徵檢視與各節點接收時間對照 UI。相對事件時間不等於精準聲波到達差 |
| 7. 威脅狀態 | 正式功能未完成 | 模擬据點保護半徑、接近/離開、預計進入與最近接近；shadow helper | 尚無正式可配置警戒區、持續接近判定及警戒分級完整流程；目前展示為 simulation-only |
| 8. 資料可信度 | 診斷資料已有，使用者功能不完整 | 節點數、GPS accuracy、時間同步 offset/RTT/quality；shadow clock diagnostics、定位與運動診斷 | 未整合事件級可信度摘要與原因；缺多節點校正，不能顯示成已驗證精度 |

## 即時部署狀態
2026-09-08 唯讀查詢 /runtime-status：
- node_websocket_connections：0
- tracking_enabled：true
- localization_enabled：false
- motion_shadow_enabled：false
- dashboard_v2_experimental_motion_enabled：false
- observation_shadow_enabled / observation_tracking_enabled：true
- live_audio_enabled：false
- gcs_configured：false

## 程式依據
- C:/sound_backend/services/event_fusion.py：group_payload、update_group_region、group_device_relative_times；群組時間、節點與區域模型。
- C:/sound_backend/services/region_localization.py：節點位置幾何區域。
- C:/sound_backend/services/localization/localization_service.py：TDOA/GCC 實作。
- C:/sound_backend/services/classification.py：五類分類契約。
- C:/sound_backend/services/tracking/motion.py、tracking_service.py：方向、速度、品質計算。
- C:/sound_backend/services/realtime/node_manager.py、observation_shadow.py：GPS、時鐘與連線診斷。
- C:/sound_backend/templates/dashboard_v2_4.html：renderTracksView、renderEventDetail、renderNodesView、renderMotion、playAudio。
- C:/sound_backend/main.py：runtime_status、音訊路由與定位開關。
- C:/sound_backend/docs/backend_intelligence/validation/BI2_MOTION_FIELD_REPORT.md：TOOLING PASS / FIELD INCOMPLETE，未完成實地精度驗證。

## 建議次序
1. 將既有事件群組時間、參與節點、位置來源、缺失資料原因整合為清楚的事件摘要，明確分開模型分數與定位品質。
2. 完成錄音儲存配置、證據時間對照與資料品質分頁。
3. 收集多節點實測，驗證定位、方向、速度與誤差。
4. 依驗證結果設計真正的警戒區與警戒分級；無資料時呈現「無法判定」，不預設安全。

本次核對沒有啟用實驗旗標或變更雲端憑證。
