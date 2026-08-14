#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_tw.py
台股版「上市/櫃買 融資淨買入 MA20 疊加指數」資料建構

資料源（3 類 / 4 次呼叫）：
  1. FinMind 上市加權指數  (TaiwanStockPrice, data_id=TAIEX,  close)
  2. FinMind 櫃買指數       (TaiwanStockPrice, data_id=TPEx,   close)   ← 注意小寫 x
  3. FinMind 上市融資       (TaiwanStockTotalMarginPurchaseShortSale,
                             name=MarginPurchaseMoney, TodayBalance-YesBalance, 單位=元)
  4. TPEx 官網每日融資      (margin_bal_result.php, summary[1][6] 仟元)  ← 櫃買唯一可靠源
     ※ FinMind 的 data_id=OTC 在本 dataset 會被忽略（TSE/OTC 回傳相同合併值），
       故「櫃買單獨」序列只能走 TPEx 官網。

運作模式：
  - 預設：若 chart_data_tw.json 已存在 → 增量模式（只抓 last_date 之後的新交易日，追加）。
  - --full：強制全量重建（2018 起重抓，首次或校正用）。
  - GitHub Actions 也走增量：checkout 出已提交的 json → 追加新日 → 提交回去。

輸出 chart_data_tw.json，欄位：
  dates, twse_idx_raw, tpex_idx_raw,
  twse_netbuy_daily, tpex_netbuy_daily,        # 每日融資淨買入 (TWD 億元)
  tpex_balance_raw,                            # 櫃買融資餘額 (仟元，供增量差分)
  twse_netbuy_ma20, tpex_netbuy_ma20,
  twse_ma20_latest, tpex_ma20_latest,
  baseline / n / asof
