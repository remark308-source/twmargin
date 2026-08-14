# twmargin — 台股融資淨買入 MA20 疊加圖

台股「上市加權指數 (TAIEX)」與「櫃買指數 (TPEx)」**融資淨買入 20 日移動平均 (MA20)** 疊加走勢圖。
報告為**自包含單一 HTML**（echarts 已 base64 內聯），可離線直接打開，亦可部署到 GitHub Pages。

## 線上版

https://remark308-source.github.io/twmargin/

> 線上版由 **GitHub Actions 每日台北收盤後自動更新**（週一至週五 UTC 10:30 ≈ 台北 18:30），無須手動推送。想立即刷新可按 Actions 頁面 **Run workflow** 手動觸發。

## 讀圖方法

- **上圖**：上市加權 / 櫃買指數以 2018-01-02 為基準歸一化 (=100) 疊加；
  橙線 = 上市融資淨買入 MA20、桃紅線 = 櫃買融資淨買入 MA20（右軸，億元 TWD）。上市 MA20 附 0 參考線。
- **下圖**：兩市每日融資淨買入柱狀（紅 = 淨買入/加槓桿，綠 = 淨償還/去槓桿）+ 各自 MA20 折線。

## 資料來源

| 項目 | 來源 | 欄位 / 路徑 |
| --- | --- | --- |
| 上市加權指數 | FinMind `TaiwanStockPrice` | data_id = `TAIEX`，欄位 `close` |
| 櫃買指數 | FinMind `TaiwanStockPrice` | data_id = `TPEx`（小寫 x），欄位 `close` |
| 上市融資淨買入 | FinMind `TaiwanStockTotalMarginPurchaseShortSale` | name = `MarginPurchaseMoney`，`(TodayBalance − YesBalance)` 差分（單位：元 → 億元） |
| 櫃買融資淨買入 | TPEx 官網 `margin_bal_result.php` | `tables[0].summary[1][6]` 仟元餘額差分（單位：仟元 → 億元） |

融資淨買入 (日) = 當日融資餘額 − 前日融資餘額。

## 自動更新（GitHub Actions）

倉庫已內建 `.github/workflows/update.yml`：

- **排程**：台北交易日收盤後（週一至週五 UTC 10:30 ≈ 台北 18:30）自動跑。
- **流程**：`python build_tw.py`（增量只抓新交易日）→ `python gen_html_tw.py`（輸出 `index.html`）→ 自動 commit & push。
- **手動**：在 Actions 頁面點 **Run workflow** 可立即觸發。
- 首次執行會偵測到舊 `chart_data_tw.json` 缺 `tpex_balance_raw`，自動做一次**全量重建**建立增量基礎，之後皆為輕量增量。

### 關於「櫃買」資料來源（重要）

櫃買融資餘額**只能**來自 TPEx 官網（FinMind 的 OTC 欄位會被忽略、回傳的是 TSE+OTC 合併值）。
TPEx 官網對**雲端 IP（如 GitHub 託管 runner）可能會封鎖**，導致雲端自動更新時櫃買序列停在舊值。
若發現線上「櫃買 MA20」不再跟著更新，請改用**自託管 runner**（跑在你家網路，TPEx 必達）：

```bash
# 1) 下載並設定 runner（一次）：Actions → Runners → New runner，照頁面指令執行
# 2) 把 update.yml 的 runs-on 改為：
#       runs-on: self-hosted
# 3) 啟動 runner（保持開著，排程會自動喚醒它）
./run.sh
```

## 本地更新（開發者）

僅需 Python 3.13 + 網路，標準庫即可（urllib / ssl / concurrent.futures），無第三方套件相依。

```bash
# Windows 一鍵（雙擊 refresh_tw.bat）：
python build_tw.py && python gen_html_tw.py
```

`build_tw.py` 預設**增量**模式（抓新交易日追加）；加 `--full` 可強制全量重建。
`gen_html_tw.py` 預設輸出帶日期檔名；設 `OUTPUT_HTML=index.html` 可覆寫為 Pages 用的 `index.html`。

本地產出後推送，GitHub Pages 即更新：

```bash
git add -A
git commit -m "update data"
git push
```

## 檔案說明

| 檔案 | 說明 |
| --- | --- |
| `index.html` | 自包含報告（GitHub Pages 入口，echarts base64 內聯） |
| `build_tw.py` | 資料抓取與計算 |
| `gen_html_tw.py` | 報告生成（讀 `chart_data_tw.json` + `echarts.min.js`） |
| `chart_data_tw.json` | 中間資料 |
| `echarts.min.js` | 本地重建報告用 |
| `refresh_tw.bat` | Windows 一鍵更新 |
| `.nojekyll` | 停用 Jekyll 處理，避免 HTML 被改寫 |

## 備註

- 本圖**不含 P20/P95 分位標記**（與 A 股版不同），僅保留 MA20 與 0 參考線。
- 台股融資規模遠小於 A 股，MA20 量級約 ±30 億 TWD（上市）/ ±5 億 TWD（櫃買），門檻不可與 A 股通用。
