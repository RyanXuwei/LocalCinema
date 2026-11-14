# 個人資料與遷移

所有個人狀態在 `%LOCALAPPDATA%/LocalCinema`。本文件描述欄位與不變量，不是要求 AI 打開真實資料。

## config.json

- roots：path、mode（directory／flat）、group；順序與群組可由後台調整。
- groups：穩定 id、名稱、icon 或 custom_image、更新時間；可選 hidden、password_salt、password_hash、access_revision。
- group_categories：group id → 該群組分類陣列。
- group_tags：group id → item id → 標籤陣列。
- 舊 categories／tags 保留相容資訊，不應再當成所有群組的共用分類來源。
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
| media_replacements | 新 MP4 路徑 → 原影片／集數 ID、名稱與標題 |

轉檔狀態：ready → confirmed → saved → 完成後移除記錄。saved 代表 MP4 已保存但原檔仍可能待回收，不能因其已存在就當成完成。舊版 replaced 記錄於啟動清除，識別別名仍保留。

## 識別與檔案操作不變量

影片與集數 ID 原本依來源路徑建立。保存 MP4 會改路徑，所以必須先寫 media_replacements，再於同一交易移除待辦記錄。下次掃描先套用別名，才能讓原收藏、觀看、書籤與群組標籤延續。

禁止刪除別名表來「清理已完成項目」。不覆蓋原有同名 MP4；使用額外名稱，來源更新時間會帶到保存副本。回收前核對來源與成品是否改變，並比對副本雜湊。真實回收僅使用 Windows 現代 Send2Trash，不可退回永久 unlink。

## 遷移與更新規則

現有表使用 CREATE TABLE IF NOT EXISTS，相容升級不可 DROP 或重設使用者資料。新欄位要有舊設定回退，任何格式變更先測隔離樣本。更新／解除安裝不碰 DATA。SQLite 備份請完整退出程式後進行，避免只複製主檔卻忽略 WAL。

## 自動保留模式（v1.6.0）

使用者勾選「略過人工審核」即授權當次執行期間自動確認並保存全部完成項目；不寫入個人設定，重啟預設關閉。取消勾選停止後續項目，當前單筆保存／驗證／回收會完成。自動與手動流程共用同名保護、來源變更檢查、雜湊驗證及 media_replacements；回收失敗保留 saved 記錄，同一檔案版本不持續重試，重新勾選可重試。
