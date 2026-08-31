"""
產生 GitHub Pages 用的靜態頁面 docs/index.html

沒有伺服器端 callback，改把圖表資料內嵌進頁面，由前端 Plotly.react 繪製。
hover、框選縮放、時間軸縮圖等 Plotly 原生互動全部保留。

版面由底部懸浮式標籤列切換（切換時指示器會滑動）：
  DRAM       DRAM 現貨報價（TrendForce）
  美債殖利率  美國公債各年期殖利率（MoneyDJ）
  設定       外觀、各資料集資訊、關於

圖例不使用 Plotly 內建的那一份（項目一多在手機上會佔掉大半畫面），
改成一顆顯示各色圓點的小按鈕，點開才列出全部項目，可逐項開關。

要新增圖表分頁：在 PANELS 加一筆即可，標籤列、分頁、圖例、設定頁的資料卡片
都會跟著生成。

    python build_static.py
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import plotly.io as pio

from bond_data import CSV_PATH as BOND_CSV, latest_date as bond_latest, load_bonds
from chart import build_bond_figure, build_figure, series_colors
from dram_data import BASE_DIR, CSV_PATH as DRAM_CSV, latest_date as dram_latest, load_dram
from version import __version__

DOCS_DIR = BASE_DIR / "docs"
OUTPUT = DOCS_DIR / "index.html"

# 圖表分頁定義。新增一組資料只要在這裡加一筆。
PANELS = [
    {
        "id": "dram",
        "tab": "DRAM",
        "title": "DRAM 現貨報價趨勢",
        "meta": "資料來源：TrendForce　·　單位：USD（盤平均）",
        "item_label": "型號",
        "source_name": "TrendForce",
        "source_url": "https://www.trendforce.com.tw/price/dram/dram_spot",
        "csv": DRAM_CSV,
        "load": load_dram,
        "figure": build_figure,
        "latest": dram_latest,
        # 折線圖圖示
        "icon": '<path d="M3 3v16.5A1.5 1.5 0 0 0 4.5 21H21"/>'
                '<path d="M7 15l3.5-4 3 2.5L20 7"/>'
                '<circle cx="20" cy="7" r="1.4" fill="currentColor" stroke="none"/>',
    },
    {
        "id": "bond",
        "tab": "美債殖利率",
        "title": "美國公債殖利率",
        "meta": "資料來源：MoneyDJ　·　單位：%（各年期）",
        "item_label": "年期",
        "source_name": "MoneyDJ",
        "source_url": "https://www.moneydj.com/bond/defaultBD.xdjhtm",
        "csv": BOND_CSV,
        "load": load_bonds,
        "figure": build_bond_figure,
        "latest": bond_latest,
        # 百分比圖示
        "icon": '<line x1="19" y1="5" x2="5" y2="19"/>'
                '<circle cx="6.6" cy="6.6" r="2.4"/>'
                '<circle cx="17.4" cy="17.4" r="2.4"/>',
    },
]

# 齒輪圖示（設定分頁）
SETTINGS_ICON = (
    '<circle cx="12" cy="12" r="3.2"/>'
    '<path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34'
    ' 1.7 1.7 0 0 0-1.03 1.56V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 8.9 19.3a1.7 1.7 0 0 0-1.87.34l-.06.06'
    'a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.56-1.03H3a2 2 0 1 1 0-4h.09'
    'A1.7 1.7 0 0 0 4.7 8.9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6'
    'a1.7 1.7 0 0 0 1.03-1.56V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15.1 4.7a1.7 1.7 0 0 0 1.87-.34l.06-.06'
    'a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9v.03A1.7 1.7 0 0 0 21 10.06H21a2 2 0 1 1 0 4h-.09'
    'a1.7 1.7 0 0 0-1.51 1.03z"/>'
)


def _tab_button(tab_id: str, label: str, icon: str, selected: bool) -> str:
    return (
        f'    <button class="tab" type="button" role="tab" data-tab="{tab_id}"\n'
        f'            aria-selected="{"true" if selected else "false"}"'
        f' aria-controls="panel-{tab_id}">\n'
        f'      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"\n'
        f'           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{icon}</svg>\n'
        f'      <span>{label}</span>\n'
        f'    </button>'
    )


def _tabbar_html() -> str:
    btns = [_tab_button(p["id"], p["tab"], p["icon"], i == 0)
            for i, p in enumerate(PANELS)]
    btns.append(_tab_button("settings", "設定", SETTINGS_ICON, False))
    return ('<nav class="tabbar" role="tablist" aria-label="主要分頁">\n'
            '    <span class="tab-pill" id="tab-pill" aria-hidden="true"></span>\n'
            + "\n".join(btns) + "\n  </nav>")


def _chart_panels_html() -> str:
    out = []
    for i, p in enumerate(PANELS):
        out.append(
            f'  <section id="panel-{p["id"]}" class="panel" role="tabpanel"'
            f'{"" if i == 0 else " hidden"}>\n'
            f'    <div class="chart" id="chart-{p["id"]}"></div>\n'
            f'    <div class="legend-bar" data-chart="{p["id"]}"></div>\n'
            f'  </section>'
        )
    return "\n\n".join(out)


def _stats(p: dict) -> dict:
    """該資料集的摘要，供設定分頁與標頭使用。"""
    df = p["load"]()
    if df.empty:
        return {"latest": "無資料", "rows": 0, "items": 0, "range": "無資料"}
    first = df["price_date"].min().strftime("%Y-%m-%d")
    return {
        "latest": p["latest"](df),
        "rows": len(df),
        "items": df["item"].nunique(),
        "range": f"{first} ～ {p['latest'](df)}",
    }


def _settings_cards(stats: dict) -> str:
    cards = []
    for p in PANELS:
        s = stats[p["id"]]
        cards.append(f'''    <div class="card">
      <div class="card-h">{p["tab"]}　資料</div>
      <div class="row"><span>最後更新日</span><b>{s["latest"]}</b></div>
      <div class="row"><span>資料筆數</span><b>{s["rows"]} 筆</b></div>
      <div class="row"><span>{p["item_label"]}數</span><b>{s["items"]} 項</b></div>
      <div class="row"><span>涵蓋區間</span><b>{s["range"]}</b></div>
      <div class="row"><span>資料來源</span>
        <a href="{p["source_url"]}" target="_blank" rel="noopener">{p["source_name"]}</a></div>
    </div>''')
    return "\n\n".join(cards)


TPL = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>市場走勢</title>

<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="icon-180.png">
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#161a2b">
<meta name="description" content="DRAM 現貨報價與美國公債殖利率走勢，每日自動更新。">

<!-- iOS 加入主畫面：圖示標題與獨立視窗模式 -->
<meta name="apple-mobile-web-app-title" content="市場走勢">
<meta name="application-name" content="市場走勢">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">

<!-- plotly.js 版本必須對應 plotly.py（6.7 → 3.5）：
     plotly.py 6.x 以 base64 二進位陣列輸出資料，2.x 的 plotly.js 畫得出線，
     但無法用它做 hover 的點位查找，指標標籤會完全不出現。 -->
<script src="https://cdn.plot.ly/plotly-3.5.0.min.js" charset="utf-8"></script>
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
  .head-right { display:flex; align-items:center; gap:8px; padding-top:1px; }
  .ver { font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums;
         white-space:nowrap; }
  button { font-family:inherit; color:var(--fg); background:transparent;
           border:1px solid var(--border); border-radius:6px; cursor:pointer; }
  .iconbtn { display:inline-flex; align-items:center; justify-content:center;
             width:32px; height:32px; padding:0; border-radius:8px; color:var(--muted);
             -webkit-tap-highlight-color:transparent; }
  .iconbtn:hover { color:var(--fg); border-color:var(--muted); }
  .iconbtn svg { width:17px; height:17px; }
  .iconbtn.spin svg { animation:spin .8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }

  /* pan-y：垂直滑動仍由瀏覽器捲動頁面，水平與雙指手勢交給 initTouch 處理 */
  .chart { width:100%; height:600px; touch-action:pan-y; }

  /* 收合式圖例 */
  .legend-bar { margin-top:10px; }
  .legend-toggle { display:inline-flex; align-items:center; gap:8px; font-size:13px; padding:7px 12px; }
  .legend-toggle:hover { border-color:var(--muted); }
  .legend-dots { display:inline-flex; gap:3px; }
  .legend-dots i { width:9px; height:9px; border-radius:50%; display:block; }
  .legend-dots i.off { opacity:.25; }
  .chev { font-size:10px; color:var(--muted); transition:transform .15s; }
  .legend-toggle[aria-expanded="true"] .chev { transform:rotate(180deg); }
  .legend-panel { margin-top:8px; border:1px solid var(--border); border-radius:8px; padding:8px; }
  .lg-actions { display:flex; gap:8px; margin-bottom:6px; }
  .lg-actions button { font-size:12px; padding:4px 10px; color:var(--muted); }
  .legend-list { display:grid; gap:2px; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); }
  .lg-item { display:flex; align-items:center; gap:9px; padding:7px 8px; border-radius:6px;
             cursor:pointer; font-size:13px; line-height:1.2; user-select:none; }
  .lg-item:hover { background:var(--hover); }
  .lg-item.off { opacity:.42; }
  .lg-item .sw { width:12px; height:12px; border-radius:50%; flex:none; }

  /* 設定分頁 */
  .card { border:1px solid var(--border); border-radius:10px; background:var(--card);
          padding:4px 14px; margin-bottom:14px; max-width:560px; }
  .card-h { font-size:12px; font-weight:600; letter-spacing:.06em; color:var(--muted);
            padding:12px 0 6px; }
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
         gap:3px; width:88px; padding:8px 0 6px; border:0; background:transparent;
         border-radius:999px; font-size:11px; font-weight:600; letter-spacing:.03em;
         color:var(--tab-fg); transition:color .22s; -webkit-tap-highlight-color:transparent;
         white-space:nowrap; }
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
    .chart { height:520px; }
    .legend-list { grid-template-columns:1fr; }
    .card { max-width:none; }
  }
  @media (prefers-reduced-motion: reduce) {
    .tab-pill, .knob, .switch, .chev { transition:none; }
    .iconbtn.spin svg { animation:none; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1 id="page-title">__TITLE0__</h1>
      <div class="meta" id="page-meta">__META0__</div>
    </div>
    <div class="head-right">
      <button id="reload" class="iconbtn" type="button" title="重新載入" aria-label="重新載入">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="23 4 23 10 17 10"/>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
        </svg>
      </button>
      <span class="ver">__VERSION__</span>
    </div>
  </header>

__CHART_PANELS__

  <section id="panel-settings" class="panel" role="tabpanel" hidden>
    <div class="card">
      <div class="card-h">外觀</div>
      <div class="row">
        <span>深色模式</span>
        <button id="toggle" class="switch" type="button" role="switch"
                aria-checked="false" aria-label="深色模式"><span class="knob"></span></button>
      </div>
    </div>

__SETTINGS_CARDS__

    <div class="card">
      <div class="card-h">關於</div>
      <div class="row"><span>版本</span><b>__VERSION__</b></div>
      <div class="row"><span>頁面產生時間</span><b>__BUILT__</b></div>
      <div class="row"><span>原始碼</span>
        <a href="https://github.com/ChrisHo0317/Local_Dashboard"
           target="_blank" rel="noopener">GitHub</a></div>
      <p class="note">資料每日由 GitHub Actions 自動更新，有新資料才會重新產生頁面。</p>
    </div>
  </section>

  __TABBAR__
</div>

<script>
// 每張圖只嵌入一份 traces：淺色與深色的線條顏色完全相同，只有 layout 不同，
// 各嵌一份會讓頁面體積直接翻倍。
const CHARTS = __CHARTS__;
const HEAD   = __HEAD__;           // 各分頁的標題與說明
const MOBILE_Q = window.matchMedia('(max-width: 820px)');

let dark = false;

Object.keys(CHARTS).forEach(function (k) { CHARTS[k].hidden = new Set(); });

// 窄螢幕：縮小邊界、拿掉 y 軸標題（單位已寫在頁面標頭）、隱藏工具列
function layoutFor(key, mobile) {
  const L = JSON.parse(JSON.stringify(CHARTS[key].layout[dark ? 'dark' : 'light']));
  if (!mobile) return L;
  L.margin = {l: 46, r: 14, t: 54, b: 34};
  L.yaxis  = Object.assign({}, L.yaxis, {title: {text: ''}});
  L.dragmode = false;
  return L;
}

function renderChart(key) {
  const c = CHARTS[key];
  const mobile = MOBILE_Q.matches;
  const data = c.traces.map(function (t, i) {
    return Object.assign({}, t, {visible: c.hidden.has(i) ? 'legendonly' : true});
  });
  Plotly.react('chart-' + key, data, layoutFor(key, mobile), {
    responsive: true,
    displaylogo: false,
    displayModeBar: !mobile,  // 手機隱藏工具列，改用原生手勢與下方時間軸縮圖
    // 觸控裝置上 Plotly 會把單次輕觸判成雙擊而重設縮放，直接關掉；
    // 要回到全區間改用左上角的「全部」按鈕。
    doubleClick: mobile ? false : 'reset+autosize'
  });
  c.rendered = true;
  c.dirty = false;
}

function applyTheme() {
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  document.getElementById('toggle').setAttribute('aria-checked', String(dark));
}

// 只重畫已經顯示過的圖；還沒畫的標記為待重畫，等它第一次被開啟時再處理。
// 在隱藏的分頁裡畫圖會量到錯誤的寬度，指標的座標換算就會失準。
function renderAll() {
  applyTheme();
  Object.keys(CHARTS).forEach(function (k) {
    if (CHARTS[k].rendered) { renderChart(k); } else { CHARTS[k].dirty = true; }
  });
}

// ── 收合式圖例（每張圖各一份，由 .legend-bar 就地生成）─────────
function buildLegend(bar) {
  const key = bar.dataset.chart;
  const c = CHARTS[key];

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'legend-toggle';
  btn.setAttribute('aria-expanded', 'false');
  const dots = document.createElement('span');
  dots.className = 'legend-dots';
  const label = document.createElement('span');
  const chev = document.createElement('span');
  chev.className = 'chev';
  chev.textContent = '\\u25BC';
  btn.appendChild(dots); btn.appendChild(label); btn.appendChild(chev);

  const panel = document.createElement('div');
  panel.className = 'legend-panel';
  panel.hidden = true;
  const actions = document.createElement('div');
  actions.className = 'lg-actions';
  const list = document.createElement('div');
  list.className = 'legend-list';
  panel.appendChild(actions); panel.appendChild(list);

  function sync() {
    c.series.forEach(function (_, i) {
      const off = c.hidden.has(i);
      dots.children[i].classList.toggle('off', off);
      list.children[i].classList.toggle('off', off);
    });
    const shown = c.series.length - c.hidden.size;
    label.textContent = (shown === c.series.length)
      ? c.itemLabel : (c.itemLabel + ' ' + shown + '/' + c.series.length);
  }

  [['show', '全部顯示'], ['hide', '全部隱藏']].forEach(function (a) {
    const ab = document.createElement('button');
    ab.type = 'button'; ab.textContent = a[1];
    ab.addEventListener('click', function () {
      c.hidden.clear();
      if (a[0] === 'hide') c.series.forEach(function (_, i) { c.hidden.add(i); });
      sync(); renderChart(key);
    });
    actions.appendChild(ab);
  });

  c.series.forEach(function (s, i) {
    const dot = document.createElement('i');
    dot.style.background = s.color;
    dots.appendChild(dot);

    const item = document.createElement('div');
    item.className = 'lg-item';
    const sw = document.createElement('span');
    sw.className = 'sw'; sw.style.background = s.color;
    const nm = document.createElement('span');
    nm.textContent = s.name;   // textContent：名稱來自外部資料，不直接當 HTML 插入
    item.appendChild(sw); item.appendChild(nm);
    item.addEventListener('click', function () {
      if (c.hidden.has(i)) { c.hidden.delete(i); } else { c.hidden.add(i); }
      sync(); renderChart(key);
    });
    list.appendChild(item);
  });

  btn.addEventListener('click', function () {
    const open = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!open));
    panel.hidden = open;
  });

  bar.appendChild(btn); bar.appendChild(panel);
  sync();
}

// ── 底部標籤列 ─────────────────────────────────────────────
var tabs = Array.prototype.slice.call(document.querySelectorAll('.tab'));
var pill = document.getElementById('tab-pill');

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
  var h = HEAD[name];
  document.getElementById('page-title').textContent = h.title;
  document.getElementById('page-meta').innerHTML = h.meta;
  // 圖表第一次顯示（或主題變更後首次顯示）才真正繪製；
  // 已畫過的只要重新丈量寬度即可。
  var c = CHARTS[name];
  if (c) {
    if (!c.rendered || c.dirty) { renderChart(name); }
    else { Plotly.Plots.resize(document.getElementById('chart-' + name)); }
  }
}

tabs.forEach(function (t) {
  t.addEventListener('click', function () { selectTab(t.dataset.tab, true); });
});

window.addEventListener('resize', function () {
  var cur = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0];
  if (cur) movePill(cur, false);
});

// ── 觸控手勢 ───────────────────────────────────────────────
// 單指：按下當下就顯示垂直指標線與該時間點的資料，按住拖曳可移動；
//       指標已顯示時再輕點一下（沒有拖動）就收起。
// 雙指：以兩指中心為錨點縮放時間軸。
//
// 繪圖區內的觸控事件會在捕獲階段被攔下（stopPropagation），不讓 Plotly 自己的
// 拖曳／點按處理接手 —— 否則指標會變成放開手指才出現，輕點也會被判成雙擊而重設縮放。
// 落在時間軸縮圖與區間按鈕上的觸控則放行，那些仍由 Plotly 自己處理。
// 桌機滑鼠完全不受影響。
function initTouch(gd) {
  if (!window.matchMedia('(pointer: coarse)').matches) return;

  var pinch = null, shown = false, wasShown = false, moved = false, taken = false;
  var sx = 0, sy = 0;
  var TAP_SLOP = 6;
  var MIN_SPAN = 3 * 864e5;

  function xAxis() { return gd._fullLayout && gd._fullLayout.xaxis; }
  function plotLeft() { return gd.getBoundingClientRect().left + xAxis()._offset; }

  function inPlot(t) {
    var fl = gd._fullLayout;
    if (!fl || !fl.xaxis || !fl.yaxis) return false;
    var r = gd.getBoundingClientRect();
    var px = t.clientX - r.left, py = t.clientY - r.top;
    return px >= fl.xaxis._offset && px <= fl.xaxis._offset + fl.xaxis._length &&
           py >= fl.yaxis._offset && py <= fl.yaxis._offset + fl.yaxis._length;
  }

  function fullExtent() {
    var xa = xAxis(), lo = Infinity, hi = -Infinity;
    (gd.data || []).forEach(function (t) {
      if (!t.x || !t.x.length) return;
      lo = Math.min(lo, xa.d2l(t.x[0]));
      hi = Math.max(hi, xa.d2l(t.x[t.x.length - 1]));
    });
    return (lo < hi) ? [lo, hi] : null;
  }

  function showAt(touch) {
    var xa = xAxis();
    if (!xa) return;
    var px = touch.clientX - plotLeft();
    px = Math.min(Math.max(px, 0), xa._length);
    Plotly.Fx.hover(gd, {xval: xa.p2l(px)}, 'xy');
    shown = true;
  }

  function hide() { Plotly.Fx.unhover(gd); shown = false; }

  // 指標也可能被我們以外的原因清掉（Plotly 內部、其他互動）。
  // 跟著 plotly_unhover 更新旗標，否則「再次輕點收起」會誤判成已顯示而空點一次。
  // 圖表是延後繪製的，gd.on 要等 Plotly 初始化後才有，因此第一次觸控時才綁。
  var unhoverBound = false;
  function bindUnhover() {
    if (unhoverBound || typeof gd.on !== 'function') return;
    gd.on('plotly_unhover', function () { shown = false; });
    unhoverBound = true;
  }

  function dist(e) {
    var dx = e.touches[0].clientX - e.touches[1].clientX;
    var dy = e.touches[0].clientY - e.touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy) || 1;
  }

  gd.addEventListener('touchstart', function (e) {
    var xa = xAxis();
    if (!xa) return;
    bindUnhover();

    if (e.touches.length === 2) {
      if (!inPlot(e.touches[0]) && !inPlot(e.touches[1])) return;
      e.stopPropagation();
      taken = true;
      hide();
      pinch = {
        d: dist(e),
        cx: (e.touches[0].clientX + e.touches[1].clientX) / 2 - plotLeft(),
        r0: xa.d2l(xa.range[0]),
        r1: xa.d2l(xa.range[1]),
        len: xa._length
      };
      return;
    }

    if (e.touches.length !== 1 || !inPlot(e.touches[0])) { taken = false; return; }
    e.stopPropagation();
    taken = true;
    pinch = null;
    wasShown = shown;
    moved = false;
    sx = e.touches[0].clientX;
    sy = e.touches[0].clientY;
    showAt(e.touches[0]);          // 按下當下就顯示，不等放開
  }, {capture: true, passive: true});

  gd.addEventListener('touchmove', function (e) {
    if (pinch && e.touches.length === 2) {
      e.stopPropagation();
      if (e.cancelable) e.preventDefault();
      var scale = pinch.d / dist(e);
      var frac = Math.min(1, Math.max(0, pinch.cx / pinch.len));
      var anchor = pinch.r0 + (pinch.r1 - pinch.r0) * frac;
      var lo = anchor - (anchor - pinch.r0) * scale;
      var hi = anchor + (pinch.r1 - anchor) * scale;
      var ext = fullExtent();
      if (ext) { lo = Math.max(lo, ext[0]); hi = Math.min(hi, ext[1]); }
      if (hi - lo < MIN_SPAN) return;
      Plotly.relayout(gd, {'xaxis.range': [lo, hi]});
      return;
    }

    if (!taken || pinch || e.touches.length !== 1) return;
    var t = e.touches[0];
    if (Math.abs(t.clientX - sx) > TAP_SLOP || Math.abs(t.clientY - sy) > TAP_SLOP) moved = true;
    e.stopPropagation();
    if (e.cancelable) e.preventDefault();
    showAt(t);
  }, {capture: true, passive: false});

  gd.addEventListener('touchend', function (e) {
    if (!taken) return;
    if (e.touches.length > 0) return;
    e.stopPropagation();
    if (pinch) { pinch = null; taken = false; return; }
    if (wasShown && !moved) hide();
    taken = false;
  }, {capture: true, passive: true});

  // 觸控裝置上沒有真的滑鼠：輕觸後瀏覽器會補送一串相容滑鼠事件
  // （mousemove → mousedown → mouseup → click → mouseout），
  // 其中的 mouseout 會讓 Plotly 觸發 unhover，把我們剛設好的指標清掉。
  // 只擋主繪圖區（.nsewdrag）內的這類事件，時間軸縮圖與區間按鈕照常運作。
  ['mousemove', 'mousedown', 'mouseup', 'click', 'dblclick', 'mouseover', 'mouseout']
    .forEach(function (type) {
      gd.addEventListener(type, function (e) {
        if (e.target && e.target.closest && e.target.closest('.nsewdrag')) {
          e.stopPropagation();
        }
      }, {capture: true});
    });
}

// ── 重新載入 ───────────────────────────────────────────────
// GitHub Pages 的 CDN 會把頁面快取約 10 分鐘，單純 location.reload() 常常
// 拿回同一份舊的。改成帶時間戳重新導向，強制取得最新版；用 replace 避免
// 在瀏覽記錄裡堆一堆條目。
document.getElementById('reload').addEventListener('click', function () {
  this.classList.add('spin');
  location.replace(location.pathname + '?r=' + Date.now());
});

// ── 主題 ───────────────────────────────────────────────────
try {
  var saved = localStorage.getItem('dram-theme');
  dark = saved ? saved === 'dark'
               : window.matchMedia('(prefers-color-scheme: dark)').matches;
} catch (e) { dark = false; }

document.querySelectorAll('.legend-bar').forEach(buildLegend);
applyTheme();
selectTab(Object.keys(CHARTS)[0], false);   // 只會畫出第一張圖
Object.keys(CHARTS).forEach(function (k) {
  initTouch(document.getElementById('chart-' + k));
});

document.getElementById('toggle').addEventListener('click', function () {
  dark = !dark;
  renderAll();
  try { localStorage.setItem('dram-theme', dark ? 'dark' : 'light'); } catch (e) {}
});

// 轉螢幕方向 / 改變視窗寬度而跨越斷點時，重新套用對應 layout
if (MOBILE_Q.addEventListener) {
  MOBILE_Q.addEventListener('change', renderAll);
} else if (MOBILE_Q.addListener) {
  MOBILE_Q.addListener(renderAll);   // 舊版 Safari
}
</script>
</body>
</html>
"""


