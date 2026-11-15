# 素材與第三方授權

- 根目錄 LICENSE 保留儲存庫原有 MIT 授權與 Ryan Hsu 署名，不重寫既有授權選擇。
- BitingBox Studio 名稱與 Logo 為專案品牌識別；程式碼 MIT 授權不授予商標權，也不將品牌 Logo 提供為任意再用的素材庫。如需使用 BitingBox Studio 商標、名稱或 Logo，請透過 [RyanXuwei 的 GitHub](https://github.com/RyanXuwei) 聯繫並取得許可。
- 目前頁尾使用 assets/bitingbox-studio-plaque.svg，後台 PNG 由同一稿輸出透明 RGBA；移除米白外底，保留玉綠牌匾與原品牌路徑。assets/bitingbox-studio-horizontal.svg 為保留的早期素材，不代表目前頁尾稿。不使用外部網站載入。
- 背景、山茶花、程式圖示與 30 款分類頭像使用內建圖像生成工具製作；逐張頭像提示詞在 assets/group-icons/prompts.json。素材總覽在 assets/group-icons-preview.jpg。
- 兩張片源說明圖是程式繪製的虛構資料夾示意，沒有使用個人片庫或截圖。
- Pillow、pystray、Send2Trash、pywin32、Python、imageio-ffmpeg、PyInstaller 及 FFmpeg 保留各自授權，文件位於 licenses/。
- 現有 FFmpeg 授權記錄來自獨立的 GPL 組建，不能當成 MIT 元件。打包或再散布二進位時應連同對應的第三方授權及適用來源提供方式處理；本 Git 儲存庫不包含 FFmpeg／Python 二進位或 Windows 安裝檔。

不建立未確認的商標註冊標示、品牌網址、權利人或其他授權宣稱。不要把私人品牌交接 ZIP、完整歷史參考素材或機器絕對路徑加入儲存庫。

- v1.3.1 使用內建 image_gen 對原頭像總覽去背，保持 6×5 順序，移除方塊背景與文字，再切為 30 個含 alpha 的 WebP。透明度不由 RGB 轉換抹除。

- v1.5.2 頁尾使用 assets/bitingbox-studio-plaque.svg（使用者提供的 08_horizontal_plaque.svg 原稿），保留原始配色、向量路徑與比例；既有 PNG 仍供後台使用。

- v1.5.3 依使用者要求移除橫式牌匾的米白底矩形；其餘向量路徑與配色保留。後台 PNG 由同一 SVG 等比例輸出並保留 alpha。
