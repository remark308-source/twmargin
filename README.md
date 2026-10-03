# twmargin

台股「上市/櫃買 融資淨買入 MA20 疊加指數」報告產生器。

## 資料源

[KGI MoneyDJ 盤後資訊](https://kgiweb.moneydj.com/b2brwd/page/afterhours/market/0002)（嘉實資訊 b2brwd），
頁面背後的資料端點為 `twstockdata.xdjjson`（`?c=` 可指定回傳筆數，3000 筆可回補至 2014 年）：

- 上市：`/b2brwdCommon/jsondata/32/06/4a/twstockdata.xdjjson?x=afterHours-market0002-1&b=d&c=3000`
- 上櫃：`/b2brwdCommon/jsondata/3a/b1/8d/twstockdata.xdjjson?x=afterHours-market0002-2&b=d&c=3000`

欄位：`V1` 日期、`V3` 融資餘額（萬元）、`V7` 大盤指數收盤（上市=加權、上櫃=櫃買）。
每日融資淨買入（億元）＝ 融資餘額差分 ÷ 1e4。

> 2026-10 前：指數與上市融資走 FinMind、櫃買融資走 TPEx 官網逐日爬蟲。
> FinMind 上市融資自 2026-08-14 起斷更，故全面改用 KGI 單一源。
> 指數部分兩源經 2100+ 交易日逐日比對完全一致。

## 用法

```
python -X utf8 build_tw.py      # 重建 chart_data_tw.json（每次皆全量，2 次 HTTP 呼叫）
python -X utf8 gen_html_tw.py   # 產生自包含 HTML 報告（echarts 內聯）
```

或直接執行 `refresh_tw.bat`。盤後資訊約 17:00 後更新當日資料。
