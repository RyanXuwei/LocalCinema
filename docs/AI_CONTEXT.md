# AI 快速交接

## 目前狀態

- 應用程式版本以 version.py 為準，目前為1.2.0。
- 原始碼現在位於儲存庫根目錄；不要把忽略版控的 outputs/LocalCinema 當成主要維護來源。
- 以使用者選定的prototype為方向完成深綠前端、桌面側邊／窄版底部導覽、Banner與卡片；新增studio-layout.css與studio-navigation.js，未加入未實作的分享控件。
- README 已含完整使用說明、兩種收集圖解、實際虛構片單截圖與標為概念圖的AI prototype。
- 後續每次改版完成需同步指定GitHub，規則在AGENTS.md。不得 force push 或上傳個人資料。

## 已完成驗證

六個Python合成測試、Short幾何模型120次迴圈、Python／JS／PowerShell語法與文件連結。隔離瀏覽器檢查桌面、390px窄版、收藏、搜尋、群組及Short載入／清理。可重用Windows打包腳本已完整生成1.2.0，凍結程式隔離self-test通過。

## 尚未覆蓋

沒有讀取或測試使用者真實片庫；未做所有瀏覽器、實體手機、多裝置長時間播放與完整滲透測試。不要用概念插圖宣稱功能已實作。SQLite換檔識別／回收的安全不變量見DATA_MODEL，網路與頻道限制見SECURITY。

## 修改前

讀AGENTS、實際 owning source 與相關測試，避免重新推導錯誤假設。不要無故重寫大型index.html；視覺增量優先放既有外部樣式與導覽層。新增asset需同步HTTP白名單與封裝；版本同步頁尾及CHANGELOG。
