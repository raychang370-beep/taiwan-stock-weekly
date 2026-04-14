📊 台股技術分析週報系統

⚙️ 股市每週自動流程
每週一 08:00
  → 自動抓取股票資料 + 財經新聞
  → 計算 KD / 辨識型態
  → 產生 HTML 週報（含密碼保護）
  → git push → GitHub Pages 自動更新

🖥️ 手動執行
cd C:/Users/user/taiwan-stock-weekly
uv run deploy.py   # 產生報告 + 自動推送
分類	股票
📈 買入	台勝科、南亞科
⏳ 等待	台積電、旺宏、兆赫


🗂 系統架構
C:/Users/user/taiwan-stock-weekly/
├── config.json          ← 自訂公司清單、產業、KD參數
├── stock_analyzer.py    ← 抓股價、計算KD、辨識型態
├── news_fetcher.py      ← 抓取財經新聞（Google News RSS）
├── report_generator.py  ← 產生漂亮HTML週報
├── main.py              ← 主程式
└── output/index.html    ← 每週自動更新的週報網頁

⏰ 自動排程
每週一早上 8:00 自動執行，產生週報並開啟瀏覽器

🔧 自訂設定
編輯 config.json 可以：

新增/移除公司：加入代號（格式：2330.TW）
更換產業分類
調整 KD 參數（預設 K=9, D=3）
📐 型態分類依據（對應您的圖片）
分類	條件
🚀 必買	KD黃金交叉＋超賣區（K<20）+ 底部型態（W底/頭肩底）
📈 買入	底部型態或上升趨勢
⏳ 等待	三角收斂/箱型盤整/上升通道
📉 賣出	頭部型態或下跌趨勢
💣 必賣	KD死亡交叉＋超買區（K>80）+ 頭部型態（M頭/三重頂）


1. 📊 日線圖（K棒圖）
每支股票現在有兩層圖表：

圖表	說明
日線圖（上方）	K棒（台灣慣例：🔴紅漲 🟢綠跌），滑鼠/手指點選可看 開/高/低/收
KD 線（下方）	K線（橙）＋ D線（藍），0–100 區間
2. 📱 手機支援確認
完全可以在手機使用！

步驟：

手機瀏覽器輸入：
https://raychang370-beep.github.io/taiwan-stock-weekly/
輸入密碼：
即可查看完整週報
手機版特別優化：

卡片改為單欄顯示（不擠）
輸入框自動全寬
圖表高度自動縮小適配螢幕
密碼輸入框支援手機鍵盤
GitHub Pages 部署約需 1~2 分鐘，稍後刷新網頁即可看到日線圖版本。
