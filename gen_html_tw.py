#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gen_html_tw.py
台股版「上市/櫃買 融資淨買入 MA20 疊加加權指數」自包含 HTML 報告

输入：chart_data_tw.json  （由 build_tw.py 生成）
输出：台股融资净买入MA20叠加-YYYYMMDD.html  (echarts base64 内联，~1.6MB)
"""
import json
import os
import sys
import base64
import datetime as dt

TODAY = dt.date.today().strftime("%Y%m%d")
# 預設輸出帶日期的檔名（本機用）；Actions 透過 OUTPUT_HTML 環境變數指定 index.html
HTML_FILE = os.environ.get("OUTPUT_HTML") or f"台股融资净买入MA20叠加-{TODAY}.html"

# 1. 读 chart_data_tw.json
with open("chart_data_tw.json", encoding="utf-8") as f:
    d = json.load(f)

dates = d["dates"]
twse_idx = d["twse_idx_raw"]
tpex_idx = d["tpex_idx_raw"]
twse_nb  = d["twse_netbuy_daily"]
tpex_nb  = d["tpex_netbuy_daily"]
twse_ma  = d["twse_netbuy_ma20"]
tpex_ma  = d["tpex_netbuy_ma20"]
twse_latest = d["twse_ma20_latest"]
tpex_latest = d["tpex_ma20_latest"]
baseline = d["baseline"]
n        = d["n"]

# 2. 归一化指數到 2018-01-02=100
def norm(series):
    """用 bfill 找首個非空值當基線 → 解決櫃買指數早期 NaN"""
    out = [None] * len(series)
    base = None
    for i, v in enumerate(series):
        if v is not None:
            if base is None:
                base = v
            out[i] = round(v / base * 100, 2)
    return out

twse_norm = norm(twse_idx)
tpex_norm = norm(tpex_idx)

# 3. 柱狀顏色 (淨買入>0 紅, <0 綠) — A 股慣例
def colors(arr):
    return ["#e04141" if (v is not None and v >= 0) else "#1ca84b" for v in arr]

twse_bar_colors = colors(twse_nb)
tpex_bar_colors = colors(tpex_nb)

# 4. 把 echarts 5.5.1 base64 內聯
EC = open("echarts.min.js", "rb").read()
EC_B64 = base64.b64encode(EC).decode()
EC_TAG = f'<script src="data:application/javascript;base64,{EC_B64}"></script>'

# 5. 計算最後一個有指數 / 淨買入 / MA20 的日期
last_date = dates[-1] if dates else "?"
last_with_data = None
for i in range(len(dates)-1, -1, -1):
    if twse_ma[i] is not None and tpex_ma[i] is not None:
        last_with_data = i
        break
last_with_data = last_with_data if last_with_data is not None else len(dates)-1

# 6. 計算最近 5 日的每日淨買入
def last_n_nonnull(arr, n=5):
    out = []
    for i in range(len(arr)-1, -1, -1):
        if arr[i] is not None:
            out.append((dates[i], arr[i]))
            if len(out) >= n:
                break
    return list(reversed(out))

twse_recent = last_n_nonnull(twse_nb, 5)
tpex_recent = last_n_nonnull(tpex_nb, 5)

# 7. 數據注入 JSON
DATA_JS = json.dumps({
    "dates": dates,
    "twse_idx": twse_idx, "tpex_idx": tpex_idx,
    "twse_idx_norm": twse_norm, "tpex_idx_norm": tpex_norm,
    "twse_nb": twse_nb, "tpex_nb": tpex_nb,
    "twse_ma": twse_ma, "tpex_ma": tpex_ma,
    "twse_bar": twse_bar_colors, "tpex_bar": tpex_bar_colors,
}, ensure_ascii=False)

# 9. HTML template
HTML = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>台股融資淨買入 MA20 疊加上市/櫃買加權指數</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: "Microsoft JhengHei", "Segoe UI", "PingFang TC", sans-serif; margin: 0; padding: 20px; background: #f5f6f8; color: #222; }
  h1 { font-size: 20px; margin: 0; }
  .topbar { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: #fff; border: 1px solid #e6e8eb; border-radius: 10px; margin-bottom: 14px; }
  .topbar .title { display: flex; flex-direction: column; gap: 2px; }
  .topbar .sub { font-size: 12px; color: #8a9099; }
  .topbar .actions { display: flex; gap: 8px; align-items: center; }
  button.refresh { padding: 8px 14px; background: #2563eb; color: #fff; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; }
  button.refresh:hover { background: #1d4ed8; }
  .toast { font-size: 12px; color: #1ca84b; opacity: 0; transition: opacity 0.3s; }
  .toast.show { opacity: 1; }
  .card { background: #fff; border: 1px solid #e6e8eb; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
  .note { font-size: 13px; line-height: 1.6; }
  .note b { color: #1f2937; }
  .tag { display: inline-block; padding: 1px 8px; border-radius: 3px; font-size: 12px; margin: 0 2px; }
  .tag.green { background: rgba(28,168,75,0.15); color: #1ca84b; }
  .tag.red { background: rgba(224,65,65,0.15); color: #e04141; }
  .tag.blue { background: rgba(37,99,235,0.15); color: #2563eb; }
  .recent { display: flex; gap: 20px; flex-wrap: wrap; margin: 8px 0; font-size: 13px; }
  .recent .col { background: #f9fafb; border-radius: 6px; padding: 8px 12px; }
  .recent .col h4 { margin: 0 0 4px 0; font-size: 13px; color: #1f2937; }
  .recent .col table { border-collapse: collapse; font-size: 12px; }
  .recent .col td { padding: 1px 8px 1px 0; }
  #chart1, #chart2 { width: 100%; height: 460px; }
  .lastdata { font-size: 12px; color: #8a9099; margin-top: 6px; }
</style>
</head>
<body>

<div class="topbar">
  <div class="title">
    <h1>台股融資淨買入 MA20 × 上市/櫃買加權指數 疊加圖</h1>
    <div class="sub">區間 __BASELINE__ ｜ 共 __N__ 個交易日 ｜ 上市 = TAIEX、櫃買 = TPEx 收盘</div>
  </div>
  <div class="actions">
    <span class="toast" id="toast"></span>
    <span class="onlinenote" id="onlineNote" style="display:none; font-size:12px; color:#8a9099;">線上為靜態快照，最新資料請本機執行 refresh_tw.bat 更新</span>
    <button class="refresh" id="refreshBtn" title="複製 refresh_tw.bat 絕對路徑">🔄 刷新資料</button>
  </div>
</div>

<div class="card">
  <div class="note">
    <b>讀圖方法：</b>上圖——上市加權 / 櫃買指數以 2018-01-02 為基準歸一化(=100) 疊加，
    <span class="tag blue">橙線 = 上市融資淨買入 MA20</span>、
    <span class="tag red">桃紅線 = 櫃買融資淨買入 MA20</span>，均為右軸(億元 TWD)。
    上市 MA20 附 0 參考線。<br/>
    下圖——兩市每日融資淨買入柱狀(紅=淨買入/加槓桿，綠=淨償還/去槓桿) + 各自 MA20 折線。<br/>
    <b>資料口徑：</b>上市加權與櫃買指數走 FinMind <code>TaiwanStockPrice</code> ；
    上市融資淨買入走 FinMind <code>TaiwanStockTotalMarginPurchaseShortSale</code> 的 <code>MarginPurchaseMoney</code> 字段；
    櫃買融資淨買入走 TPEx 官網 <code>margin_bal_result.php</code> 的 <code>summary[1][6]</code> 仟元餘額差分。
  </div>

  <div class="recent">
    <div class="col">
      <h4>📊 上市 (TAIEX) 最近 5 個交易日淨買入</h4>
      <table>__TWSE_RECENT__</table>
    </div>
    <div class="col">
      <h4>📊 櫃買 (TPEx) 最近 5 個交易日淨買入</h4>
      <table>__TPEX_RECENT__</table>
    </div>
  </div>
</div>

<div class="card"><div id="chart1"></div></div>
<div class="card"><div id="chart2"></div></div>

<div class="lastdata">資料截止：__LAST_DATE__ ｜ 上市 MA20 = __TWSE_MA__ 億 TWD ｜ 櫃買 MA20 = __TPEX_MA__ 億 TWD</div>

<!--ECHARTS_INLINE-->
<script>
const D = __DATA_JS__;

const chart1 = echarts.init(document.getElementById('chart1'));
const chart2 = echarts.init(document.getElementById('chart2'));
const allDates = D.dates;

// ===== 上圖：兩市指數歸一化 + 兩條 MA20 =====
const option1 = {
  title: { text: '上市/櫃買 加權指數（歸一化 2018-01-02=100） × 融資淨買入 MA20（右軸，億 TWD）',
    left: 10, top: 6, textStyle: { fontSize: 14, fontWeight: 600 } },
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross' },
    formatter: function(params) {
      let s = params[0].axisValue + '<br/>';
      params.forEach(p => {
        const v = p.seriesName.indexOf('MA20') >= 0 ? (p.value==null?'-':p.value.toFixed(2)+' 億') :
                   (p.value==null?'-':p.value.toFixed(2));
        s += p.marker + p.seriesName + ': <b>' + v + '</b><br/>';
      });
      return s;
    }
  },
  legend: { top: 32, type:'scroll', data: ['上市加權 (TAIEX)','櫃買指數 (TPEx)','上市融資 MA20','櫃買融資 MA20'] },
  grid: { left: 60, right: 70, top: 70, bottom: 60 },
  xAxis: { type: 'category', data: allDates, axisLabel: { hideOverlap: true }, boundaryGap: false },
  yAxis: [
    { type: 'value', name: '指數(歸一化)', position: 'left',  scale: true,
      axisLabel: { color: '#374151' } },
    { type: 'value', name: '融資淨買入(億)', position: 'right', scale: true,
      axisLabel: { color: '#b45309' } }
  ],
  dataZoom: [
    { type: 'inside', xAxisIndex: 0 },
    { type: 'slider', xAxisIndex: 0, height: 22, bottom: 14 }
  ],
  series: [
    { name:'上市加權 (TAIEX)', type:'line', yAxisIndex:0, smooth:true, showSymbol:false,
      lineStyle:{ width:2, color:'#2563eb' },
      data: D.twse_idx_norm },
    { name:'櫃買指數 (TPEx)', type:'line', yAxisIndex:0, smooth:true, showSymbol:false,
      lineStyle:{ width:2, color:'#9333ea' },
      data: D.tpex_idx_norm },
    { name:'上市融資 MA20', type:'line', yAxisIndex:1, smooth:true, showSymbol:false,
      lineStyle:{ width:2, color:'#f59e0b' },
      data: D.twse_ma,
      markLine:{ silent:true, symbol:'none', label:{ formatter: v => v.name + ' ' + (v.value||0).toFixed(1) },
        data:[
          { name:'0',       yAxis: 0,            lineStyle:{ color:'#9ca3af', type:'dotted' } }
        ]
      }
    },
    { name:'櫃買融資 MA20', type:'line', yAxisIndex:1, smooth:true, showSymbol:false,
      lineStyle:{ width:2, color:'#e04141' },
      data: D.tpex_ma },
  ]
};
chart1.setOption(option1);

// ===== 下圖：兩市每日淨買入柱 + 各自 MA20 =====
const option2 = {
  title: { text: '上市/櫃買 每日融資淨買入（柱） + MA20（折線，億 TWD）',
    left: 10, top: 6, textStyle: { fontSize: 14, fontWeight: 600 } },
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
  legend: { top: 32, type:'scroll',
    data:['上市融資淨買入(日)','櫃買融資淨買入(日)','上市 MA20','櫃買 MA20'] },
  grid: { left: 60, right: 30, top: 70, bottom: 60 },
  xAxis: { type: 'category', data: allDates, axisLabel: { hideOverlap: true }, boundaryGap: true },
  yAxis: { type: 'value', name: '億元 TWD', scale: true, axisLabel: { color: '#374151' } },
  dataZoom: [
    { type: 'inside', xAxisIndex: 0 },
    { type: 'slider', xAxisIndex: 0, height: 22, bottom: 14 }
  ],
  series: [
    { name:'上市融資淨買入(日)', type:'bar',
      data: D.twse_nb.map((v,i) => ({ value: v, itemStyle: { color: D.twse_bar[i] } })),
      barWidth: '45%' },
    { name:'櫃買融資淨買入(日)', type:'bar',
      data: D.tpex_nb.map((v,i) => ({ value: v, itemStyle: { color: D.tpex_bar[i] } })),
      barWidth: '45%' },
    { name:'上市 MA20', type:'line', smooth:true, showSymbol:false,
      lineStyle:{ width:2, color:'#f59e0b' },
      data: D.twse_ma },
    { name:'櫃買 MA20', type:'line', smooth:true, showSymbol:false,
      lineStyle:{ width:2, color:'#e04141' },
      data: D.tpex_ma }
  ]
};
chart2.setOption(option2);

window.addEventListener('resize', () => { chart1.resize(); chart2.resize(); });

// ===== 刷新按鈕（僅本機 file:// 或 localhost 顯示；線上版隱藏並提示靜態快照）=====
const REFRESH_BAT = "__REFRESH_BAT__";
const isLocal = (location.protocol === 'file:') || (location.hostname === 'localhost') || (location.hostname === '127.0.0.1');
const refreshBtn = document.getElementById('refreshBtn');
const onlineNote = document.getElementById('onlineNote');
if (isLocal) {
  refreshBtn.style.display = '';
  refreshBtn.addEventListener('click', () => {
    const toast = document.getElementById('toast');
    const ok = (text) => {
      toast.textContent = text;
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 3500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(REFRESH_BAT).then(
        () => ok('✓ 已複製 refresh_tw.bat 路徑，貼到終端機執行'),
        () => fallbackCopy(REFRESH_BAT, ok)
      );
    } else {
      fallbackCopy(REFRESH_BAT, ok);
    }
  });
} else {
  refreshBtn.style.display = 'none';
  if (onlineNote) onlineNote.style.display = '';
}
function fallbackCopy(text, ok) {
  const ta = document.createElement('textarea');
  ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); ok('✓ 已複製 (降級) — 貼到終端機執行'); }
  catch(e) { ok('✗ 複製失敗，請手動執行：' + text); }
  document.body.removeChild(ta);
}
</script>
</body>
</html>
"""

