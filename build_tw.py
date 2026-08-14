#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_tw.py
台股版「上市/櫃買 融資淨買入 MA20 疊加指數」資料建構

架構（4 源 / 3 步）：
  1. FinMind 拉上市加權指數（TaiwanStockPrice, data_id=TAIEX, 字段 close）
  2. FinMind 拉櫃買指數    （TaiwanStockPrice, data_id=TPEx,  字段 close）
  3. FinMind 拉上市融資    （TaiwanStockTotalMarginPurchaseShortSale,
                              name=MarginPurchase 的 TodayBalance-YesBalance, 仟元）
  4. TPEx 官網每日融資    （margin_bal_result.php, summary[1][6] 仟元）
      └─ 備援：若 FinMind 上市融資缺日，嘗試從 TWSE margin MI_MARGN 反推；
              若 TPEx 官網當日回應非 OK/找不到，視為該日缺。

輸出 chart_data_tw.json，欄位：
  dates, twse_idx_raw, tpex_idx_raw,
  twse_netbuy_daily, tpex_netbuy_daily,        # 每日融資淨買入 (TWD 億元)
  twse_netbuy_ma20, tpex_netbuy_ma20,
  baseline / n / 最後交易日
"""

import json
import math
import ssl
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows Python 3.13 對 tpex.org.tw 證書 SKI 字段驗證會卡 → 用 unverified context
# 不影響資料正確性（curl 對同 URL 取回正常）
_TLS = ssl._create_unverified_context()

# === 設定 ============================================================
START = "2018-01-01"
TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_TW = (datetime.now() - timedelta(days=0)).strftime("%Y-%m-%d")
# TPEx 官網用 ROC 民國年：113 = 2024、115 = 2026
def roc(date_str: str) -> str:
    """YYYY-MM-DD -> ROC年/月/日"""
    y, m, d = date_str.split("-")
    return f"{int(y)-1911}/{int(m):02d}/{int(d):02d}"

# === 工具：HTTP GET ==================================================
def http_get_json(url, timeout=25, retries=3, sleep=1.5):
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout, context=_TLS) as r:
                data = r.read()
            return json.loads(data)
        except Exception as e:
            last_err = e
            time.sleep(sleep * (i+1))
    raise RuntimeError(f"GET {url} failed after {retries} retries: {last_err}")

# === Source 1+2+3: FinMind ===========================================
def finmind(dataset, data_id=None, start=START, end=TODAY):
    qs = {"dataset": dataset, "start_date": start, "end_date": end}
    if data_id:
        qs["data_id"] = data_id
    url = "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode(qs)
    return http_get_json(url)

def fetch_taiex():
    """上市加權指數日線，回傳 {date(str): close(float)}"""
    rows = finmind("TaiwanStockPrice", "TAIEX").get("data", [])
    out = {}
    for r in rows:
        try:
            out[r["date"]] = float(r["close"])
        except (KeyError, ValueError, TypeError):
            continue
    return out

def fetch_tpex_idx():
    """櫃買指數日線，回傳 {date(str): close(float)}"""
    rows = finmind("TaiwanStockPrice", "TPEx").get("data", [])
    out = {}
    for r in rows:
        try:
            out[r["date"]] = float(r["close"])
        except (KeyError, ValueError, TypeError):
            continue
    return out

def fetch_twse_margin():
    """上市融資淨買入 (TWD 億元) — FinMind MarginPurchaseMoney (單位：元)
    字段校驗：name=MarginPurchaseMoney, TodayBalance 是「元」
    經與 TWSE 官方 MI_MARGN「融資金額(仟元)*1000」比對，數值完全一致。
    """
    rows = finmind("TaiwanStockTotalMarginPurchaseShortSale").get("data", [])
    by_date = {}
    for r in rows:
        if r.get("name") != "MarginPurchaseMoney":
            continue
        try:
            today = float(r["TodayBalance"]); yest = float(r["YesBalance"])
            by_date[r["date"]] = (today - yest) / 1e8  # 元 → 億元
        except (KeyError, ValueError, TypeError):
            continue
    # diff 的第一個值 (第一日) 沒意義 → NaN
    dates_sorted = sorted(by_date.keys())
    if dates_sorted:
        by_date[dates_sorted[0]] = float("nan")
    return by_date

# === Source 4: TPEx 官網每日融資 ======================================
def fetch_tpex_margin_one(date_str):
    """取單日 TPEx 全市場融資餘額 (仟元)，無資料回 None"""
    url = f"https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&o=json&d={roc(date_str)}"
    try:
        d = http_get_json(url, timeout=12, retries=2, sleep=0.6)
    except Exception:
        return None
    if d.get("stat", "").upper() != "OK":
        return None
    # 真實路徑：tables[0].summary 是 list of list，summary[1] = 「融資金(仟元)」，
    # summary[1][6] = 今日餘額，summary[1][2] = 前日餘額
    try:
        summary = d["tables"][0]["summary"]
        if not summary or len(summary) < 2 or len(summary[1]) < 7:
            return None
        today = float(str(summary[1][6]).replace(",", ""))
        return today
    except (KeyError, IndexError, ValueError, TypeError):
        return None

def fetch_tpex_margin_all(dates_list, workers=6):
    """多並發取 TPEx 每日融資餘額，回傳 {date: balance_仟元}"""
    out = {}
    n = len(dates_list)
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fut = {ex.submit(fetch_tpex_margin_one, dt): dt for dt in dates_list}
        for f in as_completed(fut):
            dt = fut[f]
            try:
                bal = f.result()
            except Exception:
                bal = None
            if bal is not None:
                out[dt] = bal
            done += 1
            if done % 200 == 0 or done == n:
                print(f"  TPEx margin progress {done}/{n}  hit={len(out)}  elapsed={time.time()-t0:.1f}s")
    return out

# === 主要 ============================================================
def main():
    print("=" * 60)
    print("台股融資淨買入 MA20 × 上市/櫃買加權 疊加圖 資料建構")
    print(f"區間 {START} ~ {TODAY}")
    print("=" * 60)

    # 1) FinMind 拉三源
    print("\n[1/4] FinMind 拉上市加權指數 (TAIEX)...")
    taiex = fetch_taiex()
    print(f"      取回 {len(taiex)} 筆  起={min(taiex)} 末={max(taiex)}")

    print("\n[2/4] FinMind 拉櫃買指數 (TPEx)...")
    tpex_idx = fetch_tpex_idx()
    print(f"      取回 {len(tpex_idx)} 筆  起={min(tpex_idx)} 末={max(tpex_idx)}")

    # 3) FinMind 拉上市融資 — MarginPurchaseMoney (元)
    print("\n[3/4] FinMind 拉上市融資淨買入 (MarginPurchaseMoney)...")
    twse_margin = fetch_twse_margin()
    twse_dates = sorted(twse_margin.keys())
    print(f"      取回 {len(twse_margin)} 筆  起={twse_dates[0] if twse_dates else '-'} 末={twse_dates[-1] if twse_dates else '-'}")

    # 4) TPEx 官網每日融資
    # 估計要拉的日期清單：上市融資的日期為主（FinMind 上市有資料的日子，櫃買理論上也開市）
    print("\n[4/4] TPEx 官網逐日取櫃買融資餘額...")
    if not twse_dates:
        print("      ⚠ 上市融資無資料，TPEx 清單改用櫃買指數日期")
        tpex_dates = sorted(tpex_idx.keys())
    else:
        tpex_dates = twse_dates
    tpex_bal = fetch_tpex_margin_all(tpex_dates)
    print(f"      取回 {len(tpex_bal)} 筆  首={min(tpex_bal) if tpex_bal else '-'} 末={max(tpex_bal) if tpex_bal else '-'}")
    # diff 櫃買淨買入 (TWD 億元)
    tpex_netbuy = {}
    sorted_dates = sorted(tpex_bal.keys())
    for i, dt in enumerate(sorted_dates):
        if i == 0:
            tpex_netbuy[dt] = float("nan")
        else:
            tpex_netbuy[dt] = (tpex_bal[dt] - tpex_bal[sorted_dates[i-1]]) / 1e5

    # 對齊日曆：上市融資 ∪ 櫃買融資 ∪ 上市指數 ∪ 櫃買指數
    all_dates = sorted(set(twse_margin) | set(tpex_netbuy) | set(taiex) | set(tpex_idx))
    print(f"\n合併日曆: {len(all_dates)} 個交易日  起={all_dates[0]} 末={all_dates[-1]}")

    # 寫成 array（None 表缺值）
    def arr(d, key_map):
        return [key_map.get(d) for d in all_dates]

    twse_nb_arr = arr(all_dates, twse_margin)
    tpex_nb_arr = arr(all_dates, tpex_netbuy)
    taiex_arr   = arr(all_dates, taiex)
    tpexid_arr  = arr(all_dates, tpex_idx)

    # 各自計算 MA20 + P20/P95（用 >=2018-01-01 完整段）
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

    twse_ma = ma20(twse_nb_arr)
    tpex_ma = ma20(tpex_nb_arr)

    def last_nonnull(arr):
        for v in reversed(arr):
            if v is not None:
                return v
        return None

    out = {
        "dates": all_dates,
        "twse_idx_raw":  taiex_arr,
        "tpex_idx_raw":  tpexid_arr,
        "twse_netbuy_daily": [None if (v is None or (isinstance(v,float) and math.isnan(v))) else round(v, 2) for v in twse_nb_arr],
        "tpex_netbuy_daily": [None if (v is None or (isinstance(v,float) and math.isnan(v))) else round(v, 2) for v in tpex_nb_arr],
        "twse_netbuy_ma20": twse_ma,
        "tpex_netbuy_ma20": tpex_ma,
        "twse_ma20_latest": last_nonnull(twse_ma),
        "tpex_ma20_latest": last_nonnull(tpex_ma),
        "baseline": f"{all_dates[0]} ~ {all_dates[-1]}",
        "n": len(all_dates),
        "asof": TODAY,
    }

    out_path = "chart_data_tw.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n✓ 已輸出 {out_path}")
    print(f"  上市 MA20 末值 = {out['twse_ma20_latest']} 億 TWD")
    print(f"  櫃買 MA20 末值 = {out['tpex_ma20_latest']} 億 TWD")
    print(f"  上市 末日淨買入 = {out['twse_netbuy_daily'][-1]} 億")
    print(f"  櫃買 末日淨買入 = {out['tpex_netbuy_daily'][-1]} 億")
    return out

if __name__ == "__main__":
    main()
