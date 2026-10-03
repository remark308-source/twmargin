#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_tw.py
台股版「上市/櫃買 融資淨買入 MA20 疊加指數」資料建構

資料源（2026-10 改版）：
  KGI MoneyDJ 盤後資訊（嘉實資訊 b2brwd）
    https://kgiweb.moneydj.com/b2brwd/page/afterhours/market/0002
  頁面背後的資料端點（twstockdata.xdjjson，?c=筆數 可全量回補，revision 參數可省略）：
    上市：/b2brwdCommon/jsondata/32/06/4a/twstockdata.xdjjson?x=afterHours-market0002-1&b=d&c=3000
    上櫃：/b2brwdCommon/jsondata/3a/b1/8d/twstockdata.xdjjson?x=afterHours-market0002-2&b=d&c=3000
  欄位（Result[i]）：
    V1 = 日期 YYYY/MM/DD
    V3 = 融資餘額（萬元）  → 每日淨買入(億) = diff(V3) / 1e4
    V7 = 大盤指數收盤（上市=加權指數、上櫃=櫃買指數）
  c=3000 可回補至 2014 年，足涵蓋 START=2018 起；每次執行即全量重建
  （僅 2 次 HTTP 呼叫，秒級完成），不再需要增量模式與 TPEx 官網逐日爬蟲。

  ※ 改版前舊源（已棄用）：
    - FinMind TaiwanStockPrice（TAIEX/TPEx 指數）→ 上市融資自 2026-08-14 起斷更
    - FinMind TaiwanStockTotalMarginPurchaseShortSale（上市融資）
    - TPEx 官網 margin_bal_result.php（櫃買融資，需逐日請求）
    經逐日比對：KGI 指數與舊 FinMind 指數 2100+ 筆完全一致；
    融資淨買入近期一致，2018~2019 年部分交易日有 ±3 億內口徑差（以 KGI 為準）。

輸出 chart_data_tw.json，欄位：
  dates, twse_idx_raw, tpex_idx_raw,
  twse_netbuy_daily, tpex_netbuy_daily,        # 每日融資淨買入 (TWD 億元)
  twse_balance_raw, tpex_balance_raw,          # 融資餘額 (萬元，KGI V3 原值，供差分除錯)
  twse_netbuy_ma20, tpex_netbuy_ma20,
  twse_ma20_latest, tpex_ma20_latest,
  baseline / n / asof