# 替換占位符
def render_recent_table(rows):
    if not rows: return "<tr><td>—</td></tr>"
    s = ""
    for d, v in rows:
        color = "#e04141" if v >= 0 else "#1ca84b"
        s += f'<tr><td>{d}</td><td style="color:{color}; font-weight:600;">{v:+.2f} 億</td></tr>'
    return s

html = (HTML
    .replace("__BASELINE__", baseline)
    .replace("__N__", str(n))
    .replace("__LAST_DATE__", last_date)
    .replace("__TWSE_MA__", f"{twse_latest:.2f}" if twse_latest is not None else "—")
    .replace("__Tpex_MA__", f"{tpex_latest:.2f}" if tpex_latest is not None else "—")
    .replace("__TPEX_MA__", f"{tpex_latest:.2f}" if tpex_latest is not None else "—")
    .replace("__TWSE_RECENT__", render_recent_table(twse_recent))
    .replace("__TPEX_RECENT__", render_recent_table(tpex_recent))
    .replace("__REFRESH_BAT__", os.path.abspath("refresh_tw.bat").replace("\\","/"))
    .replace("__DATA_JS__", DATA_JS)
    .replace("<!--ECHARTS_INLINE-->", EC_TAG)
)

with open(HTML_FILE, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✓ 已輸出 {HTML_FILE}  ({len(html)/1024:.1f} KB)")
print(f"  上市 MA20 末值 = {twse_latest} 億 TWD")
print(f"  櫃買 MA20 末值 = {tpex_latest} 億 TWD")
