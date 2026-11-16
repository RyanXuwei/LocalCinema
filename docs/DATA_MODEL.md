# 個人資料與遷移

個人設定與資料庫固定在 `%LOCALAPPDATA%/LocalCinema`；產生的 playback 快取可另選保存目錄。本文件描述欄位與不變量，不是要求 AI 打開真實資料。

## config.json

- roots：path、mode（directory／flat）、group；順序與群組可由後台調整。
- groups：穩定 id、名稱、icon 或 custom_image、更新時間；可選 hidden、password_salt、password_hash、access_revision。
- group_categories：group id → 該群組分類陣列。
- group_tags：group id → item id → 標籤陣列。
- 舊 categories／tags 保留相容資訊，不應再當成所有群組的共用分類來源。
- groups[].kind：缺少時視為 media；"web" 為作品群組，只收網址不收根目錄。
- lock_on_page_close：是否在同一瀏覽器最後一個分頁離開後撤銷隱藏頻道授權，預設 false。
- 其他設定包含背景預轉、隱蔽等；保留未知設定，不以固定預設物件覆蓋整份檔案。

舊 roots 沒有群組時歸 default。舊共用標籤首次升級會各自複製至當時存在的群組；之後互不連動，新群組從空白開始。變更密碼或隱藏設定會改 access_revision，撤銷既有解鎖。

## library.sqlite3

| 表格 | 用途 |
|---|---|
| favorites | item_id 的收藏 |
| watches | session、影片／集數、觀看時間、position、duration |
| exposure | 推薦曝光計數 |
| keyframes | item_id／episode_id 的多個時間書籤 |
| app_settings | LAN 授權 key 等程式設定 |
| conversion_records | 已轉檔成品的人工檢查與保存待辦 |
| cache_copies | 已保存 MP4 與快取 SHA256 對應，供安全清理 |
| cache_moves | 已提交搬移的舊／新副本及 SHA256，供清理重試 |
| media_replacements | 新 MP4 路徑 → 原影片／集數 ID、名稱與標題 |
| web_works | 作品 ID、group_id、正規化 http(s) 網址、標題、建立／更新時間、快照檔名與時間、frame（allowed／blocked／unknown）、title_locked |

轉檔狀態：ready → confirmed → saved → 完成後移除記錄。saved 代表 MP4 已保存但原檔仍可能待回收，不能因其已存在就當成完成。舊版 replaced 記錄於啟動清除，識別別名仍保留。

## 識別與檔案操作不變量

影片與集數 ID 原本依來源路徑建立。保存 MP4 會改路徑，所以必須先寫 media_replacements，再於同一交易移除待辦記錄。下次掃描先套用別名，才能讓原收藏、觀看、書籤與群組標籤延續。

禁止刪除別名表來「清理已完成項目」。不覆蓋原有同名 MP4；使用額外名稱，來源更新時間會帶到保存副本。回收前核對來源與成品是否改變，並比對副本雜湊。真實回收僅使用 Windows 現代 Send2Trash，不可退回永久 unlink。

## 作品群組（v2.0.0）

作品快照存於 DATA/web-snapshots，檔名為作品 ID 加隨機尾碼的 JPEG；成功擷取新圖後才刪舊圖。使用者自填標題會鎖定，不被網頁標題覆蓋。刪除作品會在同一交易移除 web_works、favorites、exposure、watches 中該 ID，再刪快照與群組標籤。刪除作品群組會先刪除群組內全部作品。開啟作品時以 watches 記錄（episode_id 等於作品 ID）。

## 遷移與更新規則

現有表使用 CREATE TABLE IF NOT EXISTS，相容升級不可 DROP 或重設使用者資料。新欄位要有舊設定回退，任何格式變更先測隔離樣本。更新／解除安裝不碰 DATA。SQLite 備份請完整退出程式後進行，避免只複製主檔卻忽略 WAL。

## 自動保留模式（v1.6.0）

使用者勾選「略過人工審核」即授權當次執行期間自動確認並保存全部完成項目；不寫入個人設定；v1.10.0 起後台每次啟動預設勾選，v1.11.0 起服務未啟動或停止時 paused，啟動服務才恢復執行。取消勾選停止後續項目，當前單筆保存／驗證／回收會完成。自動與手動流程共用同名保護、來源變更檢查、雜湊驗證及 media_replacements；回收失敗保留 saved 記錄，同一檔案版本不持續重試，重新勾選可重試。

## playback 快取位置（v1.7.0）

app_settings.playback_directory 指定產生的快取位置，未設定時，新使用者採程式所在目錄/playback；舊版 DATA/playback 若已存在則沿用，以保留既有快取。資料庫、設定及其他 DATA 不變。搬移僅處理舊目錄第一層 64 位十六進位名稱的已完成 MP4，不遞迴、不讀取片源、不搬未完成暫存檔。先複製驗證，再於同一 SQLite 交易更新 conversion_records.output_path／成品時間戳與目錄設定；保留審核狀態、saved_path 與識別別名。提交後才清理已驗證的舊快取。失敗可重選同一目的地重試，目的地既有同內容快取可接續使用，內容不同拒絕覆蓋。

## 空間釋放（v1.8.0）

cache_copies 記錄已保存 MP4 與快取雜湊。media_replacements 與清理對應在成功回收後一併提交，之後才清理具 64 位十六進位檔名的快取；刪除前重新驗證保存副本及快取 SHA256，不刪除仍由任何待辦來源／成品／saved_path 引用的檔案。待辦或驗證失敗保留。舊版重複檔需由既有 media_replacements 找到完整相同的已保存 MP4 才可清理，不按檔案年齡盲刪。

cache_moves 在搬移路徑交易中記錄舊／新副本與雜湊，清理前驗證兩份；清理成功才移除該記錄。當回收已完成但程式中斷時，saved 記錄仍可用已保存 MP4 的雜湊驗證安全重試，不要求已回收的來源重新出現。片單識別別名不可清除。

## v1.10.0 啟動預設

完整後台啟動只預設勾選自動保留；服務啟動才實際執行。Library 合成測試與 --self-test 不會自行開啟。frozen 程式目錄取 sys.executable 所在目錄，原始碼版取 cinema.py 所在目錄。已保存的 playback_directory 設定優先於預設及舊版位置。
