"""
產生 GitHub Pages 用的靜態頁面 docs/index.html

沒有伺服器端 callback，改把圖表資料內嵌進頁面，由前端 Plotly.react 繪製。
hover、框選縮放、時間軸縮圖等 Plotly 原生互動全部保留。

版面由底部懸浮式標籤列切換（切換時指示器會滑動）：
  DRAM    DRAM 現貨報價（TrendForce）
  美債    美國公債各年期殖利率（MoneyDJ）
  黃金    國際金價（Yahoo Finance）
  行事曆  財經事件行事曆（ForexFactory）
  設定    外觀、各資料集資訊、關於

圖例不使用 Plotly 內建的那一份（項目一多在手機上會佔掉大半畫面），
改成一顆顯示各色圓點的小按鈕，點開才列出全部項目，可逐項開關。

分頁分兩種（PANELS 的 kind）：
  chart     留一個空殼由前端 Plotly 繪製
  calendar  在這裡直接產生 HTML（由 calendar_render 負責）

要新增分頁：在 PANELS 加一筆即可，標籤列、分頁、圖例、設定頁的資料卡片
都會跟著生成。

    python build_static.py
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import plotly.io as pio

from bond_data import CSV_PATH as BOND_CSV, latest_date as bond_latest, load_bonds
from calendar_data import CSV_PATH as CAL_CSV, load_events
from calendar_render import panel_html as cal_panel_html, stats as cal_stats
from chart import build_bond_figure, build_figure, build_gold_figure, series_colors
from dram_data import BASE_DIR, CSV_PATH as DRAM_CSV, latest_date as dram_latest, load_dram
from gold_data import CSV_PATH as GOLD_CSV, latest_date as gold_latest, load_gold
from version import __version__

DOCS_DIR = BASE_DIR / "docs"
OUTPUT = DOCS_DIR / "index.html"

# 圖表分頁定義。新增一組資料只要在這裡加一筆。
PANELS = [
    {
        "id": "dram",
        "kind": "chart",
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
        "kind": "chart",
        "tab": "美債",
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
    {
        "id": "gold",
        "kind": "chart",
        "tab": "黃金",
        "title": "國際金價",
        "meta": "資料來源：Yahoo Finance　·　單位：USD／盎司（COMEX 近月期貨）",
        "item_label": "商品",
        "source_name": "Yahoo Finance",
        "source_url": "https://finance.yahoo.com/quote/GC%3DF/",
        "csv": GOLD_CSV,
        "load": load_gold,
        "figure": build_gold_figure,
        "latest": gold_latest,
        # 金幣堆疊圖示
        "icon": '<ellipse cx="12" cy="6.4" rx="7" ry="3"/>'
                '<path d="M5 6.4v5c0 1.66 3.13 3 7 3s7-1.34 7-3v-5"/>'
                '<path d="M5 11.4v5c0 1.66 3.13 3 7 3s7-1.34 7-3v-5"/>',
    },
    {
        "id": "calendar",
        "kind": "calendar",
        "tab": "行事曆",
        "title": "財經行事曆",
        "meta": "資料來源：ForexFactory　·　時間為台北時間（UTC+8）",
        "source_name": "ForexFactory",
        "source_url": "https://www.forexfactory.com/calendar",
        "csv": CAL_CSV,
        "load": load_events,
        # 月曆圖示
        "icon": '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/>'
                '<line x1="3" y1="9.5" x2="21" y2="9.5"/>'
                '<line x1="8" y1="2.5" x2="8" y2="6.5"/>'
                '<line x1="16" y1="2.5" x2="16" y2="6.5"/>',
    },
]

CHART_PANELS = [p for p in PANELS if p.get("kind", "chart") == "chart"]

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


def _panels_html(cal_df) -> str:
    """各分頁的內容。圖表分頁留空殼由 JS 繪製，行事曆分頁在此直接產生 HTML。"""
    out = []
    for i, p in enumerate(PANELS):
        hidden = "" if i == 0 else " hidden"
        if p.get("kind", "chart") == "calendar":
            body = cal_panel_html(cal_df)
        else:
            body = (f'    <div class="chart" id="chart-{p["id"]}"></div>\n'
                    f'    <div class="legend-bar" data-chart="{p["id"]}"></div>')
        out.append(
            f'  <section id="panel-{p["id"]}" class="panel" role="tabpanel"{hidden}>\n'
            f'{body}\n'
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
        if p.get("kind", "chart") == "calendar":
            middle = (f'      <div class="row"><span>事件筆數</span><b>{s["rows"]} 筆</b></div>\n'
                      f'      <div class="row"><span>本頁顯示</span><b>{s["shown"]} 筆</b></div>')
        else:
            middle = (f'      <div class="row"><span>資料筆數</span><b>{s["rows"]} 筆</b></div>\n'
                      f'      <div class="row"><span>{p["item_label"]}數</span><b>{s["items"]} 項</b></div>')
        cards.append(f'''    <div class="card">
      <div class="card-h">
        <span>{p["title"]}　資料</span>
        <button class="switch sw-sm" type="button" role="switch" data-panel="{p["id"]}"
                aria-checked="true" aria-label="顯示{p["tab"]}分頁"><span class="knob"></span></button>
      </div>
      <div class="row"><span>最後更新日</span><b>{s["latest"]}</b></div>
{middle}
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
  /* hidden 屬性的 UA 預設樣式會被元素自己的 display 規則蓋掉
     （例如 .cal-row 是 display:flex），這裡統一補強 */
  [hidden] { display:none !important; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font-family:-apple-system,"Segoe UI","Microsoft JhengHei",sans-serif;
         transition:background .2s,color .2s; -webkit-text-size-adjust:100%; }
  .wrap { max-width:1400px; margin:0 auto;
          padding:0 20px calc(110px + env(safe-area-inset-bottom)); }
  /* 標題釘選在畫面上方。上方的安全區留白移到 header 自己身上，
     否則捲動後 .wrap 的 padding 跟著捲走，標題會貼到瀏海。 */
  header { position:sticky; top:0; z-index:40; background:var(--bg);
           display:flex; gap:16px; align-items:flex-start; justify-content:space-between;
           padding:calc(18px + env(safe-area-inset-top)) 0 12px;
           transition:padding .18s, box-shadow .18s; }
  body.scrolled header { padding-top:calc(9px + env(safe-area-inset-top)); padding-bottom:9px;
                         box-shadow:0 1px 0 var(--border); }
  /* 捲動後收起說明文字，只留標題，才不會吃掉太多畫面 */
  #page-meta { overflow:hidden; max-height:64px; opacity:1;
               transition:max-height .18s, opacity .18s; }
  body.scrolled #page-meta { max-height:0; opacity:0; }
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
  .card-h { display:flex; align-items:center; justify-content:space-between; gap:12px;
            font-size:12px; font-weight:600; letter-spacing:.06em; color:var(--muted);
            padding:11px 0 7px; }
  /* 分頁顯示開關放在卡片右上角，比外觀那顆小一點，才不會喧賓奪主 */
  .switch.sw-sm { width:38px; height:22px; }
  .switch.sw-sm .knob { width:16px; height:16px; }
  .switch.sw-sm[aria-checked="true"] .knob { transform:translateX(16px); }
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

  /* 行事曆 */
  .cal-bar { display:flex; align-items:center; justify-content:space-between;
             gap:10px; flex-wrap:wrap; margin-bottom:12px; }
  .cal-filter { display:flex; gap:8px; flex-wrap:wrap; }
  .chip { font-size:12px; padding:6px 14px; border-radius:999px; color:var(--muted); }
  .chip[aria-pressed="true"] { background:var(--pill); color:var(--fg); border-color:transparent; }
  .cal-clock { font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums;
               white-space:nowrap; }
  .sr { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); }

  /* border-collapse:separate 是必要的：collapse 之下 sticky 的儲存格會弄丟框線，
     所以分隔線改用 inset box-shadow 畫。 */
  .cal-table { width:100%; border-collapse:separate; border-spacing:0;
               table-layout:fixed; font-size:13px; }
  .cal-table th, .cal-table td { text-align:left; vertical-align:top; padding:9px 4px; }
  .cal-table thead th { position:sticky; top:var(--head-h,0px); z-index:3; background:var(--bg);
                        font-size:11px; font-weight:600; color:var(--muted);
                        box-shadow:inset 0 -1px 0 var(--border); padding:6px 4px; }
  .cal-table .cal-time { width:46px; color:var(--muted); font-variant-numeric:tabular-nums; }
  .cal-table .cal-imp  { width:18px; }
  .cal-table .cal-num  { width:56px; text-align:right; font-size:11px; color:var(--muted);
                         font-variant-numeric:tabular-nums; word-break:break-all; }
  /* 日期釘在表頭下方，捲到下一天才換掉 */
  .cal-day-row th { position:sticky; top:calc(var(--head-h,0px) + var(--thead-h,0px));
                    z-index:2; font-size:12px; font-weight:600; color:var(--fg);
                    background:var(--card); padding:7px 4px;
                    box-shadow:inset 0 1px 0 var(--border), inset 0 -1px 0 var(--border); }
  .cal-day.past { opacity:.6; }
  .cal-day.today .cal-day-row th { color:var(--accent); }
  .cal-today-tag { font-size:11px; font-weight:500; margin-left:6px; padding:1px 7px;
                   border-radius:999px; background:var(--accent); color:#fff; }
  .cal-row td { box-shadow:inset 0 -1px 0 var(--border); }
  .dot { display:block; width:8px; height:8px; border-radius:50%; margin-top:5px; }
  .i-high { background:#e8590c; }
  .i-mid  { background:#f08c00; }
  .i-low  { background:#adb5bd; }
  .i-hol  { background:#4dabf7; }
  .cal-title { line-height:1.45; }
  .cal-sub { font-size:11px; color:var(--muted); margin-top:1px; }

  /* 現在時間標示線 */
  .cal-now td { padding:0; }
  .cal-now .now-line { display:flex; align-items:center; gap:8px; padding:3px 4px;
                       border-top:2px solid #e03131; }
  .cal-now .now-tag { font-size:11px; font-weight:600; color:#fff; background:#e03131;
                      border-radius:999px; padding:1px 8px; font-variant-numeric:tabular-nums; }
  .cal-empty { color:var(--muted); font-size:13px; }

  /* 底部標籤列 */
  .tabbar { position:fixed; left:50%; bottom:calc(16px + env(safe-area-inset-bottom));
            transform:translateX(-50%); display:flex; gap:2px; padding:6px;
            border-radius:999px; background:var(--bar-bg); border:1px solid var(--bar-border);
            backdrop-filter:blur(16px) saturate(1.6);
            -webkit-backdrop-filter:blur(16px) saturate(1.6);
            box-shadow:0 6px 26px rgba(0,0,0,.18); z-index:50; }
  .tab { position:relative; z-index:1; display:flex; flex-direction:column; align-items:center;
         gap:3px; width:82px; padding:8px 0 6px; border:0; background:transparent;
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
    /* 分頁變多後，窄螢幕要縮小按鈕才不會超出畫面 */
    .tab { width:68px; }
  }
  @media (max-width:400px) {
    .tab { width:62px; font-size:10px; letter-spacing:0; }
    .tab svg { width:20px; height:20px; }
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
const PANEL_IDS = __PANEL_IDS__;   // 可切換顯示的分頁（設定分頁不可關）
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

// ── 黏著層：把標題與表頭的實際高度餵給 CSS ─────────────────
// 標題高度會變（分頁不同、捲動後說明文字收起），所以用量到的值設 CSS 變數，
// 下面的表頭與日期列才知道該釘在哪個位置。
var pageHeader = document.querySelector('header');
var stickyTicking = false;

function syncSticky() {
  var root = document.documentElement;
  root.style.setProperty('--head-h', pageHeader.offsetHeight + 'px');
  var thead = document.querySelector('.cal-table thead');
  if (thead) root.style.setProperty('--thead-h', thead.offsetHeight + 'px');
}

window.addEventListener('scroll', function () {
  if (stickyTicking) return;
  stickyTicking = true;
  requestAnimationFrame(function () {
    document.body.classList.toggle('scrolled', window.scrollY > 8);
    syncSticky();
    stickyTicking = false;
  });
}, {passive: true});

window.addEventListener('resize', syncSticky);

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
  syncSticky();   // 各分頁的說明文字行數不同，標題高度會跟著變
}

tabs.forEach(function (t) {
  t.addEventListener('click', function () { selectTab(t.dataset.tab, true); });
});

window.addEventListener('resize', function () {
  var cur = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0];
  if (cur) movePill(cur, false);
});

// ── 分頁顯示切換（設定分頁裡每張卡片右上角的開關）───────────
var VIS_KEY = 'dash-visible';
var visible = {};
try { visible = JSON.parse(localStorage.getItem(VIS_KEY)) || {}; } catch (e) { visible = {}; }

function isVisible(id) { return visible[id] !== false; }   // 預設全開

// reselect：由開關觸發時要處理「正在看的分頁被關掉」
function applyVisibility(reselect) {
  PANEL_IDS.forEach(function (id) {
    var on = isVisible(id);
    var tab = document.querySelector('.tab[data-tab="' + id + '"]');
    if (tab) tab.hidden = !on;
    var sw = document.querySelector('.switch[data-panel="' + id + '"]');
    if (sw) sw.setAttribute('aria-checked', String(on));
    if (!on) {
      var panel = document.getElementById('panel-' + id);
      if (panel) panel.hidden = true;
    }
  });

  if (!reselect) return;

  var cur = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0];
  if (!cur || cur.hidden) {
    var next = tabs.filter(function (t) { return !t.hidden; })[0];
    if (next) selectTab(next.dataset.tab, false);
  } else {
    movePill(cur, false);   // 分頁數變了，指示器要重新定位
  }
}

document.querySelectorAll('.switch[data-panel]').forEach(function (sw) {
  sw.addEventListener('click', function () {
    var id = sw.dataset.panel;
    visible[id] = !isVisible(id);
    try { localStorage.setItem(VIS_KEY, JSON.stringify(visible)); } catch (e) {}
    applyVisibility(true);
  });
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

// ── 行事曆：影響程度篩選、標出今天、現在時間標示 ───────────
// 所有跟「現在」有關的東西都在瀏覽器端算，不在產生頁面時寫死 ——
// 頁面會被 CDN 快取，寫死的話隔天再開就會標錯。
(function () {
  var table = document.querySelector('.cal-table');
  if (!table) return;

  var days = Array.prototype.slice.call(table.querySelectorAll('.cal-day'));
  var clock = document.getElementById('cal-clock');
  var minImpact = 0;

  // 台北時間（UTC+8）：不論使用者裝置在哪個時區，顯示都與表格一致
  function taipei() {
    return new Date(Date.now() + (8 * 60 + new Date().getTimezoneOffset()) * 60000);
  }
  function pad(n) { return String(n).padStart(2, '0'); }

  function markDays() {
    var t = taipei();
    var iso = t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());
    days.forEach(function (d) {
      d.classList.toggle('today', d.dataset.date === iso);
      d.classList.toggle('past', d.dataset.date < iso);
      var head = d.querySelector('.cal-day-row th');
      var tag = head.querySelector('.cal-today-tag');
      if (d.dataset.date === iso && !tag) {
        tag = document.createElement('span');
        tag.className = 'cal-today-tag';
        tag.textContent = '今天';
        head.appendChild(tag);
      } else if (d.dataset.date !== iso && tag) {
        tag.remove();
      }
    });
    return iso;
  }

  var nowRow = null;
  function buildNowRow(text) {
    if (!nowRow) {
      nowRow = document.createElement('tr');
      nowRow.className = 'cal-now';
      var td = document.createElement('td');
      td.colSpan = 5;
      var line = document.createElement('div');
      line.className = 'now-line';
      var tag = document.createElement('span');
      tag.className = 'now-tag';
      line.appendChild(tag);
      td.appendChild(line);
      nowRow.appendChild(td);
      nowRow._tag = tag;
    }
    nowRow._tag.textContent = text;
    return nowRow;
  }

  // 把標示線插到今天「已過去」與「還沒到」的事件之間
  function placeNow(iso) {
    var today = days.filter(function (d) { return d.dataset.date === iso; })[0];
    if (!today) { if (nowRow) nowRow.remove(); return; }

    var t = taipei();
    var row = buildNowRow(pad(t.getHours()) + ':' + pad(t.getMinutes()));
    var now = Date.now();
    var rows = Array.prototype.slice.call(today.querySelectorAll('.cal-row'))
                    .filter(function (r) { return !r.hidden; });

    var next = null;
    for (var i = 0; i < rows.length; i++) {
      if (Number(rows[i].dataset.ts) > now) { next = rows[i]; break; }
    }
    if (next) { today.insertBefore(row, next); }
    else { today.appendChild(row); }
  }

  function applyFilter() {
    days.forEach(function (d) {
      var shown = 0;
      Array.prototype.slice.call(d.querySelectorAll('.cal-row')).forEach(function (r) {
        var on = Number(r.dataset.impact) >= minImpact;
        r.hidden = !on;
        if (on) shown++;
      });
      d.hidden = (shown === 0);
    });
  }

  function refresh() {
    var iso = markDays();
    applyFilter();
    placeNow(iso);
    var t = taipei();
    clock.textContent = '現在 ' + (t.getMonth() + 1) + '/' + pad(t.getDate()) + ' ' +
                        pad(t.getHours()) + ':' + pad(t.getMinutes()) + '（UTC+8）';
  }

  Array.prototype.slice.call(document.querySelectorAll('.cal-filter .chip'))
    .forEach(function (c) {
      c.addEventListener('click', function () {
        document.querySelectorAll('.cal-filter .chip').forEach(function (x) {
          x.setAttribute('aria-pressed', String(x === c));
        });
        minImpact = Number(c.dataset.min);
        refresh();
      });
    });

  refresh();
  setInterval(refresh, 30000);   // 每半分鐘更新時鐘與標示線位置
})();

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
applyVisibility(false);
var firstTab = tabs.filter(function (t) { return !t.hidden; })[0];
selectTab(firstTab ? firstTab.dataset.tab : 'settings', false);   // 只會畫出這一張圖
syncSticky();
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

    cal_df = None

    for p in PANELS:
        if p.get("kind", "chart") == "calendar":
            cal_df = p["load"]()
            stats[p["id"]] = cal_stats(cal_df)
            head[p["id"]] = {
                "title": p["title"],
                "meta": f'{p["meta"]}<br>最後更新日：{stats[p["id"]]["latest"]}',
            }
            continue

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
        TPL.replace("__CHART_PANELS__", _panels_html(cal_df))
           .replace("__SETTINGS_CARDS__", _settings_cards(stats))
           .replace("__TABBAR__", _tabbar_html())
           .replace("__CHARTS__", json.dumps(charts, ensure_ascii=False, separators=(",", ":")))
           .replace("__HEAD__", json.dumps(head, ensure_ascii=False))
           .replace("__PANEL_IDS__", json.dumps([p["id"] for p in PANELS]))
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
