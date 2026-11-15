# 架構

## 元件與責任

| 檔案 | 責任 |
|---|---|
| LocalCinema.pyw | 啟動、元件缺失修復引導、隔離 self-test |
| cinema.py | Tk 後台、系統列、單一執行、掃描、SQLite、HTTP API、串流、轉檔與操作視窗 |
| source_groups.py | 群組 CRUD／排序／目錄歸屬、分類與群組影片標籤、代表圖、管理視窗 |
| group_access.py | 密碼雜湊、瀏覽器解鎖 session、群組可見範圍與媒體讀取判斷 |
| operation_progress.py | 最新進度快照、作業階段與 FFmpeg 進度解析 |
| playback_storage.py | 可選快取目錄、二次驗證搬移、空間統計與低空間停止轉檔 |
| conversion_store.py | 人工確認、MP4 副本驗證、原檔回收、持久識別別名 |
| source_help.py | 目錄／平鋪片單圖解視窗 |
| index.html | 前端完整 UI、播放器、Short、隱蔽與群組選擇 |
| assets/catalog-pagination.js | 穩定亂數排序及分頁 |
| assets/playback-modes.js | 共用篩選與自動續集／隨機互斥模式 |
| assets/short-queue.js | Short 篩選片單及亂數佇列 |
| assets/interaction-controls.js | Banner 歷史、定時間隔、拖曳等互動工具 |
| assets/studio-layout.css | prototype 對齊的視覺與響應式版面 |
| assets/studio-navigation.js | 重用原控制項的側邊／底部導覽 |
| version.py | 版本號 |

## 執行流程

Tk 主執行緒維護後台與視窗狀態；HTTP 使用 ThreadingHTTPServer；掃描、轉檔與批次保存使用背景執行緒。透過 lock 與 queue 傳遞結果，不在背景執行緒直接操作 Tk 控件。

掃描原始 roots → 檢查一層內容與平鋪優先 → 合併相同來源的群組歸屬 → 套用 media_replacements → 建立媒體／圖片索引 → 補封面 → 可選背景預轉。

前端每 5 秒取得片庫與狀態；隱蔽另有同步。群組切換會關閉當前播放／Short、清除篩選與 Banner 歷史，再在所選群組建立片單。標籤由 groupCategories／groupTags 覆蓋成目前群組的值。

HTTP 請求先經 Host／Origin／LAN admission，再依群組 session 判斷。`visible_payload` 過濾前端片單與群組資料；媒體、封面、prepare、recommend 與寫入操作另有存取檢查。

## Short 維護重點

只保留有限掛載卡片並釋放離開的播放器。新增三個項目後可移除上方舊卡片；必須以目前卡片的 getBoundingClientRect 差值補償，而非假設瀏覽器未做捲動錨定。變更 DOM 時暫停 snap，下一幀恢復。導覽必須在可能清理卡片後重新找 activeCard 的索引。

## 已知限制

沒有獨立使用者帳號或多使用者資料隔離；收藏與觀看記錄仍以影片識別共用。群組標籤是例外，已獨立儲存。非原生瀏覽器格式須轉檔，損壞／受保護／缺編碼器的影片不保證可播。前端仍是單一較大的內嵌檔案，重構需保持資源路徑與封裝一致。
