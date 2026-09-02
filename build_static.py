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
from chart import (build_bond_figure, build_figure, build_gold_figure,
                   build_points_figure, series_colors)
from dram_data import BASE_DIR, CSV_PATH as DRAM_CSV, latest_date as dram_latest, load_dram
from f1_data import CSV_PATH as F1_CSV, load_all as load_f1_all, load_points_series
from f1_render import panel_html as f1_panel_html, stats as f1_stats
from gold_data import CSV_PATH as GOLD_CSV, latest_date as gold_latest, load_gold
from news_data import CSV_PATH as NEWS_CSV, load_all as load_news_all
from news_render import panel_html as news_panel_html, stats as news_stats
from spacex_data import CSV_PATH as SPACEX_CSV, load_all as load_spacex_all
from spacex_render import panel_html as spacex_panel_html, stats as spacex_stats
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
        "render": cal_panel_html,
        "stats": cal_stats,
        # 月曆圖示
        "icon": '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/>'
                '<line x1="3" y1="9.5" x2="21" y2="9.5"/>'
                '<line x1="8" y1="2.5" x2="8" y2="6.5"/>'
                '<line x1="16" y1="2.5" x2="16" y2="6.5"/>',
    },
    {
        "id": "f1",
        "kind": "calendar",
        "tab": "F1",
        "title": "F1 賽程表",
        "meta": "資料來源：F1 Calendar　·　時間為台北時間（UTC+8）",
        "source_name": "F1 Calendar",
        "source_url": "https://f1calendar.com/zh-HK",
        "csv": F1_CSV,
        "load": load_f1_all,
        "render": f1_panel_html,
        "stats": f1_stats,
        # 方格旗圖示
        "icon": '<path d="M5 3v18"/>'
                '<path d="M5 4.5h14v10H5z"/>'
                '<path d="M5 4.5h4.7v3.3H5zm9.3 0H19v3.3h-4.7zM9.7 7.8h4.6v3.3H9.7zM5 11.1h4.7v3.4H5zm9.3 0H19v3.4h-4.7z"'
                ' fill="currentColor" stroke="none"/>',
    },
    {
        "id": "spacex",
        "kind": "calendar",
        "tab": "SpaceX",
        "title": "SpaceX 發射排程",
        "meta": "資料來源：SpaceX　·　時間為台北時間（UTC+8）",
        "source_name": "SpaceX",
        "source_url": "https://www.spacex.com/launches",
        "csv": SPACEX_CSV,
        "load": load_spacex_all,
        "render": spacex_panel_html,
        "stats": spacex_stats,
        # 火箭圖示
        "icon": '<path d="M12 2.5c2.6 2.2 4 5.5 4 9v4.5l-2 2h-4l-2-2V11.5c0-3.5 1.4-6.8 4-9z"/>'
                '<circle cx="12" cy="10" r="1.7"/>'
                '<path d="M8 13.5 5.5 16v3l2.5-1.6M16 13.5 18.5 16v3L16 17.4"/>'
                '<path d="M10.6 20.2 12 22.5l1.4-2.3"/>',
    },
    {
        "id": "news",
        "kind": "calendar",
        "tab": "新聞",
        "title": "新聞",
        "meta": "資料來源：各新聞網站　·　點標題可看內文",
        "source_name": "各新聞網站",
        "source_url": "https://technews.tw/",
        "csv": NEWS_CSV,
        "load": load_news_all,
        "render": news_panel_html,
        "stats": news_stats,
        # 報紙圖示
        "icon": '<path d="M4 5.5h13v13H4z"/>'
                '<path d="M17 9h3v7.5a2 2 0 0 1-2 2H4"/>'
                '<line x1="7" y1="9" x2="14" y2="9"/>'
                '<line x1="7" y1="12" x2="14" y2="12"/>'
                '<line x1="7" y1="15" x2="11" y2="15"/>',
    },
]

CHART_PANELS = [p for p in PANELS if p.get("kind", "chart") == "chart"]

