# 開發、測試與 Windows 打包

## 環境

使用 Windows x64 與 Python 3.12；程式使用 Tk、標準庫 HTTP、SQLite，不需要 Node 建置工具。Node 只用於 JS 回歸測試。依賴以 requirements.txt 為準，沒有雲端服務／API 金鑰需求。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe LocalCinema.pyw
```

啟動正式後台會使用個人資料；自動化測試禁止直接開正式後台，請用隔離 fixture 或 self-test。

## 測試

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node tests/short_scroll.cjs
node tests/hover_preview.cjs
node tests/player_navigation.cjs
```

Python 測試在匯入 cinema 前替換 LOCALAPPDATA，建立虛構目錄及 SQLite。目前共有 27 項測試，涵蓋模式與深度、平鋪子片源接管、群組標籤、頻道授權撤銷／限制、換檔識別、回收中斷重試、快取搬移／清理／損壞保留、進度解析、視窗邊界，以及合成影片的實際 FFmpeg 轉檔與停止／重啟。數量僅是本次文件盤點，新增測試後應更新。JS 測試提取實際 Short 函式，以合成幾何模型驗證載入／清理不移動畫面、清理後不跳片。這不是瀏覽器實機視覺驗證。

對安全與資料流程的修改，請依需求補實際 HTTP 測試；不要只斷言程式碼內存在某字串。不要用使用者媒體或真實回收筒做 fixture。

## Windows 打包（須使用者明確要求）

先從官方來源準備 Inno Setup（已用 6.7.4 封裝過）。此儲存庫不自動下載或安裝編譯器。

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\packaging\build_windows.ps1 -Python .\.venv\Scripts\python.exe -InnoCompiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

腳本讀 version.py、收集本機 assets／index.html／imageio_ffmpeg，產生無主控台的 onedir 程式，先執行隔離 self-test，再由 packaging/setup.iss 產生 dist/LocalCinema_Setup_v版本_x64.exe 及 SHA256。build／dist 不入 Git。

安裝固定 AppId、目前使用者權限、可選桌面捷徑，不自動啟動程式；不刪除 LocalAppData/LocalCinema。已有安裝版沿用這個 AppId，不得每版更換。正式更新前完整退出舊後台。歷史已使用此流程封裝至 v1.6.0，內建隔離 self-test 曾通過；目前 v1.11.3 尚未打包。舊安裝包、舊 SHA256 或舊報告不得用作目前版本證據。安裝邏輯沿用固定 AppId 與個人資料分離規則。

未做程式發行者數位簽章。自行散布二進位前，確認第三方元件、FFmpeg 組建與對應授權／來源；不要用根目錄 MIT 覆蓋其條件。

## 手動驗證清單

- 後台分頁、群組排序、右鍵移動來源與 X 提醒／系統列。
- 前端群組／標籤切換，隱藏頻道的未授權媒體拒絕與解鎖／重鎖。
- Short 連續下滑、定時換片、切回完整播放器、清理後沒有回頂。
- 更新前後收藏／進度／書籤；只用合成影片測試保存與回收。
- 單一服務按鈕啟動／停止兩輪；實際中止合成影片轉檔、清理 .partial.mp4、保留原檔與完成快取並可重啟。
- 自動保留勾選偏好與 paused 狀態分離；服務停止時不再接續處理，當前保存／回收單筆安全完成。
- 快取目錄在轉檔視窗「快取與空間」分頁；檢查搬移、清理與不同階段進度，使用合成檔案測試驗證失敗保留。
- 確認沒有啟用永久刪除回退，也沒有更改防火牆或讀取個人片庫。

## 發行

同步 version.py、index.html 頁尾、CHANGELOG。檢查 git diff 與待提交檔案，避免個人資料。安裝包宜由 Releases 發行，而非提交大型 EXE 到 Git 歷史。是否已有遠端 Release 需實際確認，不根據本機產物推定已發布。使用者規定只有明確要求時才打包；每次改版完成均提供實際程式路徑與打包／同步狀態。純文件整理不升程式版本。

滑鼠預覽回歸測試使用實際 index.html 函式、合成 DOM、虛擬時鐘與 API 回應，檢查靜止 500ms、長短影片 10% 起播、輪詢不中斷與來源移除立即停止。這不代表已在真實瀏覽器驗證解碼或自動播放政策。
