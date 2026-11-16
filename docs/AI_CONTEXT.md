# LocalCinema AI 交接

更新日期：2026-11-16。適用程式版本：v2.3.0（分支 refactor/architecture-v2）。先讀根目錄 AGENTS.md、本檔與 version.py，再按工作閱讀 README、ARCHITECTURE、DATA_MODEL、SECURITY、DEVELOPMENT。文件是導航，實際程式與重新執行的驗證優先。

## 目前狀態

- 程式版本由 version.py 決定。v1.11.0 程式提交：676cbe8768f7c20374f12ea4569daf3d9b7d5af7，已同步 main，為 v1.11.1 修正前的程式基準；目前修正以現行 HEAD 為準。純文件提交不代表程式升版。
- 根目錄為主要原始碼；outputs/LocalCinema 為使用副本，改版完成後同步所需程式、素材與文件，保留既有捷徑，不整個刪掉重建。outputs 不入 Git。
- v2.0.0 作品群組在 refactor/architecture-v2 分支開發，尚未合併 main、尚未打包。v1.12.1 為 main 最新版並有 tag。
- v1.12.1 尚未產生安裝檔。歷史曾封裝至 v1.6.0，但舊產物不保證仍存在；不可將舊 self-test 報告或 SHA256 當成最新版證據。發行前確認實際檔名、版本、雜湊及報告。
- v1.11.1 修正：服務已停止時，保留背景預轉／自動保留勾選不再阻擋快取搬移與清理；實際忙碌仍拒絕並顯示具體原因。

## 使用者已確定的工作方式

- README 僅聚焦功能、用法、注意事項、部署與版權；不放提示詞、設計推演、聊天指示與 AI 執行過程。AI 接手資訊留在本檔，開發細節留在專門文件。

- 改版驗證後例行同步 RyanXuwei/LocalCinema；不必每次再問，但禁止 force push 或提交個人資料。
- 只有使用者明確要求打包時才建立安裝檔。每次新版完成均提供可點擊的實際程式路徑，說明是否打包與是否同步。
- 桌面與程式資料夾捷徑已補回，指向 outputs/LocalCinema/LocalCinema.pyw；不要覆蓋或提交本機捷徑。
- 不自行開啟正式後台做測試。任何 UI 測試必須使用隔離設定、SQLite、虛構片單／影片，完成後退出自建視窗及控制狀態。

## 隱私與不可破壞的不變量

- 未有特定授權，不讀取、掃描、列出或引用真實片庫、名稱、來源路徑、設定、資料庫、入口碼或 QR 內容。測試只用合成資料。
- import cinema 前必須指定隔離 LOCALAPPDATA；匯入即建立 DATA。Library 測試與 --self-test 不啟用自動回收。
- 設定、SQLite、封面等 DATA 固定在 LocalAppData/LocalCinema；playback 可另選位置。新使用者預設程式同層/playback，舊 DATA/playback 存在時沿用，已自訂目錄優先。
- 掃描一層邊界、平鋪子片源優先、群組獨立標籤、後端隱藏頻道授權與 media_replacements 識別別名不可破壞。
- 來源影片只能經保存／驗證後回收，禁止永久刪除回退或覆蓋同名 MP4。程式快取的已驗證重複副本可依安全清理流程移除，不能據此放寬原始影片規則。

## 後台群組合併（v2.3.0）

- 使用者要求：作品群組與片源群組只有一個管理入口；管理視窗內「新增網路作品」建立 web 群組；後台分頁含 web 群組，切換時按鈕改為新增作品網址並顯示網址列。open_group_manager 不再有 kind 參數。後台 watch_works 每 2 秒比對作品簽章刷新。已以隔離資料啟動完整後台截圖確認兩種分頁。

## 作品備註（v2.2.0）

- web_works.notes 由 clean_notes 正規化換行、去除行尾空白，上限 5000 字；update(notes=None) 表示不變。舊資料表以 PRAGMA table_info 檢查後 ALTER TABLE 補欄位。前端備註面板 #webNotes，設定鍵 localcinema:web-notes-open。使用者說明備註會放專案背景、帳號密碼、開發資源路徑與參考連結；v2.2.1 讓 http(s) 連結可點。明碼保存與傳輸的風險已寫入 README／SECURITY，尚未做遮罩或加密。

## 作品群組修正（v2.1.1）