def build() -> Path:
    """讀各資料集、產生 docs/index.html，回傳輸出路徑。"""
    charts = {}
    stats = {}
    head = {}

    for p in PANELS:
        df = p["load"]()
        fig_light = p["figure"](df, dark=False, showlegend=False)
        fig_dark = p["figure"](df, dark=True, showlegend=False)

        light = json.loads(pio.to_json(fig_light))
        darkj = json.loads(pio.to_json(fig_dark))

        # 只嵌入一份 traces 的前提是兩個主題的線條完全相同。
        # plotly_dark 目前與 plotly 共用同一組 colorway，但若哪天不再成立，
        # 這裡要立刻發現，而不是默默送出配色錯誤的頁面。
        if light["data"] != darkj["data"]:
            raise RuntimeError(
                f"{p['id']}：淺色與深色的 traces 不一致，不能只嵌入一份。"
                "請改回各嵌一份，或找出差異來源。"
            )

        charts[p["id"]] = {
            "traces": light["data"],
            "layout": {"light": light["layout"], "dark": darkj["layout"]},
            "series": series_colors(fig_light),
            "itemLabel": p["item_label"],
        }
        stats[p["id"]] = _stats(p)
        head[p["id"]] = {
            "title": p["title"],
            "meta": f'{p["meta"]}<br>最後更新日：{stats[p["id"]]["latest"]}',
        }

    head["settings"] = {"title": "設定", "meta": "外觀、資料集資訊與版本"}

    built = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M (UTC+8)")
    first = PANELS[0]

    html = (
        TPL.replace("__CHART_PANELS__", _chart_panels_html())
           .replace("__SETTINGS_CARDS__", _settings_cards(stats))
           .replace("__TABBAR__", _tabbar_html())
           .replace("__CHARTS__", json.dumps(charts, ensure_ascii=False, separators=(",", ":")))
           .replace("__HEAD__", json.dumps(head, ensure_ascii=False))
           .replace("__TITLE0__", first["title"])
           .replace("__META0__", f'{first["meta"]}<br>最後更新日：{stats[first["id"]]["latest"]}')
           .replace("__BUILT__", built)
           .replace("__VERSION__", __version__)
    )

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"[完成] 已產生 {path}（{path.stat().st_size // 1024} KB）")