# 不自成一個分頁、而是嵌在別的分頁裡的圖表（F1 積分子分頁的走勢圖）
EXTRA_CHARTS = [
    {"key": "f1drivers", "kind": "driver", "item_label": "車手"},
    {"key": "f1teams", "kind": "constructor", "item_label": "車隊"},
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


def _panels_html(panel_data) -> str:
    """各分頁的內容。圖表分頁留空殼由 JS 繪製，行事曆分頁在此直接產生 HTML。"""
    out = []
    for i, p in enumerate(PANELS):
        hidden = "" if i == 0 else " hidden"
        if p.get("kind", "chart") == "calendar":
            body = p["render"](panel_data[p["id"]])
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
            # 各表格分頁的重點數字不同：F1 看站數、SpaceX 看即將發射場次
            extra = ""
            if "sources" in s:
                extra = f'      <div class="row"><span>來源數</span><b>{s["sources"]} 個</b></div>\n'
            elif "races" in s:
                extra = f'      <div class="row"><span>賽事站數</span><b>{s["races"]} 站</b></div>\n'
            elif "upcoming" in s:
                extra = f'      <div class="row"><span>即將發射</span><b>{s["upcoming"]} 場</b></div>\n'
            middle = (f'      <div class="row"><span>資料筆數</span><b>{s["rows"]} 筆</b></div>\n'
                      f'{extra}'
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
  .cal-table .cal-sess { width:78px; text-align:right; font-size:11px; color:var(--muted); }
  /* SpaceX：即將發射／進行中的小標籤 */
  .sx-tag { font-size:10px; font-weight:600; margin-left:6px; padding:1px 7px;
            border-radius:999px; background:var(--accent); color:#fff;
            vertical-align:1px; white-space:nowrap; }
  /* F1：日期與時間疊成兩行，一個賽事週末橫跨數天也看得清楚 */
  .cal-table .cal-when { width:76px; }
  .w-date { font-size:11px; color:var(--muted); line-height:1.3; }
  .w-time { font-variant-numeric:tabular-nums; line-height:1.3; }
  /* 分組標題（F1 用兩行：賽事 + 地點/日期）*/
  .grp-head { display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .grp-main { font-size:12px; font-weight:600; color:var(--fg); }
  .grp-sub { font-size:11px; font-weight:400; color:var(--muted); margin-top:1px; }
  .grp-chev { font-size:10px; color:var(--muted); transition:transform .15s; flex:none; }
  /* 可摺疊的分組：整列可點，收合時只留標題 */
  .cal-day.collapsible .cal-day-row th { cursor:pointer; user-select:none;
                                        -webkit-tap-highlight-color:transparent; }
  .cal-day.collapsible .cal-day-row th[aria-expanded="false"] .grp-chev {
    transform:rotate(-90deg); }
  .cal-day.collapsed .cal-row, .cal-day.collapsed .cal-now { display:none; }
  /* 日期釘在表頭下方，捲到下一天才換掉 */
  .cal-day-row th { position:sticky; top:calc(var(--head-h,0px) + var(--thead-h,0px));
                    z-index:2; font-size:12px; font-weight:600; color:var(--fg);
                    background:var(--card); padding:7px 4px;
                    box-shadow:inset 0 1px 0 var(--border), inset 0 -1px 0 var(--border); }
  .cal-day.past { opacity:.6; }
  /* 置頂區塊（進行中的任務）：標題不可點，也沒有摺疊箭頭 */
  .cal-day.pinned .cal-day-row th { cursor:default; }
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

  /* 二階分頁 */
  /* 來源多的時候（新聞有 5 個）橫向捲動，不要把標籤擠成直排 */
  .subtabs { display:flex; gap:6px; margin-bottom:14px; overflow-x:auto;
             scrollbar-width:none; -webkit-overflow-scrolling:touch; }
  .subtabs::-webkit-scrollbar { display:none; }
  .subtab { flex:none; white-space:nowrap;
            font-size:13px; padding:7px 16px; border-radius:999px; color:var(--muted); }
  .subtab[aria-selected="true"] { background:var(--pill); color:var(--fg); border-color:transparent;
                                  font-weight:600; }

  .grandtabs { display:flex; gap:6px; margin-bottom:12px; }
  .grandtab { font-size:12px; padding:5px 14px; border-radius:999px; color:var(--muted); }
  .grandtab[aria-selected="true"] { background:var(--pill); color:var(--fg);
                                    border-color:transparent; font-weight:600; }
  /* 嵌在分頁裡的小圖：不需要跟主圖表分頁一樣高 */
  .chart.chart-sm { height:360px; }
  @media (max-width:820px) { .chart.chart-sm { height:320px; } }

  /* 積分榜 */
  .rank-table { width:100%; border-collapse:separate; border-spacing:0;
                table-layout:fixed; font-size:13px; }
  .rank-table th, .rank-table td { text-align:left; vertical-align:top; padding:10px 4px; }
  .rank-table thead th { position:sticky; top:var(--head-h,0px); z-index:3; background:var(--bg);
                         font-size:11px; font-weight:600; color:var(--muted);
                         box-shadow:inset 0 -1px 0 var(--border); padding:6px 4px; }
  .rank-table tbody td { box-shadow:inset 0 -1px 0 var(--border); }
  .rank-table .rk-pos  { width:52px; font-variant-numeric:tabular-nums; color:var(--muted); }
  .rank-table .rk-pts  { width:50px; text-align:right; font-variant-numeric:tabular-nums;
                         font-weight:600; }
  .rank-table .rk-num  { width:44px; text-align:right; font-size:12px; color:var(--muted);
                         font-variant-numeric:tabular-nums; }
  .gain { font-size:10px; margin-left:3px; }
  .gain.up { color:#2f9e44; }
  .gain.down { color:#e03131; }

  /* 新聞：條列清單 + 內文檢視 */
  .news-list { list-style:none; margin:0; padding:0; }
  .news-item { display:flex; gap:10px; align-items:baseline; padding:12px 2px;
               box-shadow:inset 0 -1px 0 var(--border); cursor:pointer;
               -webkit-tap-highlight-color:transparent; }
  .news-item:hover { background:var(--hover); }
  .news-no { flex:none; width:22px; text-align:right; font-size:12px; color:var(--muted);
             font-variant-numeric:tabular-nums; }
  .news-main { display:block; min-width:0; }
  .news-title { display:block; font-size:14px; line-height:1.5; }
  .news-meta { display:block; font-size:11px; color:var(--muted); margin-top:3px; }
  .news-article { padding-top:2px; }
  .news-back { font-size:13px; padding:6px 12px; border-radius:8px; color:var(--muted);
               margin-bottom:14px; }
  .news-back:hover { color:var(--fg); border-color:var(--muted); }
  .news-h { font-size:18px; line-height:1.45; margin:0 0 6px; font-weight:600; }
  .news-body { margin-top:14px; }
  .news-body p { font-size:15px; line-height:1.8; margin:0 0 14px; }
  .news-nobody { color:var(--muted); font-size:13px; }
  .news-link { display:inline-block; margin-top:4px; font-size:13px; color:var(--accent); }
  .news-more { display:block; width:100%; margin-top:14px; padding:12px;
               font-size:13px; color:var(--muted); border-radius:10px; }

  /* 底部標籤列 */
  /* 分頁再增加時標籤列會塞不下，允許橫向捲動當保險（塞得下時不會出現捲軸）*/
  .tabbar { position:fixed; left:50%; bottom:calc(16px + env(safe-area-inset-bottom));
            transform:translateX(-50%); display:flex; gap:2px; padding:6px;
            max-width:calc(100vw - 20px); overflow-x:auto;
            scrollbar-width:none; -webkit-overflow-scrolling:touch;
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
  .tabbar::-webkit-scrollbar { display:none; }
  .tab { flex:none; }
  .tab-pill.no-anim { transition:none; }

  @media (max-width:820px) {
    .wrap { padding-left:12px; padding-right:12px; }
    h1 { font-size:18px; }
    .meta { font-size:12px; }
    .chart { height:520px; }
    .legend-list { grid-template-columns:1fr; }
    .card { max-width:none; }
    /* 分頁變多後，窄螢幕要縮小按鈕才不會超出畫面 */
    .tab { width:56px; }
  }
  @media (max-width:400px) {
    .tab { width:50px; font-size:10px; letter-spacing:0; }
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

// Plotly 不會因為 x 縮放而自動調整 y，切到短區間時線會擠成一團。
// 這裡依「目前 x 範圍內、且沒被關掉的線」重算 y 範圍。
// 用 calcdata 而不是原始 data：calcdata 的 x 已經是數值（毫秒），
// y 也解好了（嵌入的資料是 base64 二進位陣列），不必逐點換算。
function rescaleY(gd) {
  var fl = gd._fullLayout;
  if (!fl || !fl.xaxis || !gd.calcdata) return;
  var x0 = fl.xaxis.r2l(fl.xaxis.range[0]);
  var x1 = fl.xaxis.r2l(fl.xaxis.range[1]);
  var lo = Infinity, hi = -Infinity;

  gd.calcdata.forEach(function (cd, i) {
    var tr = (gd._fullData || [])[i];
    if (!tr || tr.visible !== true) return;
    for (var j = 0; j < cd.length; j++) {
      var pt = cd[j];
      var y = pt.y;
      if (y === undefined || y === null || y !== y) continue;   // y!==y 濾 NaN
      if (pt.x < x0 || pt.x > x1) continue;
      if (y < lo) lo = y;
      if (y > hi) hi = y;
    }
  });

  if (lo === Infinity || hi === -Infinity) return;
  var pad = (hi - lo) * 0.04 || Math.abs(hi) * 0.02 || 1;
  // 價格與殖利率都不會是負的，下緣不要因為留白而掉到 0 以下
  var bottom = (lo >= 0) ? Math.max(0, lo - pad) : lo - pad;
  Plotly.relayout(gd, {'yaxis.range': [bottom, hi + pad]});
}

function renderChart(key) {
  const c = CHARTS[key];
  const gd = document.getElementById('chart-' + key);
  const mobile = MOBILE_Q.matches;
  const data = c.traces.map(function (t, i) {
    return Object.assign({}, t, {visible: c.hidden.has(i) ? 'legendonly' : true});
  });
  const L = layoutFor(key, mobile);

  // 已經畫過的話沿用目前的時間軸範圍：切換型號顯示或深色模式時，
  // 不該把使用者已經縮放好的區間重設回預設值。
  if (c.rendered && gd._fullLayout && gd._fullLayout.xaxis) {
    L.xaxis = Object.assign({}, L.xaxis, {range: gd._fullLayout.xaxis.range.slice()});
  }

  Plotly.react(gd, data, L, {
    responsive: true,
    displaylogo: false,
    displayModeBar: !mobile,  // 手機隱藏工具列，改用原生手勢與下方時間軸縮圖
    // 觸控裝置上 Plotly 會把單次輕觸判成雙擊而重設縮放，直接關掉；
    // 要回到全區間改用左上角的「全部」按鈕。
    doubleClick: mobile ? false : 'reset+autosize'
  });

  if (!c.bound) {
    // 改變時間軸範圍後重算 y。自己的 relayout 也會觸發這個事件，用旗標擋掉遞迴。
    gd.on('plotly_relayout', function (ev) {
      if (c.busy) return;
      var touchedX = Object.keys(ev || {}).some(function (k) { return k.indexOf('xaxis') === 0; });
      if (!touchedX) return;
      c.busy = true;
      rescaleY(gd);
      setTimeout(function () { c.busy = false; }, 0);
    });
    c.bound = true;
  }

  c.rendered = true;
  c.dirty = false;
  rescaleY(gd);            // 型號顯示改變後 y 也要跟著重算
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
  // 有二階分頁的話，回到主分頁時重設回第一個子分頁
  var panel = document.getElementById('panel-' + name);
  var firstSub = panel ? panel.querySelector('.subtab') : null;
  if (firstSub && firstSub.getAttribute('aria-selected') !== 'true') { firstSub.click(); }
  else { activateCharts(panel); }
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

// ── 行事曆／賽程表：篩選、標出今天、現在時間標示 ─────────────
// 財經行事曆與 F1 賽程共用同一套表格結構，所以逐個 .cal-table 各自初始化。
// 所有跟「現在」有關的東西都在瀏覽器端算，不在產生頁面時寫死 ——
// 頁面會被 CDN 快取，寫死的話隔天再開就會標錯。
function initCalendarTable(table) {
  var days = Array.prototype.slice.call(table.querySelectorAll('.cal-day'));
  var panel = table.closest('.panel');
  var clock = panel ? panel.querySelector('.cal-clock') : null;
  var chips = panel
    ? Array.prototype.slice.call(panel.querySelectorAll('.cal-filter .chip'))
    : [];
  var cols = table.querySelectorAll('thead th').length;
  var minRank = 0;
  var nowRow = null;

  // 台北時間（UTC+8）：不論使用者裝置在哪個時區，顯示都與表格一致
  function taipei() {
    return new Date(Date.now() + (8 * 60 + new Date().getTimezoneOffset()) * 60000);
  }
  function pad(n) { return String(n).padStart(2, '0'); }

  // 以每一列自己的日期判斷，財經行事曆（一天一組）與 F1（一個賽事週末一組）
  // 都適用：只要組裡有今天的場次就標「今天」，整組都過了才算已過去。
  function markDays() {
    var t = taipei();
    var iso = t.getFullYear() + '-' + pad(t.getMonth() + 1) + '-' + pad(t.getDate());
    days.forEach(function (d) {
      // 置頂區塊（SpaceX 的「進行中的任務」）不套今天／已過去 ——
      // 那是現在的狀態，用發射日期判斷會被標成已過去而淡化
      if (d.dataset.pinned) return;
      var rowDays = Array.prototype.slice.call(d.querySelectorAll('.cal-row'))
        .map(function (r) { return r.dataset.day || d.dataset.date; });
      var hasToday = rowDays.indexOf(iso) >= 0;
      var allPast = rowDays.length > 0 && rowDays.every(function (x) { return x < iso; });
      d.classList.toggle('today', hasToday);
      d.classList.toggle('past', allPast);
      // 有分組標題內層時把「今天」掛在標題文字後面，不要掛在 flex 容器外
      var head = d.querySelector('.grp-main') || d.querySelector('.cal-day-row th');
      var tag = head.querySelector('.cal-today-tag');
      if (hasToday && !tag) {
        tag = document.createElement('span');
        tag.className = 'cal-today-tag';
        tag.textContent = '今天';
        head.appendChild(tag);
      } else if (!hasToday && tag) {
        tag.remove();
      }
    });
    return iso;
  }

  function buildNowRow(text) {
    if (!nowRow) {
      nowRow = document.createElement('tr');
      nowRow.className = 'cal-now';
      var td = document.createElement('td');
      td.colSpan = cols;
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

  // 標示線插在「全表第一個還沒到的可見項目」之前。
  // 不綁定今天那一組：F1 是依大獎賽分組，今天不一定有場次。
  function placeNow() {
    var t = taipei();
    var row = buildNowRow(pad(t.getHours()) + ':' + pad(t.getMinutes()));
    var now = Date.now();

    for (var i = 0; i < days.length; i++) {
      if (days[i].hidden || days[i].classList.contains('collapsed')) continue;
      var rows = Array.prototype.slice.call(days[i].querySelectorAll('.cal-row'))
                      .filter(function (r) { return !r.hidden; });
      for (var j = 0; j < rows.length; j++) {
        if (Number(rows[j].dataset.ts) > now) {
          days[i].insertBefore(row, rows[j]);
          return;
        }
      }
    }
    // 全部都過去了就放在最後一組末尾
    var last = days.filter(function (d) { return !d.hidden; }).pop();
    if (last) { last.appendChild(row); } else if (nowRow) { nowRow.remove(); }
  }

  function applyFilter() {
    days.forEach(function (d) {
      var shown = 0;
      Array.prototype.slice.call(d.querySelectorAll('.cal-row')).forEach(function (row) {
        var on = Number(row.dataset.impact) >= minRank;
        row.hidden = !on;
        if (on) shown++;
      });
      d.hidden = (shown === 0);
    });
  }

  function refresh() {
    markDays();
    applyFilter();
    placeNow();
    if (clock) {
      var t = taipei();
      clock.textContent = '現在 ' + (t.getMonth() + 1) + '/' + pad(t.getDate()) + ' ' +
                          pad(t.getHours()) + ':' + pad(t.getMinutes()) + '（UTC+8）';
    }
  }

  chips.forEach(function (c) {
    c.addEventListener('click', function () {
      chips.forEach(function (x) { x.setAttribute('aria-pressed', String(x === c)); });
      minRank = Number(c.dataset.min);
      refresh();
    });
  });

  // ── 可摺疊的分組（F1 賽程用）──────────────────────────
  // 預設只展開「進行中或下一場」那一組，整季 20 幾站才不會一次全部攤開。
  var collapsible = days.filter(function (d) { return d.classList.contains('collapsible'); });
  if (collapsible.length) {
    collapsible.forEach(function (d) {
      var th = d.querySelector('.cal-day-row th');
      function toggle() {
        var open = d.classList.toggle('collapsed') === false;
        th.setAttribute('aria-expanded', String(open));
        placeNow();
        syncSticky();
      }
      th.addEventListener('click', toggle);
      th.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
      });
    });

    var now = Date.now();
    var target = null;
    for (var gi = 0; gi < collapsible.length && !target; gi++) {
      var rs = collapsible[gi].querySelectorAll('.cal-row');
      for (var ri = 0; ri < rs.length; ri++) {
        if (Number(rs[ri].dataset.ts) > now) { target = collapsible[gi]; break; }
      }
    }
    if (!target) target = collapsible[collapsible.length - 1];   // 賽季已結束就開最後一站
    collapsible.forEach(function (d) {
      var open = (d === target);
      d.classList.toggle('collapsed', !open);
      d.querySelector('.cal-day-row th').setAttribute('aria-expanded', String(open));
    });
  }

  refresh();
  setInterval(refresh, 30000);   // 每半分鐘更新時鐘與標示線位置
}

Array.prototype.slice.call(document.querySelectorAll('.cal-table'))
  .forEach(initCalendarTable);

// ── 二階／三階分頁（目前只有 F1 用）─────────────────────────
// 圖表在隱藏的分頁裡量不到寬度，所以顯示的當下才繪製或重新丈量。
function activateCharts(container) {
  if (!container) return;
  Array.prototype.slice.call(container.querySelectorAll('.chart')).forEach(function (div) {
    if (div.offsetParent === null) return;          // 還藏著就先不畫
    var key = div.id.replace('chart-', '');
    var c = CHARTS[key];
    if (!c) return;
    if (!c.rendered || c.dirty) { renderChart(key); }
    else { Plotly.Plots.resize(div); }
  });
}

function setHead(el) {
  if (!el || !el.dataset.title) return;
  document.getElementById('page-title').textContent = el.dataset.title;
  document.getElementById('page-meta').innerHTML = el.dataset.meta || '';
}

function initTabGroup(bar, tabClass, panelClass, dataKey) {
  var scope = bar.parentElement;
  var tabs = Array.prototype.slice.call(bar.querySelectorAll('.' + tabClass));
  var panes = Array.prototype.slice.call(scope.children).filter(function (el) {
    return el.classList.contains(panelClass);
  });
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      tabs.forEach(function (x) { x.setAttribute('aria-selected', String(x === t)); });
      var shown = null;
      panes.forEach(function (p) {
        var on = (p.dataset[dataKey] === t.dataset[dataKey]);
        p.hidden = !on;
        if (on) shown = p;
      });
      setHead(t);
      // 顯示的分頁裡若還有孫分頁，標題以孫分頁為準
      var grand = shown ? shown.querySelector('.grandtab[aria-selected="true"]') : null;
      setHead(grand);
      activateCharts(shown);
      syncSticky();   // 內容換了，黏著層高度要重量
    });
  });
}

Array.prototype.slice.call(document.querySelectorAll('.subtabs')).forEach(function (bar) {
  initTabGroup(bar, 'subtab', 'subpanel', 'sub');
});
Array.prototype.slice.call(document.querySelectorAll('.grandtabs')).forEach(function (bar) {
  initTabGroup(bar, 'grandtab', 'grandpanel', 'grand');
});

// ── 新聞：點標題看內文，返回鍵回清單 ───────────────────────
// 清單與內文都是產生頁面時就寫好的靜態內容，切換只是顯示／隱藏。
var FIRST_BATCH = 12;   // 一開始排幾則
var BATCH = 10;         // 捲到底再接幾則
Array.prototype.slice.call(document.querySelectorAll('.subpanel')).forEach(function (panel) {
  var list = panel.querySelector('.news-list');
  if (!list) return;
  var articles = Array.prototype.slice.call(panel.querySelectorAll('.news-article'));

  function show(key) {
    list.hidden = (key !== null);
    // 「載入更多」在 ul 外面，看內文時要一起藏
    if (sentinel) sentinel.hidden = (key !== null) || (shown >= items.length);
    articles.forEach(function (a) { a.hidden = (a.dataset.article !== key); });
    window.scrollTo(0, 0);
    syncSticky();
  }

  var items = Array.prototype.slice.call(list.querySelectorAll('.news-item'));
  items.forEach(function (li) {
    function open() { show(li.dataset.article); }
    li.addEventListener('click', open);
    li.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    });
  });

  // 捲到底自動接上後面的：全部都已經在頁面裡，只是先藏起來，
  // 一次全顯示會讓清單長到難捲，也沒必要一開始就排版那麼多列。
  var shown = FIRST_BATCH;
  var sentinel = panel.querySelector('.news-more');
  function reveal() {
    items.forEach(function (li, i) { li.hidden = (i >= shown); });
    if (sentinel) sentinel.hidden = (shown >= items.length);
  }
  function extend() {
    if (shown >= items.length) return;
    shown = Math.min(shown + BATCH, items.length);
    reveal();
  }
  reveal();
  if (sentinel) {
    if (window.IntersectionObserver) {
      new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting) extend();
      }, {rootMargin: '200px'}).observe(sentinel);
    }
    sentinel.addEventListener('click', extend);   // 沒有 IO 時仍可手動載入
  }

  articles.forEach(function (a) {
    a.querySelector('.news-back').addEventListener('click', function () { show(null); });
  });

  // 切走再回來時回到清單，不要停在上次看的那一篇
  var subtab = document.querySelector('.subtab[data-sub="' + panel.dataset.sub + '"]');
  if (subtab) subtab.addEventListener('click', function () { show(null); });
});

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


