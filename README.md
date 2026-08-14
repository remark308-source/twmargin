# twmargin — 台股融資淨買入 MA20 疊加圖

台股「上市加權指數 (TAIEX)」與「櫃買指數 (TPEx)」**融資淨買入 20 日移動平均 (MA20)** 疊加走勢圖。
報告為**自包含單一 HTML**（echarts 已 base64 內聯），可離線直接打開，亦可部署到 GitHub Pages。

## 線上版

https://remark308-source.github.io/twmargin/

> 線上為靜態快照；最新資料請見下方「本地更新」章節，重新產生後推送即可。

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

## 本地更新（開發者）

僅需 Python 3.13 + 網路，標準庫即可（urllib / ssl / concurrent.futures），無第三方套件相依。

```bash
# Windows 一鍵（雙擊 refresh_tw.bat）：
python build_tw.py && python gen_html_tw.py
```

`build_tw.py` 重新抓取並產生 `chart_data_tw.json`；`gen_html_tw.py` 產生 `index.html`。

推送後 GitHub Pages 即更新：

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
