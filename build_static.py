"""
產生 GitHub Pages 用的靜態頁面 docs/index.html

沒有伺服器端 callback，改把淺色 / 深色兩份圖表 JSON 內嵌進頁面，
由前端 Plotly.react 切換。hover、框選縮放、時間軸縮圖等 Plotly 原生互動全部保留。

版面分成兩個分頁，由底部懸浮式標籤列切換（切換時有滑動動畫）：
  DRAM  圖表 + 收合式型號圖例
  設定  外觀（深色模式）、資料資訊、關於

圖例不使用 Plotly 內建的那一份（9 個型號在手機上會佔掉大半畫面），
改成一顆顯示各色圓點的小按鈕，點開才列出全部型號，可逐項開關。

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

# 底部標籤列。未來新增分頁時在這裡加一筆，並在 TPL 補上對應的 <section>，
# JS 會自動接手（滑動指示器依按鈕實際位置計算，不必改動任何數值）。
TABS = [
    {
        "id": "dram",
        "label": "DRAM",
        # 折線圖圖示
        "icon": '<path d="M3 3v16.5A1.5 1.5 0 0 0 4.5 21H21"/>'
                '<path d="M7 15l3.5-4 3 2.5L20 7"/>'
                '<circle cx="20" cy="7" r="1.4" fill="currentColor" stroke="none"/>',
    },
    {
        "id": "settings",
        "label": "設定",
        # 齒輪圖示
        "icon": '<circle cx="12" cy="12" r="3.2"/>'
                '<path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34'
                ' 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.9 19.3a1.7 1.7 0 0 0-1.87.34l-.06.06'
                'a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09'
                'A1.7 1.7 0 0 0 4.7 8.9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6'
                'a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15.1 4.7a1.7 1.7 0 0 0 1.87-.34l.06-.06'
                'a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9v.03A1.7 1.7 0 0 0 21 10.06H21a2 2 0 1 1 0 4h-.09'
                'a1.7 1.7 0 0 0-1.51 1.03z"/>',
    },
]


def _tabbar_html() -> str:
    """依 TABS 產生底部標籤列。"""
    btns = []
    for i, t in enumerate(TABS):
        btns.append(
            f'    <button class="tab" type="button" role="tab" data-tab="{t["id"]}"\n'
            f'            aria-selected="{"true" if i == 0 else "false"}"'
            f' aria-controls="panel-{t["id"]}">\n'
            f'      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"\n'
            f'           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{t["icon"]}</svg>\n'
            f'      <span>{t["label"]}</span>\n'
            f'    </button>'
        )
    return ('<nav class="tabbar" role="tablist" aria-label="主要分頁">\n'
            '    <span class="tab-pill" id="tab-pill" aria-hidden="true"></span>\n'
            + "\n".join(btns) + "\n  </nav>")


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
  :root {
    --bg:#fff; --fg:#212529; --muted:#6c757d; --border:#dee2e6; --hover:rgba(0,0,0,.05);
    --card:#fbfbfc; --bar-bg:rgba(255,255,255,.82); --bar-border:rgba(0,0,0,.09);
    --pill:rgba(0,0,0,.075); --tab-fg:#6c757d; --accent:#1f9d6b;
  }
  html[data-theme="dark"] {
    --bg:#1e2130; --fg:#e8e8e8; --muted:#9aa0ac; --border:#333849; --hover:rgba(255,255,255,.07);
    --card:#242839; --bar-bg:rgba(42,47,69,.80); --bar-border:rgba(255,255,255,.10);
    --pill:rgba(255,255,255,.13); --tab-fg:#9aa0ac; --accent:#4dd4ac;
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font-family:-apple-system,"Segoe UI","Microsoft JhengHei",sans-serif;
         transition:background .2s,color .2s; -webkit-text-size-adjust:100%; }
  .wrap { max-width:1400px; margin:0 auto;
          padding:calc(20px + env(safe-area-inset-top)) 20px
                  calc(110px + env(safe-area-inset-bottom)); }
  header { display:flex; gap:16px; align-items:flex-start;
           justify-content:space-between; margin-bottom:14px; }
  h1 { font-size:20px; margin:0 0 4px; font-weight:600; }
  .meta { font-size:13px; color:var(--muted); line-height:1.6; }
  .ver { font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums;
         white-space:nowrap; padding-top:3px; }
  button { font-family:inherit; color:var(--fg); background:transparent;
           border:1px solid var(--border); border-radius:6px; cursor:pointer; }
  #chart { width:100%; height:600px; }

  /* 收合式圖例 */
  .legend-bar { margin-top:10px; }
  #legend-toggle { display:inline-flex; align-items:center; gap:8px; font-size:13px; padding:7px 12px; }
  #legend-toggle:hover { border-color:var(--muted); }
  #legend-dots { display:inline-flex; gap:3px; }
  #legend-dots i { width:9px; height:9px; border-radius:50%; display:block; }
  #legend-dots i.off { opacity:.25; }
  .chev { font-size:10px; color:var(--muted); transition:transform .15s; }
  #legend-toggle[aria-expanded="true"] .chev { transform:rotate(180deg); }
  #legend-panel { margin-top:8px; border:1px solid var(--border); border-radius:8px; padding:8px; }
  .lg-actions { display:flex; gap:8px; margin-bottom:6px; }
  .lg-actions button { font-size:12px; padding:4px 10px; color:var(--muted); }
  #legend-list { display:grid; gap:2px; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); }
  .lg-item { display:flex; align-items:center; gap:9px; padding:7px 8px; border-radius:6px;
             cursor:pointer; font-size:13px; line-height:1.2; user-select:none; }
  .lg-item:hover { background:var(--hover); }
  .lg-item.off { opacity:.42; }
  .lg-item .sw { width:12px; height:12px; border-radius:50%; flex:none; }

  /* 設定分頁 */
  .card { border:1px solid var(--border); border-radius:10px; background:var(--card);
          padding:4px 14px; margin-bottom:14px; max-width:560px; }
  .card-h { font-size:12px; font-weight:600; letter-spacing:.06em; color:var(--muted);
            padding:12px 0 6px; text-transform:uppercase; }
  .row { display:flex; align-items:center; justify-content:space-between; gap:16px;
         padding:11px 0; border-top:1px solid var(--border); font-size:14px; }
  .row b { font-weight:500; font-variant-numeric:tabular-nums; }
  .row a { color:var(--accent); }
  .note { font-size:12px; color:var(--muted); line-height:1.7; margin:0; padding:10px 0 14px;
          border-top:1px solid var(--border); }
  .switch { width:46px; height:26px; flex:none; border-radius:999px; border:1px solid var(--border);
            background:var(--hover); position:relative; padding:0;
            transition:background .2s,border-color .2s; }
  .switch[aria-checked="true"] { background:var(--accent); border-color:var(--accent); }
  .knob { position:absolute; top:2px; left:2px; width:20px; height:20px; border-radius:50%;
          background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.35); transition:transform .2s; }
  .switch[aria-checked="true"] .knob { transform:translateX(20px); }

  /* 底部標籤列 */
  .tabbar { position:fixed; left:50%; bottom:calc(16px + env(safe-area-inset-bottom));
            transform:translateX(-50%); display:flex; gap:2px; padding:6px;
            border-radius:999px; background:var(--bar-bg); border:1px solid var(--bar-border);
            backdrop-filter:blur(16px) saturate(1.6);
            -webkit-backdrop-filter:blur(16px) saturate(1.6);
            box-shadow:0 6px 26px rgba(0,0,0,.18); z-index:50; }
  .tab { position:relative; z-index:1; display:flex; flex-direction:column; align-items:center;
         gap:3px; width:96px; padding:8px 0 6px; border:0; background:transparent;
         border-radius:999px; font-size:11px; font-weight:600; letter-spacing:.05em;
         color:var(--tab-fg); transition:color .22s; -webkit-tap-highlight-color:transparent; }
  .tab[aria-selected="true"] { color:var(--fg); }
  .tab svg { width:22px; height:22px; }
  .tab-pill { position:absolute; top:6px; bottom:6px; left:0; width:0; border-radius:999px;
              background:var(--pill); pointer-events:none;
              transition:transform .32s cubic-bezier(.4,0,.2,1),
                         width .32s cubic-bezier(.4,0,.2,1); }
  .tab-pill.no-anim { transition:none; }

  @media (max-width:820px) {
    .wrap { padding-left:12px; padding-right:12px; }
    h1 { font-size:18px; }
    .meta { font-size:12px; }
    #chart { height:520px; }
    #legend-list { grid-template-columns:1fr; }
    .card { max-width:none; }
  }
  @media (prefers-reduced-motion: reduce) {
    .tab-pill, .knob, .switch, .chev { transition:none; }
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
    <span class="ver">__VERSION__</span>
  </header>

  <section id="panel-dram" class="panel" role="tabpanel">
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
  </section>

  <section id="panel-settings" class="panel" role="tabpanel" hidden>
    <div class="card">
      <div class="card-h">外觀</div>
      <div class="row">
        <span>深色模式</span>
        <button id="toggle" class="switch" type="button" role="switch"
                aria-checked="false" aria-label="深色模式"><span class="knob"></span></button>
      </div>
    </div>

    <div class="card">
      <div class="card-h">資料</div>
      <div class="row"><span>最後報價日</span><b>__LATEST__</b></div>
      <div class="row"><span>資料筆數</span><b>__ROWS__ 筆</b></div>
      <div class="row"><span>型號數</span><b>__ITEMS__ 種</b></div>
      <div class="row"><span>涵蓋區間</span><b>__RANGE__</b></div>
      <div class="row"><span>資料來源</span>
        <a href="https://www.trendforce.com.tw/price/dram/dram_spot"
           target="_blank" rel="noopener">TrendForce</a></div>
      <p class="note">報價每日由 GitHub Actions 自動抓取，有新資料才會重新產生頁面。</p>
    </div>

    <div class="card">
      <div class="card-h">關於</div>
      <div class="row"><span>版本</span><b>__VERSION__</b></div>
      <div class="row"><span>頁面產生時間</span><b>__BUILT__</b></div>
      <div class="row"><span>原始碼</span>
        <a href="https://github.com/ChrisHo0317/Local_Dashboard"
           target="_blank" rel="noopener">GitHub</a></div>
    </div>
  </section>

  __TABBAR__
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
  document.getElementById('toggle').setAttribute('aria-checked', String(dark));
}

// ── 底部標籤列 ─────────────────────────────────────────────
var tabs  = Array.prototype.slice.call(document.querySelectorAll('.tab'));
var pill  = document.getElementById('tab-pill');

function movePill(btn, animate) {
  if (!animate) pill.classList.add('no-anim');
  pill.style.width = btn.offsetWidth + 'px';
  pill.style.transform = 'translateX(' + btn.offsetLeft + 'px)';
  if (!animate) {
    void pill.offsetWidth;            // 強制 reflow，讓 no-anim 立即生效
    pill.classList.remove('no-anim');
  }
}

function selectTab(name, animate) {
  tabs.forEach(function (t) {
    var on = t.dataset.tab === name;
    t.setAttribute('aria-selected', String(on));
    if (on) movePill(t, animate);
    var panel = document.getElementById('panel-' + t.dataset.tab);
    if (panel) panel.hidden = !on;
  });
  // 圖表在隱藏狀態下量不到寬度，切回來要重新丈量
  if (name === 'dram') Plotly.Plots.resize(document.getElementById('chart'));
}

tabs.forEach(function (t) {
  t.addEventListener('click', function () { selectTab(t.dataset.tab, true); });
});

window.addEventListener('resize', function () {
  var cur = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0];
  if (cur) movePill(cur, false);
});

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
selectTab('dram', false);

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
        TPL.replace("__TABBAR__", _tabbar_html())
           .replace("__FIG_LIGHT__", pio.to_json(fig_light))
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