def _chart_entry(key: str, fig_light, fig_dark, item_label: str) -> dict:
    """把一張圖包成前端要的格式（只嵌一份 traces + 兩份 layout）。"""
    light = json.loads(pio.to_json(fig_light))
    darkj = json.loads(pio.to_json(fig_dark))

    # 只嵌入一份 traces 的前提是兩個主題的線條完全相同。
    # plotly_dark 目前與 plotly 共用同一組 colorway，但若哪天不再成立，
    # 這裡要立刻發現，而不是默默送出配色錯誤的頁面。
    if light["data"] != darkj["data"]:
        raise RuntimeError(
            f"{key}：淺色與深色的 traces 不一致，不能只嵌入一份。"
            "請改回各嵌一份，或找出差異來源。"
        )

    return {
        "traces": light["data"],
        "layout": {"light": light["layout"], "dark": darkj["layout"]},
        "series": series_colors(fig_light),
        "itemLabel": item_label,
    }


def build() -> Path:
    """讀各資料集、產生 docs/index.html，回傳輸出路徑。"""
    charts = {}
    stats = {}
    head = {}

    panel_data = {}

    for p in PANELS:
        if p.get("kind", "chart") == "calendar":
            panel_data[p["id"]] = p["load"]()
            stats[p["id"]] = p["stats"](panel_data[p["id"]])
            head[p["id"]] = {
                "title": p["title"],
                "meta": f'{p["meta"]}<br>最後更新日：{stats[p["id"]]["latest"]}',
            }
            continue

        df = p["load"]()
        fig_light = p["figure"](df, dark=False, showlegend=False)
        fig_dark = p["figure"](df, dark=True, showlegend=False)

        charts[p["id"]] = _chart_entry(p["id"], fig_light, fig_dark, p["item_label"])
        stats[p["id"]] = _stats(p)
        head[p["id"]] = {
            "title": p["title"],
            "meta": f'{p["meta"]}<br>最後更新日：{stats[p["id"]]["latest"]}',
        }

    # 嵌在 F1 積分子分頁裡的兩張走勢圖
    series = load_points_series()
    for extra in EXTRA_CHARTS:
        part = series[series["kind"] == extra["kind"]] if not series.empty else series
        charts[extra["key"]] = _chart_entry(
            extra["key"],
            build_points_figure(part, dark=False, showlegend=False),
            build_points_figure(part, dark=True, showlegend=False),
            extra["item_label"],
        )

    head["settings"] = {"title": "設定", "meta": "外觀、資料集資訊與版本"}

    built = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M (UTC+8)")
    first = PANELS[0]

    html = (
        TPL.replace("__CHART_PANELS__", _panels_html(panel_data))
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