- Short 作品卡不用 installShortScrub，改用 installWebShortGesture：滑鼠拖曳捲動、放開超過 40px 換卡，移動超過 8px、捲動過或按壓超過 600ms 都不觸發點擊。
- 重新擷取：getDisplayMedia(preferCurrentTab)＋CropTarget（可用時）擷取檢視器區域上傳；任何失敗都退回主機 capture_now（virtual-time 1.5 秒，同步回應）。內建瀏覽器窗格會自動拒絕分頁擷取，所以實測走的是主機路徑；真實 Edge／Chrome 的分享提示路徑未實測。
- 新增後 refreshWebNow 等待輪詢結束再刷新，watchWebSnapshots 在有 snapshotPending 時每 1.5 秒刷新。

## 品牌署名開關（v2.1.0）

- 使用者要求後台可選隱藏網頁上的 BitingBox 與 Ryan Hsu 署名：config.hide_branding，預設 false。只以 html.hide-branding 隱藏 header .sub 與 .studio-credit、改分頁標題；原始碼、README、LICENSE 與後台 Logo 保留。預設仍須顯示署名。

## 作品群組（v2.0.0）

- 使用者確定：作品只支援網址；作品群組與片源群組同一個首頁選單，隱藏頻道／密碼規則相同；刪除作品須兩次確認；卡片與 Short 只顯示快照，放大才載入真實網站，另有以分頁開啟。
- web_works.py 管理 SQLite web_works 與快照佇列（單一背景執行緒）。快照用 Edge／Chrome `--headless=new --virtual-time-budget=10000`，即網頁時間 10 秒，實際耗時通常數秒。合成網頁（8 秒後變色）實測擷取到變色後畫面。
- 測試：tests/test_web_works.py（網址規則、嵌入政策、增刪改與快照替換、群組 kind、隱藏群組與 HTTP 路由）。前端以隔離資料與本機合成網站在內建瀏覽器實測卡片、檢視器、禁嵌提示、手機寬度、新增、兩次確認刪除與 Short；後台群組視窗以隔離 Tk 程式化檢查，主視窗按鈕未做畫面截圖驗證。

## 最新後台與服務行為

- v1.12.0 新增 lock_on_page_close 後台選項，預設 false。只在同瀏覽器最後一個分頁離開時撤銷隱藏頻道授權。首頁設 HttpOnly／SameSite=Strict 的 cinema_pages 識別 cookie，伺服器生成頁面 ID 並先登記，解鎖前已開啟的其他頁也計入。pagehide 以 keepalive POST 送關頁通知，仍須 LAN admission、Host／Origin 與 X-Cinema-Token。15秒心跳／90秒租約，逾時在後端存取檢查失效，背景頁遭節流可能保守鎖定。開啟選項會撤銷所有現有隱藏頻道授權；不是停止服務或清除 LAN admission。

- 啟動／停止合併為一個切換按鈕，停止中鎖定按鈕並非阻塞 UI。
- 後台每次啟動預設勾選「略過人工審核」，但服務尚未啟動時 paused，不自動處理。服務啟動後才恢復，停止後偏好保留但暫停。
- 停止服務關閉 HTTP、中止 FFmpeg（包含影片長度探測）、清空待轉佇列，清理當次未完成暫存；已完成快取與來源影片保留。中斷影片下次從頭轉。
- 保存／回收中的單筆先安全完成，再停止後續項目；掃描退出前仍顯示停止中。取消背景預轉勾選只停止後續排程，與停止整個服務不同。
- 「開啟入口頁」含系統列選單，優先預設路由的區網 IPv4 並帶完整 access，無位址才 loopback。預設綁 0.0.0.0，啟動不自動開瀏覽器。
- QR 在本機生成；LAN 授權 Cookie 為 HttpOnly／SameSite=Lax，群組授權仍 SameSite=Strict。不要宣稱所有手機掃碼器或網路都已驗證。
- Windows 主視窗預設 1160×850、轉檔視窗 1280×850，依工作區置中／縮小；主視窗可捲動。

## 轉檔、空間與進度

