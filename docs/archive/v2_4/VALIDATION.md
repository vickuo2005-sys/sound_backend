# V2.4 歸檔驗證
乾淨 detached worktree d7aa87d：pytest 231 passed；2 個既有 Pydantic deprecation warnings。
Node：dashboard status、simulation prediction、location picker suites 全通過。
既有本次 UI 驗證：Google 底圖、1280×720 左右欄、V2.2 圖示、七分頁、模擬退出、位置點選、取消不保存、免授權碼欄位隱藏。
免 token staging API 檢查：故意使用無效 location_source，回 400 驗證錯誤而非 401；在資料庫写入前拒絕，未改變節點。
Flutter/APK 無本次功能修改：沿用上一版 93 tests / analyze 通過的歷史證據，不宣稱本次重跑。
本次歸檔未新增部署、未修改 Render 設定、未修改節點位置、未做正式站操作。
