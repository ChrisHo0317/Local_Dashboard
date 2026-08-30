"""
產生 GitHub Pages 用的靜態頁面 docs/index.html

沒有伺服器端 callback，改把淺色 / 深色兩份圖表 JSON 內嵌進頁面，
由前端 Plotly.react 切換。hover、框選縮放、時間軸縮圖等 Plotly 原生互動全部保留。

圖例不使用 Plotly 內建的那一份（9 個型號在手機上會佔掉大半畫面），
改成頁面上一顆顯示各色圓點的小按鈕，點開才列出全部型號，可逐項開關。

    python build_static.py
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import plotly.io as pio

from chart import build_figure, series_colors
from dram_data import BASE_DIR, latest_date, load_dram
from version import __version__

DOCS_DIR = BASE_DIR / "docs"
OUTPUT = DOCS_DIR / "index.html"

TPL = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>DRAM 現貨報價</title>

<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="icon-180.png">
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#161a2b">
<meta name="description" content="TrendForce DRAM 現貨報價歷史走勢，每日自動更新。">

<!-- iOS 加入主畫面：圖示標題與獨立視窗模式 -->
<meta name="apple-mobile-web-app-title" content="DRAM 報價">
<meta name="application-name" content="DRAM 報價">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">

<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  :root { --bg:#fff; --fg:#212529; --muted:#6c757d; --border:#dee2e6; --hover:rgba(0,0,0,.05); }
  html[data-theme="dark"] { --bg:#1e2130; --fg:#e8e8e8; --muted:#9aa0ac; --border:#333849; --hover:rgba(255,255,255,.07); }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font-family:-apple-system,"Segoe UI","Microsoft JhengHei",sans-serif;
         transition:background .2s,color .2s; -webkit-text-size-adjust:100%; }
  .wrap { max-width:1400px; margin:0 auto;
          padding:calc(20px + env(safe-area-inset-top)) 20px calc(32px + env(safe-area-inset-bottom)); }
  header { display:flex; flex-wrap:wrap; gap:12px; align-items:center;
           justify-content:space-between; margin-bottom:12px; }
  h1 { font-size:20px; margin:0 0 4px; font-weight:600; }
  .meta { font-size:13px; color:var(--muted); line-height:1.6; }
  button { font-family:inherit; color:var(--fg); background:transparent;
           border:1px solid var(--border); border-radius:6px; cursor:pointer; }
  button:hover { border-color:var(--muted); }
  #toggle { font-size:13px; padding:7px 14px; white-space:nowrap; }
  #chart { width:100%; height:600px; }

  /* 收合式圖例 */
  .legend-bar { margin-top:10px; }
  #legend-toggle { display:inline-flex; align-items:center; gap:8px;
                   font-size:13px; padding:7px 12px; }
  #legend-dots { display:inline-flex; gap:3px; }
  #legend-dots i { width:9px; height:9px; border-radius:50%; display:block; }
  #legend-dots i.off { opacity:.25; }
  .chev { font-size:10px; color:var(--muted); transition:transform .15s; }
  #legend-toggle[aria-expanded="true"] .chev { transform:rotate(180deg); }
  #legend-panel { margin-top:8px; border:1px solid var(--border); border-radius:8px; padding:8px; }
  .lg-actions { display:flex; gap:8px; margin-bottom:6px; }
  .lg-actions button { font-size:12px; padding:4px 10px; color:var(--muted); }
  #legend-list { display:grid; gap:2px;
                 grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); }
  .lg-item { display:flex; align-items:center; gap:9px; padding:7px 8px;
             border-radius:6px; cursor:pointer; font-size:13px; line-height:1.2;
             user-select:none; }
  .lg-item:hover { background:var(--hover); }
  .lg-item.off { opacity:.42; }
  .lg-item .sw { width:12px; height:12px; border-radius:50%; flex:none; }

  footer { margin-top:16px; font-size:12px; color:var(--muted); line-height:1.7; }
  footer a { color:inherit; }
  .ver { font-variant-numeric:tabular-nums; opacity:.8; }

  @media (max-width:820px) {
    .wrap { padding-left:12px; padding-right:12px; }
    h1 { font-size:18px; }
    .meta { font-size:12px; }
    #chart { height:520px; }
    #legend-list { grid-template-columns:1fr; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>DRAM 現貨報價趨勢</h1>
      <div class="meta">資料來源：TrendForce　·　單位：USD（盤平均）<br>最後報價日：__LATEST__</div>
    </div>
    <button id="toggle" type="button">深色模式</button>
  </header>

  <div id="chart"></div>

  <div class="legend-bar">
    <button id="legend-toggle" type="button" aria-expanded="false" aria-controls="legend-panel">
      <span id="legend-dots"></span>
      <span id="legend-label">型號</span>
      <span class="chev">&#9660;</span>
    </button>
    <div id="legend-panel" hidden>
      <div class="lg-actions">
        <button type="button" data-all="show">全部顯示</button>
        <button type="button" data-all="hide">全部隱藏</button>
      </div>
      <div id="legend-list"></div>
    </div>
  </div>

  <footer>
    共 __ROWS__ 筆報價，__ITEMS__ 種型號，區間 __RANGE__。<br>
    圖表由 <a href="https://github.com/ChrisHo0317/Local_Dashboard">Local_Dashboard</a> 每日自動更新　·
    頁面產生時間：__BUILT__　·　<span class="ver">__VERSION__</span>
  </footer>
</div>

<script>
const FIG_LIGHT = __FIG_LIGHT__;
const FIG_DARK  = __FIG_DARK__;
const SERIES    = __SERIES__;
const MOBILE_Q  = window.matchMedia('(max-width: 820px)');

const hidden = new Set();   // 被關掉的線（索引）
let dark = false;

// 窄螢幕：縮小邊界、拿掉 y 軸標題（單位已寫在頁面標頭）、隱藏工具列
function layoutFor(fig, mobile) {
  const L = JSON.parse(JSON.stringify(fig.layout));
  if (!mobile) return L;
  L.margin = {l: 46, r: 14, t: 54, b: 34};
  L.yaxis  = Object.assign({}, L.yaxis, {title: {text: ''}});
  return L;
}

function render() {
  const fig = dark ? FIG_DARK : FIG_LIGHT;
  const mobile = MOBILE_Q.matches;
  const data = fig.data.map(function (t, i) {
    return Object.assign({}, t, {visible: hidden.has(i) ? 'legendonly' : true});
  });
  Plotly.react('chart', data, layoutFor(fig, mobile), {
    responsive: true,
    displaylogo: false,
    displayModeBar: !mobile   // 手機隱藏工具列，改用原生手勢與下方時間軸縮圖
  });
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  document.getElementById('toggle').textContent = dark ? '淺色模式' : '深色模式';
}

// ── 收合式圖例 ─────────────────────────────────────────────
var dotsBox = document.getElementById('legend-dots');
var listBox = document.getElementById('legend-list');
var panel   = document.getElementById('legend-panel');
var legBtn  = document.getElementById('legend-toggle');

SERIES.forEach(function (s, i) {
  var dot = document.createElement('i');
  dot.style.background = s.color;
  dotsBox.appendChild(dot);

  var item = document.createElement('div');
  item.className = 'lg-item';
  item.dataset.i = i;
  var sw = document.createElement('span');
  sw.className = 'sw';
  sw.style.background = s.color;
  var nm = document.createElement('span');
  nm.textContent = s.name;   // 用 textContent：名稱來自爬蟲，不直接當 HTML 插入
  item.appendChild(sw);
  item.appendChild(nm);
  listBox.appendChild(item);
});

function syncLegend() {
  SERIES.forEach(function (s, i) {
    var off = hidden.has(i);
    dotsBox.children[i].classList.toggle('off', off);
    listBox.children[i].classList.toggle('off', off);
  });
  var shown = SERIES.length - hidden.size;
  document.getElementById('legend-label').textContent =
    (shown === SERIES.length) ? '型號' : ('型號 ' + shown + '/' + SERIES.length);
}

listBox.addEventListener('click', function (e) {
  var el = e.target.closest('.lg-item');
  if (!el) return;
  var i = Number(el.dataset.i);
  if (hidden.has(i)) { hidden.delete(i); } else { hidden.add(i); }
  syncLegend();
  render();
});

document.querySelectorAll('.lg-actions button').forEach(function (b) {
  b.addEventListener('click', function () {
    hidden.clear();
    if (b.dataset.all === 'hide') {
      SERIES.forEach(function (_, i) { hidden.add(i); });
    }
    syncLegend();
    render();
  });
});

legBtn.addEventListener('click', function () {
  var open = legBtn.getAttribute('aria-expanded') === 'true';
  legBtn.setAttribute('aria-expanded', String(!open));
  panel.hidden = open;
});

// ── 主題 ───────────────────────────────────────────────────
try {
  var saved = localStorage.getItem('dram-theme');
  dark = saved ? saved === 'dark'
               : window.matchMedia('(prefers-color-scheme: dark)').matches;
} catch (e) { dark = false; }

syncLegend();
render();

document.getElementById('toggle').addEventListener('click', function () {
  dark = !dark;
  render();
  try { localStorage.setItem('dram-theme', dark ? 'dark' : 'light'); } catch (e) {}
});

// 轉螢幕方向 / 改變視窗寬度而跨越斷點時，重新套用對應 layout
if (MOBILE_Q.addEventListener) {
  MOBILE_Q.addEventListener('change', render);
} else if (MOBILE_Q.addListener) {
  MOBILE_Q.addListener(render);   // 舊版 Safari
}
</script>
</body>
</html>
"""


def build() -> Path:
    """讀 CSV、產生 docs/index.html，回傳輸出路徑。"""
    df = load_dram()

    if df.empty:
        rows = items = 0
        date_range = "無資料"
    else:
        rows = len(df)
        items = df["item"].nunique()
        first = df["price_date"].min().strftime("%Y-%m-%d")
        date_range = f"{first} ～ {latest_date(df)}"

    built = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M (UTC+8)")

    fig_light = build_figure(df, dark=False, showlegend=False)
    fig_dark = build_figure(df, dark=True, showlegend=False)

    html = (
        TPL.replace("__FIG_LIGHT__", pio.to_json(fig_light))
           .replace("__FIG_DARK__", pio.to_json(fig_dark))
           .replace("__SERIES__", json.dumps(series_colors(fig_light), ensure_ascii=False))
           .replace("__LATEST__", latest_date(df) or "無資料")
           .replace("__ROWS__", str(rows))
           .replace("__ITEMS__", str(items))
           .replace("__RANGE__", date_range)
           .replace("__BUILT__", built)
           .replace("__VERSION__", __version__)
    )

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"[完成] 已產生 {path}（{path.stat().st_size // 1024} KB）")