- 轉檔視窗有「轉檔記錄」與「快取與空間」。後者集中目錄選擇、搬移、容量及安全清理。
- 勾選略過人工審核會停用原有三個手動動作；自動及手動共用先保存、完整雜湊驗證、再回收的流程。失敗待辦保留，重新勾選可重試。
- 成功保存／驗證／回收並提交識別別名後，才重新核對保存副本與快取、清除重複快取。只完成轉檔、唯一副本或待辦引用不刪除。
- 舊版重複快取可手動清理，但須比對已保存 MP4；不是清空 playback，不按年齡盲刪，也不清回收筒。
- 搬移前按停止服務並等待停止完成；背景預轉與略過人工審核可保留勾選。只處理第一層 64 位十六進位檔名的完整 MP4；不搬原始片源、不遞迴、不搬 .partial.mp4。
- 搬移採複製、驗證、提交前二次驗證、同一交易更新位置／記錄，再核對清理舊副本。cache_moves 記錄供中斷清理重試；cache_copies 不取代 media_replacements。
- 空間低於 512 MiB 不啟動新轉檔；執行中低於 256 MiB 則停止並清理當次暫存。
- operation_progress 只存最新快照，不累積每區塊 UI 事件。轉檔百分比來自 FFmpeg 時間；未知長度使用活動條，編碼中最高 99.9%。搬移／清理為階段及單檔百分比，不能說是整項總完成率。

## 前端與品牌延續

- v1.12.1：無自訂圖片時，自動封面由 cache_video_poster 取影片10%時間點，長度未知回退0秒。frame10-v1 縮圖快取前綴避免沿用固定5秒舊圖；重新掃描才產生新圖，舊生成圖不盲刪，使用者自訂封面優先。合成紅藍影片驗證實際擷取位置。

- v1.11.3：音量／倍速上方 hover bridge 改為 6px 且限制在按鈕寬度，未展開時不接收指標；桌面選單縮小，seekRow 上移並增加下方間距。隨機模式下 nextEpisode 使用 PlaybackModes.next 切換目前篩選範圍內的下一部，不只變更 disabled；切換模式立即同步可用狀態。tests/player_navigation.cjs 驗證實際函式，樣式尚未實際瀏覽器操作驗證。

- v1.11.2：卡片／列表列滑鼠靜止 500ms 啟動預覽，從任何有效片長的 10% 起播，不再限制最多30秒。一般輪詢更新延後列表重建，離開後套用；群組／影片／集數識別變更仍即時停止預覽。錯誤提示保留，不瞬間移除。tests/hover_preview.cjs 直接執行實際函式的合成 DOM／時鐘測試，非真實瀏覽器影片驗證。

- 深綠／米白、細線鏤空圖示；片源頭像不套毛玻璃，大方形 App 頭像桌面 52px、窄版 46px。
- 頁尾使用 bitingbox-studio-plaque.svg；只移除使用者授權的米白外底，玉綠牌匾、文字與品牌路徑保留。後台 bitingbox-studio.png 由同一稿輸出透明 RGBA。原 Logo 待選配色的討論已結束，不再列待辦。
- 保留映室／LOCAL CINEMA、BitingBox Studio 與 Created by Ryan Hsu. 2026 © Copyright。
- 關鍵幀一鍵加入時間軸旗標；跳轉不改播放狀態，暫停並在旗標 ±0.15 秒時再點刪除。
- Short 追加與裁剪按實際 anchor 幾何補償，清理後重算導覽索引；不可改回固定高度扣 scrollTop。
- 篩選面板互斥、外點或 Esc 關閉，內部勾選保留展開。截圖是歷史合成資料範例，不是目前所有後台狀態的證據。

## 驗證與發行邊界

- 上次程式驗證：31 項 unittest 通過，含合成影片實際 FFmpeg 轉檔／中止／重啟、快取驗證搬移／清理、授權與識別保留。
- node tests/short_scroll.cjs 通過 120 次追加／清理模型；這不是實體手機測試。
- 隔離 Tk 曾驗證服務切換兩輪、預設勾選、進度、目錄搬移與安全清理。沒有以真實片庫驗證，沒有跨實體磁碟故障或所有手機／瀏覽器長時間測試。
- 新改動按範圍重跑測試，不把上次報告當成本次證據。純文件變更做連結、內容一致性及 diff 檢查即可。
- 打包用 packaging/build_windows.ps1，PyInstaller onedir／windowed + Inno Setup。只在明確要求時執行，封裝後必跑 EXE --self-test 絕對報告路徑。

## GitHub 與本機同步

- CLI gh 曾使用無寫入權帳號，不擅自切帳號或取憑證。GitHub connector 可使用 create_blob → create_tree → create_commit → update_ref(force=false, expected_sha)。先核對本機與遠端基底，遠端 tree 必須等於已審查的 staged tree。
- 同步後 fetch 並確認內容一致，再對齊本機；保留未知修改，不 force push。工具 JSON 中文輸出可用 ensure_ascii=True。
- 本次整理前 docs/AI_CONTEXT.md 已有未提交交接修改；其原文已保留在 outputs/documentation-backup/AI_CONTEXT_before_2026-11-15.md，不入 Git。