"""

import json
import math
import ssl
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Windows Python 對 tpex.org.tw 證書 SKI 欄位驗證會卡 → 用 unverified context
# 不影響資料正確性（curl 對同 URL 取回正常）
_TLS = ssl._create_unverified_context()

# === 設定 ============================================================
START = "2018-01-01"
TODAY = datetime.now().strftime("%Y-%m-%d")
# TPEx 官網用 ROC 民國年：113 = 2024、114 = 2025、115 = 2026
def roc(date_str: str) -> str:
    """YYYY-MM-DD -> ROC年/月/日"""
    y, m, d = date_str.split("-")
    return f"{int(y)-1911}/{int(m):02d}/{int(d):02d}"

def _next_day(s: str) -> str:
    return (datetime.strptime(s, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

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
            time.sleep(sleep * (i + 1))
    raise RuntimeError(f"GET {url} failed after {retries} retries: {last_err}")

# === Source 1+2+3: FinMind ===========================================
def finmind(dataset, data_id=None, start=START, end=TODAY):
    qs = {"dataset": dataset, "start_date": start, "end_date": end}
    if data_id:
        qs["data_id"] = data_id
    url = "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode(qs)
    return http_get_json(url)

def fetch_taiex(start=START, end=TODAY):
    """上市加權指數日線，回傳 {date: close}"""
    rows = finmind("TaiwanStockPrice", "TAIEX", start, end).get("data", [])
    out = {}
    for r in rows:
        try:
            out[r["date"]] = float(r["close"])
        except (KeyError, ValueError, TypeError):
            continue
    return out

def fetch_tpex_idx(start=START, end=TODAY):
    """櫃買指數日線，回傳 {date: close}"""
    rows = finmind("TaiwanStockPrice", "TPEx", start, end).get("data", [])
    out = {}
    for r in rows:
        try:
            out[r["date"]] = float(r["close"])
        except (KeyError, ValueError, TypeError):
            continue
    return out

def fetch_twse_margin(start=START, end=TODAY):
    """上市融資淨買入 (TWD 億元) — FinMind MarginPurchaseMoney (單位：元)
    經與 TWSE 官方 MI_MARGN「融資金額(仟元)*1000」比對，數值完全一致。"""
    rows = finmind("TaiwanStockTotalMarginPurchaseShortSale", None, start, end).get("data", [])
    by_date = {}
    for r in rows:
        if r.get("name") != "MarginPurchaseMoney":
            continue
        try:
            today = float(r["TodayBalance"]); yest = float(r["YesBalance"])
            by_date[r["date"]] = (today - yest) / 1e8  # 元 → 億元
        except (KeyError, ValueError, TypeError):
            continue
    dates_sorted = sorted(by_date.keys())
    if dates_sorted:
        by_date[dates_sorted[0]] = float("nan")  # 首日 diff 無意義
    return by_date

# === Source 4: TPEx 官網每日融資 ======================================
def fetch_tpex_margin_one(date_str):
    """取單日 TPEx 全市場融資餘額 (仟元)，無資料回 None"""
    url = ("https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/"
           f"margin_bal_result.php?l=zh-tw&o=json&d={roc(date_str)}")
    try:
        d = http_get_json(url, timeout=12, retries=2, sleep=0.6)
    except Exception:
        return None
    if d.get("stat", "").upper() != "OK":
        return None
    try:
        summary = d["tables"][0]["summary"]
        if not summary or len(summary) < 2 or len(summary[1]) < 7:
            return None
        return float(str(summary[1][6]).replace(",", ""))
    except (KeyError, IndexError, ValueError, TypeError):
        return None

def fetch_tpex_margin_all(dates_list, workers=6):
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

# === 全量模式 =========================================================
def build_full():
    print("\n[模式] 全量重建 (START=%s)" % START)
    print("\n[1/4] FinMind 拉上市加權指數 (TAIEX)...")
    taiex = fetch_taiex()
    print(f"      取回 {len(taiex)} 筆  起={min(taiex)} 末={max(taiex)}")

    print("\n[2/4] FinMind 拉櫃買指數 (TPEx)...")
    tpex_idx = fetch_tpex_idx()
    print(f"      取回 {len(tpex_idx)} 筆  起={min(tpex_idx)} 末={max(tpex_idx)}")

    print("\n[3/4] FinMind 拉上市融資淨買入 (MarginPurchaseMoney)...")
    twse_margin = fetch_twse_margin()
    twse_dates = sorted(twse_margin.keys())
    print(f"      取回 {len(twse_margin)} 筆  起={twse_dates[0] if twse_dates else '-'} 末={twse_dates[-1] if twse_dates else '-'}")

    print("\n[4/4] TPEx 官網逐日取櫃買融資餘額...")
    tpex_dates = twse_dates if twse_dates else sorted(tpex_idx.keys())
    tpex_bal = fetch_tpex_margin_all(tpex_dates)
    print(f"      取回 {len(tpex_bal)} 筆  首={min(tpex_bal) if tpex_bal else '-'} 末={max(tpex_bal) if tpex_bal else '-'}")

    return _assemble(taiex, tpex_idx, twse_margin, tpex_bal)

# === 增量模式 =========================================================
def build_incremental(old):
    old_dates = old["dates"]
    old_last = old_dates[-1]
    new_start = _next_day(old_last)
    print(f"\n[模式] 增量追加 (last={old_last} → 新區間 {new_start} ~ {TODAY})")

    print("\n[1/3] FinMind 拉新段 (指數 + 上市融資)...")
    taiex_new = fetch_taiex(new_start, TODAY)
    tpex_idx_new = fetch_tpex_idx(new_start, TODAY)
    twse_new = fetch_twse_margin(new_start, TODAY)
    twse_new_dates = sorted(twse_new.keys())
    print(f"      上市融資新筆數 = {len(twse_new_dates)}  末={twse_new_dates[-1] if twse_new_dates else '-'}")

    print("\n[2/3] TPEx 拉新段櫃買融資餘額...")
    # 需要抓的日期：> old_last 且在上市融資新日期內；再加 old_last 本身做差分邊界
    need = [d for d in twse_new_dates if d > old_last]
    if old_last not in need:
        need.append(old_last)
    need = sorted(set(need))
    tpex_bal_new = fetch_tpex_margin_all(need)
    print(f"      新段 TPEx 取回 {len(tpex_bal_new)} 筆")

    print("\n[3/3] 合併舊檔 + 新段...")
    # 舊櫃買原始餘額對照
    old_bal = {}
    old_raw = old.get("tpex_balance_raw", [])
    for d, b in zip(old_dates, old_raw):
        if b is not None:
            old_bal[d] = b
    # 合併餘額 map（新段優先）；_assemble 會由餘額重新差分出每日淨買入
    bal_map = dict(old_bal)
    bal_map.update(tpex_bal_new)

    # 合併到舊資料
    taiex = dict(zip(old_dates, old["twse_idx_raw"])); taiex.update(taiex_new)
    tpex_idx = dict(zip(old_dates, old["tpex_idx_raw"])); tpex_idx.update(tpex_idx_new)
    twse_margin = dict(zip(old_dates, old["twse_netbuy_daily"]))
    twse_margin.update({d: v for d, v in twse_new.items()})
    tpex_bal_full = dict(old_bal); tpex_bal_full.update(tpex_bal_new)

    return _assemble(taiex, tpex_idx, twse_margin, tpex_bal_full)

# === 組裝 / 輸出 ======================================================
def _assemble(taiex, tpex_idx, twse_margin, tpex_bal):
    all_dates = sorted(set(twse_margin) | set(tpex_bal) | set(taiex) | set(tpex_idx))
    print(f"\n合併日曆: {len(all_dates)} 個交易日  起={all_dates[0]} 末={all_dates[-1]}")

    twse_nb_arr = to_arr(all_dates, twse_margin)
    # 由 tpex_bal（原始餘額 map）重新差分出每日淨買入
    tpex_netbuy = {}
    sdates = sorted(tpex_bal.keys())
    for i, dt in enumerate(sdates):
        if i == 0:
            tpex_netbuy[dt] = float("nan")
        else:
            tpex_netbuy[dt] = (tpex_bal[dt] - tpex_bal[sdates[i-1]]) / 1e5
    tpex_nb_arr = to_arr(all_dates, tpex_netbuy)

    taiex_arr = to_arr(all_dates, taiex)
    tpexid_arr = to_arr(all_dates, tpex_idx)
    tpex_bal_arr = to_arr(all_dates, tpex_bal)

    twse_ma = ma20(twse_nb_arr)
    tpex_ma = ma20(tpex_nb_arr)

    out = {
        "dates": all_dates,
        "twse_idx_raw": taiex_arr,
        "tpex_idx_raw": tpexid_arr,
        "twse_netbuy_daily": [clean(v) for v in twse_nb_arr],
        "tpex_netbuy_daily": [clean(v) for v in tpex_nb_arr],
        "tpex_balance_raw": [None if v is None else round(float(v), 1) for v in tpex_bal_arr],
        "twse_netbuy_ma20": twse_ma,
        "tpex_netbuy_ma20": tpex_ma,
        "twse_ma20_latest": last_nonnull(twse_ma),
        "tpex_ma20_latest": last_nonnull(tpex_ma),
        "baseline": f"{all_dates[0]} ~ {all_dates[-1]}",
        "n": len(all_dates),
        "asof": TODAY,
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
    print(f"區間 {START} ~ {TODAY}")
    print("=" * 60)

    full = "--full" in sys.argv
    old = None
    if not full:
        try:
            with open("chart_data_tw.json", encoding="utf-8") as f:
                old = json.load(f)
            if not old.get("dates"):
                old = None
            # 增量模式需要 tpex_balance_raw 才能正確差分歷史；
            # 舊檔若缺此欄（首次遷移），回退全量重建一次。
            elif "tpex_balance_raw" not in old:
                print("[注意] 舊檔缺 tpex_balance_raw，回退全量重建以建立增量基礎")
                old = None
        except (FileNotFoundError, json.JSONDecodeError):
            old = None

    if old is None:
        build_full()
    else:
        build_incremental(old)

if __name__ == "__main__":
    main()
