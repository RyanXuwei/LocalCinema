# LocalCinema 精簡交接

更新日期：2026-11-14。新串先讀本檔與根目錄 AGENTS.md，按需閱讀 ARCHITECTURE、DATA_MODEL、SECURITY、DEVELOPMENT，不必重讀長聊天。

## 目前可確認狀態

- 版本 1.5.1（version.py）；main 已同步 RyanXuwei/LocalCinema，程式提交 b48096d0db45d0c1ce5fdc3e5a0c98c0e61bed16。
- 專案根目錄是唯一主要原始碼。outputs/LocalCinema 是供使用者使用的副本，每次改版後同步；outputs 不入 Git。
- 最新安裝包 outputs/LocalCinema_Setup_v1.5.1_x64.exe，SHA256 在 outputs/LocalCinema_Setup_SHA256.txt。只保留最新版，過期生成檔移回收筒。
- README 含完整操作說明；docs/images/localcinema-prototype.png 是使用者選定的圖 3 參考，實際虛構片單截圖另標明。

## 最新待辦：工作室 Logo

使用者問「去背黑色 icon 會否比較合適」，所指為頁尾 BitingBox Studio 整合名稱 Logo。上一則僅建議：透明底、米白色圖案與文字，去除圖示實心底塊，以適應深綠背景。尚未實作，也未取得使用者對最終配色的選擇。不要宣稱已完成，不要自行改成黑色。新串先簡短說明交接已完成並等待下一步；若使用者確認此建議再處理。保留原品牌路徑與比例。

## 不能越過的邊界

- 絕不讀取、掃描、列出或引用真實片庫、媒體名稱、路徑、設定、資料庫、連結與入口碼。測試只用虛構檔案及隔離資料。
- import cinema 之前設定 LOCALAPPDATA 為臨時測試目錄；匯入即建立 DATA。
- 個人資料固定在 %LOCALAPPDATA%/LocalCinema，安裝更新不覆蓋。掃描一層邊界、平鋪優先、群組獨立標籤、轉檔別名等不變量見 AGENTS/DATA_MODEL。
- 完成改版後自動同步 GitHub；禁止 force push 或提交個人資料。安裝包僅本機輸出，不進 Git。
- 電腦控制完成立即 completion_summary 並關閉自建測試頁。使用者討厭控制框殘留。

## 近期設計與互動

- 深綠／米白、細線鏤空 icon；首頁側欄、圖片內標題／標籤、三欄卡片、方格／列表切換。
- 頂部片源按鈕維持大方形 App icon：桌面 52px／窄版 46px。不要改回小圓頭像。內建 30 款頭像已去背，WebP 保留 alpha；後台與自訂圖用 RGBA。
- 標籤／進階篩選互斥；點外側空白處或 Esc 收起，內部操作保持展開。
- 播放器同一視覺系統；手機兩列工具列；Hide 加首頁同款圖示。保持全螢幕與滿視窗回退。
- 1.5.0 關鍵幀：按書籤立即新增目前時間的黃色旗標；keyframeRail 位於 seekRow。點旗標跳轉但不改播放／暫停狀態；paused 且 !seeking 且時間差 <=0.15 秒時點擊刪除。不再有輸入名稱／時間面板。舊資料保留，無 DB 遷移。防重複及連點寫入。
- Short 保留按住畫面水平拖曳時間、底部時間軸／換片間隔、側邊收藏標籤放大。追加及裁剪卡片須按真實 anchor 幾何補償，不可盲目扣 scrollTop。
- 服務啟動預設綁定 0.0.0.0，列出區網網址；每個網址獨立 QR 卡片，在本機用 qrcode 生成，內含存取碼。啟動不自動開瀏覽器。

## 元件與驗證

- cinema.py：後台／HTTP／SQLite／掃描轉檔；source_groups.py：群組頭像與標籤；group_access.py：隱藏頻道授權；conversion_store.py：轉檔確認／回收／別名。
- index.html：主要播放器及內嵌互動。assets/studio-layout.css：增量樣式；studio-navigation.js：版面與共用導航。不要重寫整個 HTML。
- python -m unittest discover -s tests -v：6 個合成測試。
- node tests/short_scroll.cjs：120 次追加裁剪模型。前端變更另做 JS syntax／HTML ID 檢查。
- 近期瀏覽器已驗證桌面／390px 手機、篩選外點關閉、旗標增刪與集數隔離。未驗證使用者真實片庫、實體手機與多裝置長時間播放。
- packaging/build_windows.ps1 使用 PyInstaller + Inno，內建 frozen self-test 以隔離 DB／資源／依賴／FFmpeg 驗證。qrcode 在 requirements 和 launcher preflight 中；licenses 保留授權。
- 暫時建置 Inno 6.7.4 從官方 jrsoftware/issrc releases 取得，驗證 Authenticode Valid，裝到 work/inno；建置完成卸載並回收 work/build/dist。安裝包輸出到 outputs。

## GitHub 同步注意

CLI gh 曾登入無寫入權的 Ryan-zoustec，勿擅自切帳號／取憑證。GitHub connector 對 RyanXuwei/LocalCinema 有寫入權。可用 create_blob → create_tree(base tree) → create_commit(parent head) → update_ref(expected_sha, force=false)，再 git fetch/reset --mixed origin/main 對齊。必須先核對本機 staged tree 與遠端 tree；保留未知修改。
Python 對工具輸出的 JSON 使用 ensure_ascii=True，避免 Windows cp950 破壞中文路徑。base64 大圖按需要分塊，勿直接印給使用者。新串依工具實際 schema 操作。