"""

import json
import math
import sys
import time
import urllib.request
from datetime import datetime

# === 設定 ============================================================
START = "2018-01-01"
TODAY = datetime.now().strftime("%Y-%m-%d")

KGI_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
KGI_SOURCES = {
    "twse": "https://kgiweb.moneydj.com/b2brwdCommon/jsondata/32/06/4a/"
            "twstockdata.xdjjson?x=afterHours-market0002-1&b=d&c=3000",
    "tpex": "https://kgiweb.moneydj.com/b2brwdCommon/jsondata/3a/b1/8d/"
            "twstockdata.xdjjson?x=afterHours-market0002-2&b=d&c=3000",
}

# === 工具 ============================================================
def http_get_json(url, timeout=30, retries=3, sleep=1.5):
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": KGI_UA,
                "Referer": "https://kgiweb.moneydj.com/b2brwd/page/afterhours/market/0002",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            last_err = e
            time.sleep(sleep * (i + 1))
    raise RuntimeError(f"GET {url} failed after {retries} retries: {last_err}")

def norm_date(s: str) -> str:
    """YYYY/MM/DD -> YYYY-MM-DD"""
    y, m, d = s.split("/")
    return f"{y}-{int(m):02d}-{int(d):02d}"

def fetch_kgi(key):
    """取單一市場全量資料，回傳 {date: (融資餘額萬元, 指數收盤)}，舊→新"""
    d = http_get_json(KGI_SOURCES[key])
    rs = d.get("ResultSet", {})
    if rs.get("StatusCode") != 0:
        raise RuntimeError(f"KGI {key} StatusCode={rs.get('StatusCode')} Comment={rs.get('Comment')}")
    out = {}
    for r in rs.get("Result", []):
        try:
            dt = norm_date(r["V1"])
            if dt < START:
                continue
            out[dt] = (float(r["V3"]), float(r["V7"]))
        except (KeyError, ValueError, TypeError):
            continue
    return out

# === 計算工具 =========================================================
def ma20(series):
    out = [None] * len(series)
    vals = [v if v is not None else float("nan") for v in series]
    for i in range(19, len(vals)):
        window = vals[i-19:i+1]
        if any(math.isnan(v) for v in window):
            out[i] = None
        else:
            out[i] = round(sum(window) / 20.0, 2)
    return out

def last_nonnull(arr):
    for v in reversed(arr):
        if v is not None:
            return v
    return None

def to_arr(dates, mapping):
    return [mapping.get(d) for d in dates]

def clean(v):
    return None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 2)

def netbuy_from_balance(dates, bal_map):
    """融資餘額(萬元)差分 → 每日淨買入(億元)，首日為 NaN"""
    out = {}
    for i, dt in enumerate(dates):
        if i == 0:
            out[dt] = float("nan")
        else:
            out[dt] = (bal_map[dt] - bal_map[dates[i-1]]) / 1e4
    return out

# === 組裝 / 輸出 ======================================================
def build():
    print("\n[1/2] KGI 拉上市（加權指數 + 大盤融資餘額）...")
    twse = fetch_kgi("twse")
    twse_dates = sorted(twse)
    print(f"      取回 {len(twse)} 筆  起={twse_dates[0]} 末={twse_dates[-1]}")

    print("\n[2/2] KGI 拉上櫃（櫃買指數 + 大盤融資餘額）...")
    tpex = fetch_kgi("tpex")
    tpex_dates = sorted(tpex)
    print(f"      取回 {len(tpex)} 筆  起={tpex_dates[0]} 末={tpex_dates[-1]}")

    all_dates = sorted(set(twse) | set(tpex))
    print(f"\n合併日曆: {len(all_dates)} 個交易日  起={all_dates[0]} 末={all_dates[-1]}")

    twse_bal = {d: v[0] for d, v in twse.items()}
    tpex_bal = {d: v[0] for d, v in tpex.items()}
    twse_nb = netbuy_from_balance(all_dates, {d: twse_bal[d] for d in all_dates if d in twse_bal})
    tpex_nb = netbuy_from_balance(all_dates, {d: tpex_bal[d] for d in all_dates if d in tpex_bal})

    twse_nb_arr = to_arr(all_dates, twse_nb)
    tpex_nb_arr = to_arr(all_dates, tpex_nb)
    twse_ma = ma20(twse_nb_arr)
    tpex_ma = ma20(tpex_nb_arr)

    out = {
        "dates": all_dates,
        "twse_idx_raw": to_arr(all_dates, {d: v[1] for d, v in twse.items()}),
        "tpex_idx_raw": to_arr(all_dates, {d: v[1] for d, v in tpex.items()}),
        "twse_netbuy_daily": [clean(v) for v in twse_nb_arr],
        "tpex_netbuy_daily": [clean(v) for v in tpex_nb_arr],
        "twse_balance_raw": to_arr(all_dates, twse_bal),
        "tpex_balance_raw": to_arr(all_dates, tpex_bal),
        "twse_netbuy_ma20": twse_ma,
        "tpex_netbuy_ma20": tpex_ma,
        "twse_ma20_latest": last_nonnull(twse_ma),
        "tpex_ma20_latest": last_nonnull(tpex_ma),
        "baseline": f"{all_dates[0]} ~ {all_dates[-1]}",
        "n": len(all_dates),
        "asof": TODAY,
        "source": "KGI MoneyDJ 盤後資訊 (kgiweb.moneydj.com/b2brwd/page/afterhours/market/0002)",
    }

    with open("chart_data_tw.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n✓ 已輸出 chart_data_tw.json")
    print(f"  上市 MA20 末值 = {out['twse_ma20_latest']} 億 TWD")
    print(f"  櫃買 MA20 末值 = {out['tpex_ma20_latest']} 億 TWD")
    print(f"  上市 末日淨買入 = {out['twse_netbuy_daily'][-1]} 億")
    print(f"  櫃買 末日淨買入 = {out['tpex_netbuy_daily'][-1]} 億")
    return out

# === 主要 ============================================================
def main():
    print("=" * 60)
    print("台股融資淨買入 MA20 × 上市/櫃買加權 疊加圖 資料建構")
    print(f"區間 {START} ~ {TODAY} ｜ 源：KGI MoneyDJ 盤後資訊")
    print("=" * 60)
    if "--full" in sys.argv:
        print("[提示] KGI 源每次皆為全量重建，--full 僅為相容保留")
    build()

if __name__ == "__main__":
    main()
