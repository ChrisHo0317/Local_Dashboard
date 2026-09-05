"""
產生 GitHub Pages 用的靜態頁面 docs/index.html

沒有伺服器端 callback，改把圖表資料內嵌進頁面，由前端 Plotly.react 繪製。
hover、框選縮放、時間軸縮圖等 Plotly 原生互動全部保留。

版面由底部懸浮式標籤列切換（切換時指示器會滑動）：
  DRAM    DRAM 現貨報價（TrendForce）
  美債    美國公債各年期殖利率（MoneyDJ）
  黃金    國際金價（Yahoo Finance）
  行事曆  財經事件行事曆（FXStreet）
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
from news_render import (bodies as news_bodies, panel_html as news_panel_html,
                         stats as news_stats)
from notes_render import (META as NOTES_META, panel_html as notes_panel_html,
                          stats as notes_stats)
from stock_data import CSV_PATHS as STOCK_CSVS, load_all as load_stock_all
from stock_render import (META as STOCK_META, datasets as stock_datasets,
                          panel_html as stock_panel_html, stats as stock_stats)
from spacex_data import CSV_PATH as SPACEX_CSV, load_all as load_spacex_all
from spacex_render import panel_html as spacex_panel_html, stats as spacex_stats
from version import __version__

DOCS_DIR = BASE_DIR / "docs"
OUTPUT = DOCS_DIR / "index.html"
NEWS_DIR = DOCS_DIR / "news"
STOCK_DIR = DOCS_DIR / "stock"

# 圖表分頁定義。新增一組資料只要在這裡加一筆。
PANELS = [
    {
        "id": "dram",
        "group": "finance",
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
        "group": "finance",
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
        "group": "finance",
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
        "group": "finance",
        "kind": "calendar",
        "tab": "行事曆",
        "title": "財經行事曆",
        "meta": "資料來源：FXStreet　·　本月與下月，中／高影響　·　時間為台北時間（UTC+8）",
        "source_name": "FXStreet",
        "source_url": "https://www.fxstreet.com/economic-calendar",
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
        "group": "personal",
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
        "group": "finance",
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
        "group": "finance",
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
    {
        "id": "stock",
        "group": "finance",
        "kind": "calendar",
        "tab": "個股",
        "title": "個股",
        "meta": STOCK_META,
        "source_name": "臺灣證券交易所",
        "source_url": "https://mops.twse.com.tw/mops/#/web/home",
        "csv": STOCK_CSVS["revenue"],
        "load": load_stock_all,
        "render": stock_panel_html,
        "stats": stock_stats,
        # 放大鏡加一段走勢
        "icon": '<circle cx="10.5" cy="10.5" r="6.5"/>'
                '<line x1="15.4" y1="15.4" x2="20.5" y2="20.5"/>'
                '<polyline points="7.6 12.2 9.6 9.6 11.6 11.2 13.6 8"/>',
    },
    {
        "id": "notes",
        "group": "personal",
        "kind": "calendar",
        "tab": "筆記",
        "title": "筆記",
        "meta": NOTES_META,
        "source_name": "本機瀏覽器",
        "source_url": "",
        "csv": None,
        "load": lambda: {},
        "render": notes_panel_html,
        "stats": notes_stats,
        # 筆記本與筆的圖示
        "icon": '<path d="M6 3.5h9l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 19V5A1.5 1.5 0 0 1 6.5 3.5z"/>'
                '<polyline points="14.5 3.8 14.5 8 18.8 8"/>'
                '<line x1="8.5" y1="12" x2="15" y2="12"/>'
                '<line x1="8.5" y1="15.5" x2="13" y2="15.5"/>',
    },
]

# 內建分組：使用者還沒自訂時的預設值。底部標籤列一次只顯示一組，
# 「設定」不屬於任何一組，永遠在。分組與歸屬都可以在設定裡改，
# 改完存在瀏覽器（localStorage），所以這裡只是出廠設定。
GROUPS = [
    {"id": "finance", "label": "財經"},
    {"id": "personal", "label": "個人追蹤"},
]


def _default_groups() -> list:
    """把 PANELS 的 group 欄位攤成「分組 → 分頁清單」給前端當預設值。"""
    return [
        {"id": g["id"], "label": g["label"],
         "tabs": [p["id"] for p in PANELS if p.get("group") == g["id"]]}
        for g in GROUPS
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


def _tab_button(tab_id: str, label: str, icon: str, selected: bool,
                group: str = "all") -> str:
    return (
        f'    <button class="tab" type="button" role="tab" data-tab="{tab_id}"\n'
        f'            data-group="{group}"'
        f' aria-selected="{"true" if selected else "false"}"'
        f' aria-controls="panel-{tab_id}">\n'
        f'      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"\n'
        f'           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{icon}</svg>\n'
        f'      <span>{label}</span>\n'
        f'    </button>'
    )


def _tabbar_html() -> str:
    btns = [_tab_button(p["id"], p["tab"], p["icon"], i == 0, p.get("group", "all"))
            for i, p in enumerate(PANELS)]
    btns.append(_tab_button("settings", "設定", SETTINGS_ICON, False))
    return ('<nav class="tabbar" role="tablist" aria-label="主要分頁">\n'
            '    <span class="tab-pill" id="tab-pill" aria-hidden="true"></span>\n'
            + "\n".join(btns) + "\n  </nav>")


def _groupbar_html() -> str:
    # 按鈕由 JS 依使用者的分組設定產生，這裡只留外框與滑動指示器
    return ('<nav class="groupbar" id="groupbar" role="tablist" aria-label="分類">\n'
            '    <span class="grp-pill" id="grp-pill" aria-hidden="true"></span>\n'
            '  </nav>')


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
        if s.get("local"):
            # 筆記存在讀者自己的瀏覽器，建置時沒有任何數字可寫；
            # 筆數由頁面上的 JS 讀完 localStorage 後補上。
            cards.append(f'''    <div class="card fold" data-card="{p["id"]}">
      <div class="card-h">
        <button type="button" class="card-t" aria-expanded="false"
                aria-controls="cardbody-{p["id"]}">
          <span class="card-chev">&#9656;</span><span>{p["title"]}</span>
        </button>
        <button class="switch sw-sm" type="button" role="switch" data-panel="{p["id"]}"
                aria-checked="true" aria-label="顯示{p["tab"]}分頁"><span class="knob"></span></button>
      </div>
      <div class="card-body" id="cardbody-{p["id"]}">
      <div class="row"><span>筆記則數</span><b id="notes-count">—</b></div>
      <div class="row"><span>儲存位置</span><b>{s["range"]}</b></div>
      <div class="row"><span>同步</span><b>不會上傳，換裝置看不到</b></div>
      </div>
    </div>''')
            continue
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
        cards.append(f'''    <div class="card fold" data-card="{p["id"]}">
      <div class="card-h">
        <button type="button" class="card-t" aria-expanded="false"
                aria-controls="cardbody-{p["id"]}">
          <span class="card-chev">&#9656;</span><span>{p["title"]}　資料</span>
        </button>
        <button class="switch sw-sm" type="button" role="switch" data-panel="{p["id"]}"
                aria-checked="true" aria-label="顯示{p["tab"]}分頁"><span class="knob"></span></button>
      </div>
      <div class="card-body" id="cardbody-{p["id"]}">
      <div class="row"><span>最後更新日</span><b>{s["latest"]}</b></div>
{middle}
      <div class="row"><span>涵蓋區間</span><b>{s["range"]}</b></div>
      <div class="row"><span>資料來源</span>
        <a href="{p["source_url"]}" target="_blank" rel="noopener">{p["source_name"]}</a></div>
      </div>
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
    --pill:rgba(0,0,0,.075); --tab-fg:#6c757d; --accent:#1f9d6b; --danger:#c9453f;
  }
  html[data-theme="dark"] {
    --bg:#1e2130; --fg:#e8e8e8; --muted:#9aa0ac; --border:#333849; --hover:rgba(255,255,255,.07);
    --card:#242839; --bar-bg:rgba(42,47,69,.80); --bar-border:rgba(255,255,255,.10);
    --pill:rgba(255,255,255,.13); --tab-fg:#9aa0ac; --accent:#4dd4ac; --danger:#ff8a80;
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
  /* 看內文時標題列左邊出現返回鍵；標題列本身是 sticky，捲到哪都按得到 */
  .head-left { display:flex; gap:8px; align-items:flex-start; min-width:0; }
  .backbtn { flex:none; margin:-4px 0 0 -6px; padding:4px 6px; border-radius:8px;
             color:var(--muted); border-color:transparent; background:transparent; }
  .backbtn:hover { color:var(--fg); }
  .backbtn svg { width:22px; height:22px; display:block; }
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
  /* 可摺疊的資料卡片：八張全攤開的話設定頁要捲很久 */
  .card-t { display:flex; align-items:center; gap:7px; flex:1; min-width:0;
            padding:0; border:0; background:none; color:inherit; font:inherit;
            letter-spacing:inherit; text-align:left; cursor:pointer;
            -webkit-tap-highlight-color:transparent; }
  .card-chev { font-size:11px; transition:transform .15s; flex:none; }
  .card-t[aria-expanded="true"] .card-chev { transform:rotate(90deg); }
  .card.fold .card-body { display:none; }
  .card.fold.open .card-body { display:block; }

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
  .grp-chev { font-size:15px; color:var(--muted); flex:none; }
  /* 可鑽入的分組（F1）：清單模式只列大獎賽，點標題列才進到那一站 */
  .cal-table.list-mode thead,
  .cal-table.list-mode .cal-row,
  .cal-table.list-mode .cal-now { display:none; }
  .cal-table.list-mode .cal-day.drill .cal-day-row th {
    cursor:pointer; user-select:none; -webkit-tap-highlight-color:transparent;
    position:static; padding:13px 4px; }
  .cal-table.list-mode .cal-day.drill .cal-day-row th:hover { background:var(--hover); }
  .cal-table.list-mode .grp-main { font-size:14px; }
  .cal-table.list-mode .grp-sub { font-size:12px; }
  /* 進到某一站之後大獎賽名稱已經在頁面標頭上，表格裡就不用再寫一次 */
  .cal-table:not(.list-mode) .cal-day.drill .cal-day-row { display:none; }
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

  /* 分類切換：底部標籤列一次只顯示一組分頁 */
  .groupbar { position:relative; display:flex; gap:4px; margin:0 0 16px;
              padding:4px; border-radius:999px; background:var(--pill); width:max-content; }
  .grp { position:relative; z-index:1; font-size:13px; font-weight:600; min-width:74px;
         padding:6px 16px; border-radius:999px; color:var(--muted); border-color:transparent;
         background:transparent; }
  .grp[aria-selected="true"] { color:var(--fg); }
  .grp-pill { position:absolute; top:4px; bottom:4px; left:0; width:0; border-radius:999px;
              background:var(--bg); box-shadow:0 1px 3px rgba(0,0,0,.12);
              transition:transform .22s cubic-bezier(.4,0,.2,1), width .22s cubic-bezier(.4,0,.2,1); }
  .grp-pill.no-anim { transition:none; }

  /* 設定裡的分類編輯器 */
  .ge-group { margin-top:12px; }
  .ge-group:first-child { margin-top:4px; }
  .ge-head { display:flex; align-items:center; justify-content:space-between;
             gap:10px; padding:4px 0 6px; }
  .ge-name { font-size:13px; font-weight:600; }
  .ge-acts { display:flex; gap:6px; flex:none; }
  .ge-btn { font-size:12px; padding:4px 10px; border-radius:8px; color:var(--muted); }
  .ge-btn:hover { color:var(--fg); }
  .ge-del:hover { color:var(--danger); border-color:var(--danger); }
  .ge-list { min-height:38px; border-radius:10px; background:var(--hover); padding:4px; }
  .ge-item { display:flex; align-items:center; gap:6px; padding:9px 8px;
             border-radius:8px; background:var(--bg); margin:4px 0;
             -webkit-tap-highlight-color:transparent; }
  /* 把手要 touch-action:none，拖曳中的 pointermove 才會持續送到我們手上；
     其餘區域維持預設，手指落在列上仍然可以正常捲頁面 */
  .ge-handle { flex:none; color:var(--muted); font-size:16px; cursor:grab;
               padding:2px 8px; margin:-2px 0; touch-action:none; }
  .ge-label { font-size:13px; }
  .ge-empty { margin:6px 4px; font-size:12px; color:var(--muted); }
  .ge-dragging { opacity:.35; }
  /* 跟著手指走的那一份 */
  .ge-ghost { position:fixed; z-index:90; pointer-events:none; margin:0;
              box-shadow:0 6px 20px rgba(0,0,0,.22); }
  body.ge-nosel { user-select:none; -webkit-user-select:none; }
  .ge-add { width:100%; margin-top:14px; padding:10px; border-radius:10px;
            font-size:13px; color:var(--accent); border-style:dashed; }

  /* 個股：查詢框、建議、指標、清單 */
  .sq-box { position:relative; margin-bottom:12px; }
  /* 輸入框一律 16px：iOS Safari 遇到比 16px 小的欄位，一聚焦就會
     自動把整頁放大，之後還得自己縮回來 */
  .sq-input, .sl-filter { width:100%; padding:10px 12px; border-radius:10px;
                          font-size:16px; background:var(--bg); color:var(--fg);
                          border:1px solid var(--border); font-family:inherit; }
  .sq-input:focus, .sl-filter:focus { outline:none; border-color:var(--accent); }
  .sq-suggest { position:absolute; z-index:20; left:0; right:0; top:calc(100% + 4px);
                background:var(--card); border:1px solid var(--border);
                border-radius:10px; overflow:hidden; box-shadow:0 6px 20px rgba(0,0,0,.14); }
  .sq-opt { display:block; width:100%; text-align:left; padding:10px 12px;
            font-size:14px; border:0; border-radius:0; background:none; color:var(--fg); }
  .sq-opt:hover { background:var(--hover); }
  .sq-range { display:flex; gap:6px; margin-bottom:12px; }
  .sq-hint { color:var(--muted); font-size:13px; padding:14px 2px; }
  .sq-name { font-size:16px; font-weight:600; margin-bottom:10px; }
  .sq-stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(104px, 1fr));
              gap:8px; margin-bottom:6px; }
  .sq-stat { padding:8px 10px; border-radius:10px; background:var(--hover); }
  .sq-stat-l { display:block; font-size:11px; color:var(--muted); }
  .sq-stat b { font-size:15px; font-variant-numeric:tabular-nums; }
  /* 保險：就算 Plotly 又量錯寬度，也不要把整頁撐寬 */
  .sq-chart { min-height:300px; max-width:100%; overflow:hidden; }
  .sq-chart .svg-container, .sq-chart svg { max-width:100%; }

  /* 鎖定某一檔時的提示晶片 */
  .sl-focus { display:flex; align-items:center; justify-content:space-between;
              gap:10px; margin-bottom:12px; padding:8px 10px 8px 14px;
              border-radius:999px; background:var(--pill); font-size:13px; }
  .sl-clear { flex:none; padding:2px 8px; border-radius:999px; font-size:13px;
              color:var(--muted); border-color:transparent; background:transparent; }
  .sl-clear:hover { color:var(--fg); }

  .sl-item { padding:12px 2px; box-shadow:inset 0 -1px 0 var(--border); }
  .sl-click { cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .sl-click:hover { background:var(--hover); }
  .sl-head { display:block; margin-bottom:8px; }
  .sl-title { display:block; font-size:14px; line-height:1.5; }
  .sl-sub { display:block; font-size:11px; color:var(--muted); margin-top:3px; }
  .sl-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; }
  .sl-cell { font-size:11px; color:var(--muted); }
  .sl-v { display:block; font-size:14px; color:var(--fg); font-weight:500;
          font-variant-numeric:tabular-nums; }
  .sl-v.up { color:#e8590c; }
  .sl-v.down { color:#1f9d6b; }

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
  /* 重點清單：標題下多一句摘要，時間後面掛主題標籤 */
  .dg-item .news-title { font-weight:500; }
  .dg-sum { display:block; font-size:12px; line-height:1.6; color:var(--muted);
            margin-top:5px; }
  .dg-tag { display:inline-block; margin-left:6px; padding:1px 7px; border-radius:999px;
            background:var(--pill); color:var(--muted); font-size:10px; }
  .news-h { font-size:18px; line-height:1.45; margin:0 0 6px; font-weight:600; }
  .news-body { margin-top:14px; }
  .news-body p { font-size:15px; line-height:1.8; margin:0 0 14px; }
  .news-nobody { color:var(--muted); font-size:13px; }
  .news-link { display:inline-block; margin-top:4px; font-size:13px; color:var(--accent); }
  .news-more { display:block; width:100%; margin-top:14px; padding:12px;
               font-size:13px; color:var(--muted); border-radius:10px; }

  /* 筆記：清單與編輯 */
  .notes-item { display:block; width:100%; text-align:left; padding:12px 2px;
                box-shadow:inset 0 -1px 0 var(--border); border-color:transparent;
                border-radius:0; -webkit-tap-highlight-color:transparent; }
  .notes-item:hover { background:var(--hover); }
  .notes-t { display:block; font-size:15px; line-height:1.5; }
  .notes-sub { display:block; font-size:11px; color:var(--muted); margin-top:3px;
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .notes-empty { color:var(--muted); font-size:13px; padding:18px 2px; }
  .notes-new { width:100%; margin-top:14px; padding:12px; border-radius:10px;
               font-size:14px; color:var(--accent); border-style:dashed; }
  .notes-title { width:100%; font-size:18px; font-weight:600; padding:8px 10px;
                 border-radius:10px; background:var(--bg); color:var(--fg);
                 border:1px solid var(--border); }
  .notes-body { width:100%; margin-top:10px; padding:10px; border-radius:10px;
                font-size:16px; line-height:1.75; resize:vertical;
                background:var(--bg); color:var(--fg); border:1px solid var(--border);
                font-family:inherit; }
  .notes-title:focus, .notes-body:focus { outline:none; border-color:var(--accent); }
  .notes-foot { display:flex; align-items:center; justify-content:space-between;
                gap:12px; margin-top:12px; }
  .notes-saved { font-size:12px; color:var(--muted); }
  .notes-del { font-size:13px; padding:7px 14px; border-radius:8px; color:var(--danger); }
  .notes-del:hover { border-color:var(--danger); }

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
    <div class="head-left">
      <button id="back" class="backbtn" type="button" aria-label="返回列表" hidden>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
      </button>
      <div>
        <h1 id="page-title">__TITLE0__</h1>
        <div class="meta" id="page-meta">__META0__</div>
      </div>
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

  __GROUPBAR__

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

    <div class="card">
      <div class="card-h">分類</div>
      <p class="note">長按 ≡ 可以把分頁拖到別的分組，或調整組內順序。</p>
      <div id="group-editor"></div>
      <button type="button" class="ge-add" id="group-add">＋ 新增分組</button>
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
const DEFAULT_GROUPS = __GROUPS__; // 出廠的分組與歸屬（使用者可在設定裡改）
const TAB_LABELS = __TAB_LABELS__; // 分頁 id → 標籤文字
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
  // 個股查詢的圖不在 CHARTS 裡（資料是當場查來的），它自己重畫
  window.dispatchEvent(new Event('dash-theme'));
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

// ── 標題列的返回鍵 ─────────────────────────────────────────
// 分頁內部有「進到某一則」的檢視時（新聞內文、筆記編輯）登記回去的動作，
// 按鍵就跟著標題一起釘在畫面上方，捲到內文中段也按得到。
var backBtn = document.getElementById('back');
var backAction = null;

function setBack(fn) {
  backAction = fn;
  backBtn.hidden = !fn;
  syncSticky();
}

backBtn.addEventListener('click', function () { if (backAction) backAction(); });

// 右滑等於按返回鍵 —— 只在有東西可返回時才理會。
(function () {
  var SWIPE = 70;        // 至少要滑這麼多 px 才算
  var IN_FIELD = 130;    // 起點在輸入框裡就要滑更長 —— 那裡也可能是在移游標
  var SLOPE = 1.6;       // 橫向位移要明顯大於縱向，避免捲動時誤觸
  var LIMIT = 700;       // 超過這個時間就當成慢慢拖，不是滑動手勢
  var x0 = 0, y0 = 0, t0 = 0, tracking = false, inField = false;

  // 起點在會橫向捲動的東西上（標籤列、子分頁列）就讓它自己捲
  function scrollsX(node) {
    while (node && node !== document.body) {
      if (node.scrollWidth > node.clientWidth + 4) {
        var ov = getComputedStyle(node).overflowX;
        if (ov === 'auto' || ov === 'scroll') return true;
      }
      node = node.parentElement;
    }
    return false;
  }

  document.addEventListener('touchstart', function (e) {
    tracking = false;
    if (!backAction || e.touches.length !== 1) return;
    var el = e.target;
    if (scrollsX(el)) return;
    // 筆記編輯時畫面中央整片都是輸入框，完全不理會等於滑不動；
    // 改成一樣可以滑，但門檻拉高，才不會跟移游標混在一起
    inField = !!(el.closest && el.closest('input, textarea, select'));
    x0 = e.touches[0].clientX;
    y0 = e.touches[0].clientY;
    t0 = Date.now();
    tracking = true;
  }, {passive: true});

  document.addEventListener('touchend', function (e) {
    if (!tracking) return;
    tracking = false;
    if (!backAction || Date.now() - t0 > LIMIT) return;
    var t = e.changedTouches[0];
    var dx = t.clientX - x0;
    var dy = t.clientY - y0;
    if (dx > (inField ? IN_FIELD : SWIPE) && dx > Math.abs(dy) * SLOPE) backAction();
  }, {passive: true});
})();

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
  setBack(null);            // 換分頁就離開內文檢視
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

// ── 分類 ───────────────────────────────────────────────────
// 底部標籤列一次只顯示一組分頁；「設定」的 data-group 是 all，永遠在。
// 分組與歸屬都可以在設定裡改，存在 localStorage，所以分類列的按鈕
// 是依設定產生的，不是產生頁面時寫死的。
var GROUP_KEY = 'dash-groups';
var groupBar = document.getElementById('groupbar');
var grpPill = document.getElementById('grp-pill');
var groups = loadGroups();
var curGroup = groups.length ? groups[0].id : 'all';

function loadGroups() {
  var saved = null;
  try { saved = JSON.parse(localStorage.getItem(GROUP_KEY)); } catch (e) { saved = null; }
  var list = (saved && Array.isArray(saved.groups)) ? saved.groups : null;
  if (!list) list = JSON.parse(JSON.stringify(DEFAULT_GROUPS));

  // 只留下真的存在的分頁，並確保每個分頁都有歸屬 ——
  // 改版新增分頁時，舊的設定裡不會有它，沒有這段就會憑空消失。
  var seen = {};
  list = list.filter(function (g) { return g && g.id && Array.isArray(g.tabs); });
  list.forEach(function (g) {
    g.tabs = g.tabs.filter(function (id) {
      if (PANEL_IDS.indexOf(id) < 0 || seen[id]) return false;
      seen[id] = true;
      return true;
    });
  });
  if (!list.length) list = JSON.parse(JSON.stringify(DEFAULT_GROUPS));
  PANEL_IDS.forEach(function (id) {
    if (seen[id]) return;
    var home = DEFAULT_GROUPS.filter(function (d) { return d.tabs.indexOf(id) >= 0; })[0];
    var target = home && list.filter(function (g) { return g.id === home.id; })[0];
    (target || list[0]).tabs.push(id);
  });
  return list;
}

function saveGroups() {
  try { localStorage.setItem(GROUP_KEY, JSON.stringify({v: 1, groups: groups})); }
  catch (e) { /* 隱私模式：這次改動有效，下次開就回到預設 */ }
}

function groupOf(id) {
  for (var i = 0; i < groups.length; i++) {
    if (groups[i].tabs.indexOf(id) >= 0) return groups[i].id;
  }
  return null;
}

function inGroup(tab) {
  return tab.dataset.group === 'all' || groupOf(tab.dataset.tab) === curGroup;
}

// 依設定重畫分類列。只有一組時整列就沒有意義，直接不顯示。
function renderGroupBar() {
  Array.prototype.slice.call(groupBar.querySelectorAll('.grp'))
    .forEach(function (b) { b.remove(); });
  groupBar.hidden = groups.length < 2;
  groups.forEach(function (g) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'grp';
    b.dataset.group = g.id;
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-selected', String(g.id === curGroup));
    b.textContent = g.label;
    b.addEventListener('click', function () { selectGroup(g.id, true); });
    groupBar.appendChild(b);
  });
}

function selectGroup(name, animate) {
  if (!groups.filter(function (g) { return g.id === name; }).length) {
    name = groups.length ? groups[0].id : 'all';
  }
  curGroup = name;
  Array.prototype.slice.call(groupBar.querySelectorAll('.grp')).forEach(function (g) {
    var on = g.dataset.group === name;
    g.setAttribute('aria-selected', String(on));
    if (on) {
      if (!animate) grpPill.classList.add('no-anim');
      grpPill.style.width = g.offsetWidth + 'px';
      grpPill.style.transform = 'translateX(' + g.offsetLeft + 'px)';
      if (!animate) { void grpPill.offsetWidth; grpPill.classList.remove('no-anim'); }
    }
  });
  grpPill.hidden = groupBar.hidden;
  applyVisibility(true);      // 換組後標籤列的內容變了，可能要換分頁
}

// ── 設定裡的資料卡片：可摺疊 ───────────────────────────────
// 預設全部收起（八張攤開要捲很久），展開哪幾張記在 localStorage。
(function () {
  var KEY = 'dash-cards-open';
  var open = {};
  try { open = JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { open = {}; }

  Array.prototype.slice.call(document.querySelectorAll('.card.fold')).forEach(function (card) {
    var id = card.dataset.card;
    var btn = card.querySelector('.card-t');
    function apply(on) {
      card.classList.toggle('open', on);
      btn.setAttribute('aria-expanded', String(on));
    }
    apply(open[id] === true);
    btn.addEventListener('click', function () {
      var on = !card.classList.contains('open');
      apply(on);
      open[id] = on;
      try { localStorage.setItem(KEY, JSON.stringify(open)); } catch (e) { /* 隱私模式 */ }
    });
  });
})();

// ── 設定裡的分類編輯器 ─────────────────────────────────────
// 分組可以新增、改名、刪除；分頁用長按拖曳換組或調順序。
// 觸控裝置沒有 HTML5 的拖放，所以用 pointer 事件自己做：長按才啟動，
// 不然在清單上滑動會變成拖東西而不是捲頁面。
(function () {
  var box = document.getElementById('group-editor');
  if (!box) return;
  var addBtn = document.getElementById('group-add');
  var HOLD = 250;          // 按住這麼久才進入拖曳
  var MOVE_CANCEL = 8;     // 還沒進入拖曳就移動超過這個距離 = 想捲頁面

  function newId() {
    return 'g' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  }

  function commit() {
    saveGroups();
    render();
    renderGroupBar();
    selectGroup(curGroup, false);
  }

  function render() {
    box.textContent = '';
    groups.forEach(function (g, gi) {
      var sec = document.createElement('div');
      sec.className = 'ge-group';
      sec.dataset.group = g.id;

      var head = document.createElement('div');
      head.className = 'ge-head';
      var name = document.createElement('span');
      name.className = 'ge-name';
      name.textContent = g.label;
      head.appendChild(name);

      var acts = document.createElement('span');
      acts.className = 'ge-acts';
      var ren = document.createElement('button');
      ren.type = 'button';
      ren.className = 'ge-btn';
      ren.textContent = '改名';
      ren.addEventListener('click', function () {
        var v = window.prompt('分組名稱', g.label);
        if (v === null) return;
        v = v.trim();
        if (!v) return;
        g.label = v.slice(0, 12);
        commit();
      });
      acts.appendChild(ren);

      if (groups.length > 1) {
        var del = document.createElement('button');
        del.type = 'button';
        del.className = 'ge-btn ge-del';
        del.textContent = '刪除';
        del.addEventListener('click', function () {
          var moved = g.tabs.length;
          if (!window.confirm('刪除分組「' + g.label + '」？' +
              (moved ? '裡面的 ' + moved + ' 個分頁會移到第一個分組。' : ''))) return;
          groups = groups.filter(function (x) { return x !== g; });
          if (moved) groups[0].tabs = groups[0].tabs.concat(g.tabs);
          if (curGroup === g.id) curGroup = groups[0].id;
          commit();
        });
        acts.appendChild(del);
      }
      head.appendChild(acts);
      sec.appendChild(head);

      var list = document.createElement('div');
      list.className = 'ge-list';
      list.dataset.group = g.id;
      if (!g.tabs.length) {
        var empty = document.createElement('p');
        empty.className = 'ge-empty';
        empty.textContent = '這一組還沒有分頁，拖一個過來。';
        list.appendChild(empty);
      }
      g.tabs.forEach(function (id) {
        var row = document.createElement('div');
        row.className = 'ge-item';
        row.dataset.tab = id;
        var handle = document.createElement('span');
        handle.className = 'ge-handle';
        handle.textContent = '≡';
        handle.setAttribute('aria-hidden', 'true');
        var label = document.createElement('span');
        label.className = 'ge-label';
        label.textContent = TAB_LABELS[id] || id;
        row.appendChild(handle);
        row.appendChild(label);
        // 只有把手能拖：整列都能拖的話，手指落在列上想捲頁面會變成拖東西
        handle.addEventListener('pointerdown', function (e) { press(e, row, id); });
        list.appendChild(row);
      });
      sec.appendChild(list);
      box.appendChild(sec);
    });
  }

  // ── 長按拖曳 ────────────────────────────────────────────
  var drag = null;

  function press(e, row, id) {
    if (e.button != null && e.button !== 0) return;
    var startX = e.clientX, startY = e.clientY;
    var timer = setTimeout(function () { begin(row, id, startX, startY); }, HOLD);

    function moveBefore(ev) {
      if (drag) return;
      if (Math.abs(ev.clientX - startX) > MOVE_CANCEL ||
          Math.abs(ev.clientY - startY) > MOVE_CANCEL) cleanup();
    }
    function cleanup() {
      clearTimeout(timer);
      document.removeEventListener('pointermove', moveBefore);
      document.removeEventListener('pointerup', cleanup);
      document.removeEventListener('pointercancel', cleanup);
    }
    document.addEventListener('pointermove', moveBefore);
    document.addEventListener('pointerup', cleanup);
    document.addEventListener('pointercancel', cleanup);
  }

  function begin(row, id, x, y) {
    var rect = row.getBoundingClientRect();
    var ghost = row.cloneNode(true);
    ghost.className = 'ge-item ge-ghost';
    ghost.style.width = rect.width + 'px';
    ghost.style.left = rect.left + 'px';
    ghost.style.top = rect.top + 'px';
    document.body.appendChild(ghost);
    row.classList.add('ge-dragging');
    document.body.classList.add('ge-nosel');
    drag = {row: row, id: id, ghost: ghost,
            dx: x - rect.left, dy: y - rect.top};
    if (navigator.vibrate) { try { navigator.vibrate(10); } catch (e) {} }
    document.addEventListener('pointermove', onMove);
    document.addEventListener('pointerup', onDrop);
    document.addEventListener('pointercancel', onDrop);
  }

  function onMove(e) {
    if (!drag) return;
    e.preventDefault();
    drag.ghost.style.left = (e.clientX - drag.dx) + 'px';
    drag.ghost.style.top = (e.clientY - drag.dy) + 'px';

    // 找出手指底下的那一組，以及要插在哪一列之前
    var lists = Array.prototype.slice.call(box.querySelectorAll('.ge-list'));
    var target = null;
    lists.forEach(function (l) {
      var r = l.getBoundingClientRect();
      if (e.clientY >= r.top - 8 && e.clientY <= r.bottom + 8) target = l;
    });
    if (!target) return;
    var after = null;
    Array.prototype.slice.call(target.querySelectorAll('.ge-item')).forEach(function (it) {
      if (it === drag.row) return;
      var r = it.getBoundingClientRect();
      if (e.clientY > r.top + r.height / 2) after = it;
    });
    var empty = target.querySelector('.ge-empty');
    if (empty) empty.remove();
    if (after) target.insertBefore(drag.row, after.nextSibling);
    else target.insertBefore(drag.row, target.firstChild);
  }

  function onDrop() {
    if (!drag) return;
    document.removeEventListener('pointermove', onMove);
    document.removeEventListener('pointerup', onDrop);
    document.removeEventListener('pointercancel', onDrop);
    drag.ghost.remove();
    drag.row.classList.remove('ge-dragging');
    document.body.classList.remove('ge-nosel');
    drag = null;

    // 以畫面上的實際排列為準寫回設定
    groups.forEach(function (g) {
      var list = box.querySelector('.ge-list[data-group="' + g.id + '"]');
      if (!list) return;
      g.tabs = Array.prototype.slice.call(list.querySelectorAll('.ge-item'))
        .map(function (it) { return it.dataset.tab; });
    });
    commit();
  }

  addBtn.addEventListener('click', function () {
    var v = window.prompt('新分組的名稱', '新分組');
    if (v === null) return;
    v = v.trim();
    if (!v) return;
    groups.push({id: newId(), label: v.slice(0, 12), tabs: []});
    commit();
  });

  render();
})();

// ── 分頁顯示切換（設定分頁裡每張卡片右上角的開關）───────────
var VIS_KEY = 'dash-visible';
var visible = {};
try { visible = JSON.parse(localStorage.getItem(VIS_KEY)) || {}; } catch (e) { visible = {}; }

function isVisible(id) { return visible[id] !== false; }   // 預設全開

// 底部標籤列的排列跟著分組裡的順序走 —— 在設定裡把分頁往上拖，
// 標籤列也應該跟著往左，不然拖了半天看不出差別。
function orderTabs() {
  var g = groups.filter(function (x) { return x.id === curGroup; })[0];
  if (!g) return;
  var bar = document.querySelector('.tabbar');
  var settings = bar.querySelector('.tab[data-tab="settings"]');
  g.tabs.forEach(function (id) {
    var t = bar.querySelector('.tab[data-tab="' + id + '"]');
    if (t) bar.appendChild(t);
  });
  if (settings) bar.appendChild(settings);   // 設定固定在最後
}

// reselect：由開關觸發時要處理「正在看的分頁被關掉」
function applyVisibility(reselect) {
  orderTabs();
  PANEL_IDS.forEach(function (id) {
    var on = isVisible(id);
    var tab = document.querySelector('.tab[data-tab="' + id + '"]');
    if (tab) tab.hidden = !on || !inGroup(tab);   // 關掉的、或不屬於這一組的
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
// opts.pan：單指拖曳要平移時間軸（個股查詢），而不是移動指標。
// 兩種圖的差別只在單指拖曳那一段，其餘（雙指縮放、輕點開關指標、
// 擋掉觸控後補送的相容滑鼠事件）完全一樣，所以共用同一份。
function initTouch(gd, opts) {
  if (!window.matchMedia('(pointer: coarse)').matches) return;
  var panMode = !!(opts && opts.pan);

  var pinch = null, shown = false, wasShown = false, moved = false, taken = false;
  var sx = 0, sy = 0, pan = null;
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
    pan = panMode ? {r0: xa.d2l(xa.range[0]), r1: xa.d2l(xa.range[1]), len: xa._length}
                  : null;
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

    if (pan) {
      if (!moved) return;
      if (shown) hide();                       // 開始拖了就別留著指標
      var span = pan.r1 - pan.r0;
      var shift = -(t.clientX - sx) / pan.len * span;
      var lo = pan.r0 + shift, hi = pan.r1 + shift;
      var ext = fullExtent();
      if (ext) {                               // 不要拖到資料以外的空白
        if (lo < ext[0]) { lo = ext[0]; hi = lo + span; }
        if (hi > ext[1]) { hi = ext[1]; lo = hi - span; }
      }
      Plotly.relayout(gd, {'xaxis.range': [lo, hi]});
      return;
    }
    showAt(t);
  }, {capture: true, passive: false});

  gd.addEventListener('touchend', function (e) {
    if (!taken) return;
    if (e.touches.length > 0) return;
    e.stopPropagation();
    if (pinch) { pinch = null; taken = false; return; }
    pan = null;
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
    // 清單模式（F1）看的是大獎賽標題，就算場次全被篩掉也要留著那一列
    var listMode = table.classList.contains('list-mode');
    days.forEach(function (d) {
      var shown = 0;
      Array.prototype.slice.call(d.querySelectorAll('.cal-row')).forEach(function (row) {
        var on = Number(row.dataset.impact) >= minRank;
        row.hidden = !on;
        if (on) shown++;
      });
      d.hidden = d.dataset.off === '1' || (!listMode && shown === 0);
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

  // ── 可鑽入的分組（F1 賽程用）──────────────────────────
  // 清單只列出每一場大獎賽，點進去才看那一站的場次表；整季 20 幾站
  // 全部攤開在同一頁反而難找。用的是同一張表，切換的是要顯示哪些列。
  var drill = days.filter(function (d) { return d.classList.contains('drill'); });
  if (drill.length) {
    var subtab = panel ? panel.querySelector('.subtab[data-sub="sched"]') : null;

    var filterBar = panel ? panel.querySelector('.cal-filter') : null;

    // 只切換要顯示哪些列。不動頁面標頭 —— 切到別的分頁時標頭已經由
    // selectTab 換好了，這裡再寫一次會把它蓋掉。
    function applyRace(target) {
      table.classList.toggle('list-mode', !target);
      drill.forEach(function (d) { d.dataset.off = (target && d !== target) ? '1' : ''; });
      if (filterBar) filterBar.hidden = !target;   // 清單上沒有場次可篩
      setBack(target ? function () { showRace(null); } : null);
      refresh();
    }

    function showRace(target) {
      applyRace(target);
      var src = target || subtab;
      if (src) {
        document.getElementById('page-title').textContent = src.dataset.title;
        document.getElementById('page-meta').innerHTML = src.dataset.meta;
      }
      window.scrollTo(0, 0);
      syncSticky();
    }

    drill.forEach(function (d) {
      var th = d.querySelector('.cal-day-row th');
      th.addEventListener('click', function () {
        if (table.classList.contains('list-mode')) showRace(d);
      });
      th.addEventListener('keydown', function (e) {
        if ((e.key === 'Enter' || e.key === ' ') && table.classList.contains('list-mode')) {
          e.preventDefault();
          showRace(d);
        }
      });
    });

    // 切走再回來（換主分頁或子分頁）時回到清單
    if (subtab) subtab.addEventListener('click', function () { showRace(null); });
    tabs.forEach(function (t) {
      t.addEventListener('click', function () {
        if (!table.classList.contains('list-mode')) applyRace(null);
      });
    });

    applyRace(null);
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
// 清單寫在頁面裡，內文放在 news/{來源}.json，點開才抓、每個來源只抓一次。
var FIRST_BATCH = 12;   // 一開始排幾則
var BATCH = 10;         // 捲到底再接幾則
var newsBodies = {};    // 來源 → {序號: 內文}
var newsPending = {};   // 來源 → 進行中的請求

function loadBodies(sourceId) {
  if (newsBodies[sourceId]) return Promise.resolve(newsBodies[sourceId]);
  if (!newsPending[sourceId]) {
    newsPending[sourceId] = fetch('news/' + sourceId + '.json')
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(function (data) { newsBodies[sourceId] = data; return data; })
      .catch(function (e) { delete newsPending[sourceId]; throw e; });
  }
  return newsPending[sourceId];
}

Array.prototype.slice.call(document.querySelectorAll('.subpanel')).forEach(function (panel) {
  var list = panel.querySelector('.news-list');
  if (!list) return;
  var sourceId = panel.dataset.sub;
  var article = panel.querySelector('.news-article');
  var box = article.querySelector('.news-body');

  function note(text) {                 // 內文區的單行提示
    box.textContent = '';
    var p = document.createElement('p');
    p.className = 'news-nobody';
    p.textContent = text;
    box.appendChild(p);
  }

  function fill(li) {
    article.querySelector('.news-h').textContent =
      li.querySelector('.news-title').textContent;
    article.querySelector('.news-meta').textContent =
      li.querySelector('.news-meta').textContent;
    article.querySelector('.news-link').href = li.dataset.url;

    // 重點清單混了各家來源，每一則自己說它是哪一家
    var from = li.dataset.source || sourceId;

    if (li.dataset.body !== '1') {
      note('這則新聞抓不到內文（可能是影音報導或需要訂閱），請點下方連結看原文。');
      return;
    }
    note('載入內文中…');
    var want = li.dataset.n;
    loadBodies(from).then(function (data) {
      if (article.dataset.n !== want || article.dataset.from !== from) return;
      var text = data[want];
      if (!text) { note('這則新聞抓不到內文，請點下方連結看原文。'); return; }
      box.textContent = '';
      text.split(String.fromCharCode(10)).forEach(function (line) {
        if (!line.trim()) return;
        var p = document.createElement('p');
        p.textContent = line.trim();   // 來自新聞網站的文字，一律當純文字處理
        box.appendChild(p);
      });
      syncSticky();
    }).catch(function () {
      // 離線、或用 file:// 直接開（會被 CORS 擋）時走到這裡
      if (article.dataset.n === want && article.dataset.from === from) {
        note('內文載入失敗，請確認網路連線，或點下方連結看原文。');
      }
    });
  }

  function show(li) {
    list.hidden = !!li;
    // 「載入更多」在 ul 外面，看內文時要一起藏
    if (sentinel) sentinel.hidden = !!li || (shown >= items.length);
    article.hidden = !li;
    if (li) {
      article.dataset.n = li.dataset.n;
      article.dataset.from = li.dataset.source || sourceId;
      fill(li);
    }
    setBack(li ? function () { show(null); } : null);
    window.scrollTo(0, 0);
    syncSticky();
  }

  var items = Array.prototype.slice.call(list.querySelectorAll('.news-item'));
  items.forEach(function (li) {
    li.addEventListener('click', function () { show(li); });
    li.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(li); }
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

  // 切走再回來時回到清單，不要停在上次看的那一篇
  var subtab = document.querySelector('.subtab[data-sub="' + sourceId + '"]');
  if (subtab) subtab.addEventListener('click', function () { show(null); });
});

// ── 筆記：存在 localStorage，不上傳 ─────────────────────────
(function () {
  var panel = document.getElementById('panel-notes');
  if (!panel) return;

  var KEY = 'dash-notes';
  var listBox = panel.querySelector('.notes-list');
  var emptyMsg = panel.querySelector('.notes-empty');
  var newBtn = panel.querySelector('.notes-new');
  var editBox = panel.querySelector('.notes-edit');
  var titleIn = panel.querySelector('.notes-title');
  var bodyIn = panel.querySelector('.notes-body');
  var savedMsg = panel.querySelector('.notes-saved');
  var delBtn = panel.querySelector('.notes-del');
  var notes = [];
  var editing = null;      // 正在編輯的筆記 id
  var timer = null;

  function load() {
    try { notes = JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { notes = []; }
    if (!Array.isArray(notes)) notes = [];
  }

  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(notes));
      return true;
    } catch (e) {
      // 隱私模式或空間滿了
      savedMsg.textContent = '存不進去（瀏覽器不允許或空間已滿）';
      return false;
    }
  }

  function stamp(ms) {
    var d = new Date(ms);
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    return (d.getMonth() + 1) + '/' + pad(d.getDate()) + ' ' +
           pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function byId(id) {
    for (var i = 0; i < notes.length; i++) { if (notes[i].id === id) return notes[i]; }
    return null;
  }

  function renderCount() {
    var el = document.getElementById('notes-count');
    if (el) el.textContent = notes.length + ' 則';
  }

  function renderList() {
    listBox.textContent = '';
    notes.slice().sort(function (a, b) { return b.updated - a.updated; })
      .forEach(function (n) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'notes-item';
        var t = document.createElement('span');
        t.className = 'notes-t';
        t.textContent = n.title || '未命名筆記';
        var sub = document.createElement('span');
        sub.className = 'notes-sub';
        var preview = (n.body || '').split(String.fromCharCode(10))[0];
        sub.textContent = stamp(n.updated) + (preview ? '　' + preview : '');
        btn.appendChild(t);
        btn.appendChild(sub);
        btn.addEventListener('click', function () { open(n.id); });
        listBox.appendChild(btn);
      });
    emptyMsg.hidden = notes.length > 0;
    renderCount();
  }

  function showList() {
    editing = null;
    if (timer) { clearTimeout(timer); timer = null; flush(); }
    editBox.hidden = true;
    listBox.hidden = false;
    emptyMsg.hidden = notes.length > 0;
    newBtn.hidden = false;
    renderList();
    setBack(null);
    window.scrollTo(0, 0);
    syncSticky();
  }

  function open(id) {
    var n = byId(id);
    if (!n) return;
    editing = id;
    titleIn.value = n.title || '';
    bodyIn.value = n.body || '';
    savedMsg.textContent = '上次編輯 ' + stamp(n.updated);
    listBox.hidden = true;
    emptyMsg.hidden = true;
    newBtn.hidden = true;
    editBox.hidden = false;
    setBack(showList);
    window.scrollTo(0, 0);
    syncSticky();
  }

  function flush() {
    var n = byId(editing);
    if (!n) return;
    n.title = titleIn.value;
    n.body = bodyIn.value;
    n.updated = Date.now();
    if (save()) savedMsg.textContent = '已儲存 ' + stamp(n.updated);
  }

  function touched() {
    if (!editing) return;
    savedMsg.textContent = '編輯中…';
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () { timer = null; flush(); }, 500);
  }

  titleIn.addEventListener('input', touched);
  bodyIn.addEventListener('input', touched);

  newBtn.addEventListener('click', function () {
    var n = {id: String(Date.now()) + Math.random().toString(36).slice(2, 7),
             title: '', body: '', updated: Date.now()};
    notes.push(n);
    save();
    open(n.id);
    titleIn.focus();
  });

  delBtn.addEventListener('click', function () {
    var n = byId(editing);
    if (!n) return;
    var name = n.title || '這則未命名筆記';
    if (!window.confirm('確定要刪除「' + name + '」嗎？刪掉就找不回來了。')) return;
    notes = notes.filter(function (x) { return x.id !== editing; });
    editing = null;
    if (timer) { clearTimeout(timer); timer = null; }
    save();
    showList();
  });

  // 換到別的分頁、或關掉頁面時，把還沒寫進去的內容存好
  window.addEventListener('pagehide', function () { if (editing) flush(); });
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      if (editing) flush();
      // 回到筆記分頁時從清單開始，不要停在上次編輯的那一則
      if (t.dataset.tab === 'notes') showList();
    });
  });

  load();
  renderList();
})();

// ── 個股：目前鎖定的公司 ───────────────────────────────────
// 查過某一檔之後，營收／重訊／財報就只看那一檔 —— 想查台積電的人
// 切過去還要再篩一次很煩。清單上會有一個晶片可以解除。
var stockFocus = null;                 // {code, name}
var stockFocusWatchers = [];

function setStockFocus(target) {
  stockFocus = target;
  stockFocusWatchers.forEach(function (fn) { fn(); });
}

// ── 個股：即時查詢 ─────────────────────────────────────────
// 證交所的 www.twse.com.tw/rwd/ 端點帶 Access-Control-Allow-Origin: *，
// 所以這裡是真的當場去要資料，不是排程抓下來的快照。
// （公開資訊觀測站自己的 API 沒有這個標頭，瀏覽器連不了，那幾類走 JSON。）
(function () {
  var panel = document.querySelector('#panel-stock .subpanel[data-sub="query"]');
  if (!panel) return;

  var TWSE = 'https://www.twse.com.tw/rwd/zh/';
  var input = panel.querySelector('.sq-input');
  var sug = panel.querySelector('.sq-suggest');
  var rangeBar = panel.querySelector('.sq-range');
  var hint = panel.querySelector('.sq-hint');
  var result = panel.querySelector('.sq-result');
  var nameBox = panel.querySelector('.sq-name');
  var statsBox = panel.querySelector('.sq-stats');
  var months = 3;
  var current = null;      // {code, name}
  var seq = 0;             // 丟掉過期回應用的序號

  function say(text) {
    hint.textContent = text;
    hint.hidden = false;
  }

  function get(path) {
    return fetch(TWSE + path).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  }

  // 民國日期 115/09/01 → Date
  function rocDate(text) {
    // 用 [0-9] 這種寫法：這段 JS 住在 Python 的字串裡，反斜線會被吃掉
    var m = String(text).match(/([0-9]+)[^0-9]+([0-9]+)[^0-9]+([0-9]+)/);
    if (!m) return null;
    return new Date(Number(m[1]) + 1911, Number(m[2]) - 1, Number(m[3]));
  }

  function num(text) {
    var v = parseFloat(String(text).replace(/,/g, ''));
    return isFinite(v) ? v : null;
  }

  function ymd(d) {
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    return d.getFullYear() + pad(d.getMonth() + 1) + pad(d.getDate());
  }

  // ── 股號建議 ──────────────────────────────────────────
  var sugTimer = null;
  input.addEventListener('input', function () {
    var q = input.value.trim();
    if (sugTimer) clearTimeout(sugTimer);
    if (!q) { sug.hidden = true; return; }
    sugTimer = setTimeout(function () {
      get('api/codeQuery?query=' + encodeURIComponent(q)).then(function (d) {
        var list = (d && d.suggestions) || [];
        sug.textContent = '';
        list.slice(0, 8).forEach(function (line) {
          var parts = String(line).split('\t');
          if (parts.length < 2) return;
          var b = document.createElement('button');
          b.type = 'button';
          b.className = 'sq-opt';
          b.setAttribute('role', 'option');
          b.textContent = parts[0] + '　' + parts[1];
          b.addEventListener('click', function () {
            sug.hidden = true;
            input.value = parts[0] + ' ' + parts[1];
            load({code: parts[0], name: parts[1]});
          });
          sug.appendChild(b);
        });
        sug.hidden = !sug.childElementCount;
      }).catch(function () { sug.hidden = true; });
    }, 220);
  });

  input.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    var first = sug.querySelector('.sq-opt');
    if (first) { first.click(); return; }
    var code = input.value.trim().split(/[ 	]+/)[0];
    if (code) load({code: code, name: ''});
  });

  document.addEventListener('click', function (e) {
    if (!panel.contains(e.target)) sug.hidden = true;
  });

  Array.prototype.slice.call(rangeBar.querySelectorAll('.chip')).forEach(function (c) {
    c.addEventListener('click', function () {
      Array.prototype.slice.call(rangeBar.querySelectorAll('.chip'))
        .forEach(function (x) { x.setAttribute('aria-pressed', String(x === c)); });
      months = Number(c.dataset.months);
      if (current) load(current);
    });
  });

  // ── 查詢 ──────────────────────────────────────────────
  function load(target) {
    current = target;
    var my = ++seq;
    sug.hidden = true;
    rangeBar.hidden = false;
    result.hidden = true;
    say('查詢中…');

    // 一次只能查一個月，所以要往回逐月要
    var dates = [];
    var d = new Date();
    d.setDate(1);
    for (var i = 0; i < months; i++) {
      dates.push(ymd(d));
      d.setMonth(d.getMonth() - 1);
    }

    var jobs = dates.map(function (day) {
      return get('afterTrading/STOCK_DAY?date=' + day + '&stockNo=' +
                 encodeURIComponent(target.code) + '&response=json')
        .catch(function () { return null; });
    });
    jobs.push(get('afterTrading/BWIBBU?date=' + dates[0] + '&stockNo=' +
                  encodeURIComponent(target.code) + '&response=json')
      .catch(function () { return null; }));

    Promise.all(jobs).then(function (res) {
      if (my !== seq) return;                 // 期間又查了別的
      var value = res.slice(0, months);
      var ratio = res[months];
      var rows = [];
      value.forEach(function (r) {
        if (!r || r.stat !== 'OK' || !r.data) return;
        r.data.forEach(function (row) { rows.push(row); });
      });
      if (!rows.length) {
        say('查不到「' + target.code + '」的成交資料。可能是代號有誤，或這一段期間沒有交易。');
        result.hidden = true;
        return;
      }
      rows.sort(function (a, b) { return rocDate(a[0]) - rocDate(b[0]); });
      draw(target, rows, ratio);
    }).catch(function () {
      if (my !== seq) return;
      say('查詢失敗，可能是網路問題或證交所暫時無法連線。');
    });
  }

  function stat(label, value) {
    var box = document.createElement('div');
    box.className = 'sq-stat';
    var l = document.createElement('span');
    l.className = 'sq-stat-l';
    l.textContent = label;
    var v = document.createElement('b');
    v.textContent = value;
    box.appendChild(l);
    box.appendChild(v);
    return box;
  }

  function draw(target, rows, ratio) {
    var last = rows[rows.length - 1];
    var close = num(last[6]);
    var diff = num(last[7]);
    var name = target.name || (rows.length ? '' : '');
    nameBox.textContent = target.code + (name ? '　' + name : '');
    setStockFocus({code: target.code, name: name});   // 其他子分頁跟著只看這一檔

    statsBox.textContent = '';
    statsBox.appendChild(stat('收盤', close == null ? '—' : close.toLocaleString()));
    if (diff != null) {
      var pct = (close && close - diff) ? (diff / (close - diff) * 100) : null;
      statsBox.appendChild(stat('漲跌',
        (diff > 0 ? '+' : '') + diff.toFixed(2) +
        (pct == null ? '' : '（' + (pct > 0 ? '+' : '') + pct.toFixed(2) + '%）')));
    }
    statsBox.appendChild(stat('成交股數', last[1]));
    if (ratio && ratio.stat === 'OK' && ratio.data && ratio.data.length) {
      var r = ratio.data[ratio.data.length - 1];
      statsBox.appendChild(stat('本益比', r[3] || '—'));
      statsBox.appendChild(stat('殖利率', (r[1] || '—') + '%'));
      statsBox.appendChild(stat('股價淨值比', r[4] || '—'));
    }

    var xs = rows.map(function (r) {
      var d = rocDate(r[0]);
      return d ? d.toISOString().slice(0, 10) : null;
    });
    var ys = rows.map(function (r) { return num(r[6]); });

    // 自己組 layout，不要拿 DRAM 的來改 —— 那份鎖著 DRAM 自己的
    // x 軸範圍與快速區間鈕，套過來會讓線只畫在圖的一角。
    var grid = dark ? '#333849' : '#dee2e6';
    var fg = dark ? '#9aa0ac' : '#6c757d';
    function pad(iso, days) {
      var d = new Date(iso + 'T00:00:00Z');
      d.setUTCDate(d.getUTCDate() + days);
      return d.toISOString().slice(0, 10);
    }
    var L = {
      height: 300,
      margin: {l: 52, r: 12, t: 10, b: 34},
      showlegend: false,
      dragmode: 'pan',          // 拖曳是往回看，不是框選放大
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: {color: fg, size: 11},
      hovermode: 'x unified',
      hoverdistance: -1,
      // 指標標籤的底色要跟著主題走，不然深色模式下是一塊白
      hoverlabel: {bgcolor: dark ? '#242839' : '#ffffff', bordercolor: grid,
                   font: {color: dark ? '#e8e8e8' : '#212529', size: 12}},
      // 前後各留一天，最後一天的線才不會貼著右邊界被切掉
      xaxis: {type: 'date', gridcolor: grid, linecolor: grid, zeroline: false,
              tickformat: '%m/%d', hoverformat: '%Y/%m/%d', automargin: true,
              range: [pad(xs[0], -1), pad(xs[xs.length - 1], 1)]},
      yaxis: {gridcolor: grid, linecolor: grid, zeroline: false,
              tickformat: ',.0f', automargin: true}
    };

    // 先讓結果區顯示出來再畫：容器還藏著的話 Plotly 量不到寬度，
    // 會退回預設的 700px，把整個版面撐寬。
    hint.hidden = true;
    result.hidden = false;

    Plotly.react('chart-stockquery', [{
      type: 'scatter', mode: 'lines', x: xs, y: ys,
      line: {width: 2, color: dark ? '#4dd4ac' : '#1f9d6b'},
      // x unified 的標題已經是日期了，這裡只寫價格
      hovertemplate: '收盤 %{y:,.2f}<extra></extra>'
    }], L, {displayModeBar: false, responsive: true,
            scrollZoom: false, doubleClick: false});

    syncSticky();
  }

  // 觸控行為跟其他圖表同一套，只是單指拖曳改成平移時間軸
  initTouch(document.getElementById('chart-stockquery'), {pan: true});

  // 換主題時把已經畫好的圖重畫一次
  window.addEventListener('dash-theme', function () { if (current) load(current); });
})();

// ── 個股：營收／重訊／財報（排程抓下來的 JSON）─────────────
(function () {
  var panel = document.getElementById('panel-stock');
  if (!panel) return;
  var cache = {};

  function money(text) {          // 千元 → 億元，看得懂比精確重要
    var v = parseFloat(text);
    if (!isFinite(v)) return '—';
    return (v / 100000).toFixed(2) + ' 億';
  }
  function pct(text) {
    var v = parseFloat(text);
    if (!isFinite(v)) return '—';
    return (v > 0 ? '+' : '') + v.toFixed(2) + '%';
  }
  function cls(text) {
    var v = parseFloat(text);
    if (!isFinite(v) || v === 0) return '';
    return v > 0 ? ' up' : ' down';
  }
  function rocMonth(v) { return String(v).length === 5 ? v.slice(0, 3) + '/' + v.slice(3) : v; }
  function rocDate(v) {
    v = String(v);
    return v.length === 7 ? v.slice(0, 3) + '/' + v.slice(3, 5) + '/' + v.slice(5) : v;
  }
  // 發言時間是 HHMMSS，早上的會少掉開頭那個 0（70003 就是 07:00:03）
  function hhmm(v) {
    v = String(v || '');
    if (!v) return '';
    while (v.length < 6) v = '0' + v;
    return v.slice(0, 2) + ':' + v.slice(2, 4);
  }

  // 每個資料集怎麼變成一列
  var VIEWS = {
    revenue: {
      match: function (r) { return r.name + r.code + r.industry; },
      sort: function (a, b) { return (parseFloat(b.yoy) || -1e9) - (parseFloat(a.yoy) || -1e9); },
      row: function (r) {
        return {title: r.code + '　' + r.name,
                sub: r.industry + '　·　' + rocMonth(r.month),
                cells: [['當月營收', money(r.revenue), ''],
                        ['年增', pct(r.yoy), cls(r.yoy)],
                        ['月增', pct(r.mom), cls(r.mom)]]};
      }
    },
    income: {
      match: function (r) { return r.name + r.code; },
      sort: function (a, b) { return (parseFloat(b.revenue) || 0) - (parseFloat(a.revenue) || 0); },
      row: function (r) {
        return {title: r.code + '　' + r.name,
                sub: r.year + ' 年第 ' + r.quarter + ' 季',
                cells: [['營收', money(r.revenue), ''],
                        ['營業利益', money(r.operating), ''],
                        ['EPS', (r.eps || '—') + ' 元', cls(r.eps)]]};
      }
    }
  };

  function renderRows(box, rows, view) {
    box.textContent = '';
    if (!rows.length) {
      var none = document.createElement('p');
      none.className = 'cal-empty';
      none.textContent = '沒有符合的資料。';
      box.appendChild(none);
      return;
    }
    rows.slice(0, 200).forEach(function (r) {
      var item = view.row(r);
      var card = document.createElement('div');
      card.className = 'sl-item';
      var head = document.createElement('div');
      head.className = 'sl-head';
      var t = document.createElement('span');
      t.className = 'sl-title';
      t.textContent = item.title;
      var sb = document.createElement('span');
      sb.className = 'sl-sub';
      sb.textContent = item.sub;
      head.appendChild(t);
      head.appendChild(sb);
      card.appendChild(head);
      var grid = document.createElement('div');
      grid.className = 'sl-grid';
      item.cells.forEach(function (c) {
        var cell = document.createElement('div');
        cell.className = 'sl-cell';
        var l = document.createElement('span');
        l.textContent = c[0];
        var v = document.createElement('b');
        v.className = 'sl-v' + c[2];
        v.textContent = c[1];
        cell.appendChild(l);
        cell.appendChild(v);
        grid.appendChild(cell);
      });
      card.appendChild(grid);
      box.appendChild(card);
    });
    if (rows.length > 200) {
      var more = document.createElement('p');
      more.className = 'cal-empty';
      more.textContent = '另有 ' + (rows.length - 200) + ' 筆，用上面的搜尋框縮小範圍。';
      box.appendChild(more);
    }
  }

  // 重大訊息：清單 + 全文，動線跟新聞一樣
  function renderAnnounce(box, rows, sp) {
    box.textContent = '';
    var list = document.createElement('div');
    var article = document.createElement('div');
    article.className = 'news-article';
    article.hidden = true;

    function show(r) {
      list.hidden = !!r;
      article.hidden = !r;
      if (r) {
        article.textContent = '';
        var h = document.createElement('h2');
        h.className = 'news-h';
        h.textContent = r.subject;
        var meta = document.createElement('div');
        meta.className = 'news-meta';
        meta.textContent = r.code + '　' + r.name + '　·　' +
                           rocDate(r.date) + ' ' + hhmm(r.time) +
                           (r.clause ? '　·　' + r.clause : '');
        var body = document.createElement('div');
        body.className = 'news-body';
        (r.body || '').split(String.fromCharCode(10)).forEach(function (line) {
          if (!line.trim()) return;
          var p = document.createElement('p');
          p.textContent = line.trim();
          body.appendChild(p);
        });
        if (!body.childElementCount) {
          var p2 = document.createElement('p');
          p2.className = 'news-nobody';
          p2.textContent = '這則公告沒有說明內容。';
          body.appendChild(p2);
        }
        var link = document.createElement('a');
        link.className = 'news-link';
        link.href = 'https://mops.twse.com.tw/mops/#/web/home';
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = '到公開資訊觀測站 ↗';
        article.appendChild(h);
        article.appendChild(meta);
        article.appendChild(body);
        article.appendChild(link);
      }
      setBack(r ? function () { show(null); } : null);
      window.scrollTo(0, 0);
      syncSticky();
    }

    if (!rows.length) {
      var none = document.createElement('p');
      none.className = 'cal-empty';
      none.textContent = '沒有符合的公告。';
      list.appendChild(none);
    }
    rows.slice(0, 200).forEach(function (r) {
      var card = document.createElement('div');
      card.className = 'sl-item sl-click';
      card.setAttribute('role', 'button');
      card.tabIndex = 0;
      var head = document.createElement('div');
      head.className = 'sl-head';
      var t = document.createElement('span');
      t.className = 'sl-title';
      t.textContent = r.subject;
      var sb = document.createElement('span');
      sb.className = 'sl-sub';
      sb.textContent = r.code + '　' + r.name + '　·　' +
                       rocDate(r.date) + ' ' + hhmm(r.time);
      head.appendChild(t);
      head.appendChild(sb);
      card.appendChild(head);
      card.addEventListener('click', function () { show(r); });
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); show(r); }
      });
      list.appendChild(card);
    });
    box.appendChild(list);
    box.appendChild(article);
    sp._reset = function () { show(null); };
  }

  // 鎖定某一檔時，清單上方掛一個可以解除的晶片
  function focusChip(sp) {
    var old = sp.querySelector('.sl-focus');
    if (old) old.remove();
    if (!stockFocus) return;
    var chip = document.createElement('div');
    chip.className = 'sl-focus';
    var label = document.createElement('span');
    label.textContent = '只看 ' + stockFocus.code +
                        (stockFocus.name ? '　' + stockFocus.name : '');
    var clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'sl-clear';
    clear.setAttribute('aria-label', '顯示全部公司');
    clear.textContent = '✕';
    clear.addEventListener('click', function () { setStockFocus(null); });
    chip.appendChild(label);
    chip.appendChild(clear);
    sp.insertBefore(chip, sp.querySelector('.sl-body'));
  }

  function fill(sp) {
    var set = sp.dataset.sub;
    var box = sp.querySelector('.sl-body');
    var filter = sp.querySelector('.sl-filter');
    var rows = cache[set];
    var q = filter.value.trim().toLowerCase();
    var view = VIEWS[set];
    var shown = rows;

    focusChip(sp);
    if (stockFocus) {
      shown = shown.filter(function (r) { return r.code === stockFocus.code; });
    }
    if (q) {
      shown = shown.filter(function (r) {
        var hay = set === 'announce' ? (r.code + r.name + r.subject) : view.match(r);
        return hay.toLowerCase().indexOf(q) >= 0;
      });
    }
    if (set === 'announce') {
      shown = shown.slice().sort(function (a, b) {
        return (b.date + b.time).localeCompare(a.date + a.time);
      });
      renderAnnounce(box, shown, sp);
    } else {
      renderRows(box, shown.slice().sort(view.sort), view);
    }
    // 鎖定的公司在這份資料裡沒有東西時，講清楚是哪一種空
    if (stockFocus && !shown.length) {
      var note = box.querySelector('.cal-empty');
      if (note) note.textContent = stockFocus.code + ' 在這份資料裡沒有資料。';
    }
  }

  function ensure(sp) {
    var set = sp.dataset.sub;
    if (cache[set]) { fill(sp); return; }
    var box = sp.querySelector('.sl-body');
    fetch('stock/' + set + '.json').then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (data) {
      cache[set] = data;
      fill(sp);
    }).catch(function () {
      box.textContent = '';
      var p = document.createElement('p');
      p.className = 'cal-empty';
      p.textContent = '資料載入失敗，請確認網路連線後重新載入頁面。';
      box.appendChild(p);
    });
  }

  Array.prototype.slice.call(panel.querySelectorAll('.subpanel')).forEach(function (sp) {
    var filter = sp.querySelector('.sl-filter');
    if (!filter) return;
    var timer = null;
    filter.addEventListener('input', function () {
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () { if (cache[sp.dataset.sub]) fill(sp); }, 200);
    });
    var subtab = panel.querySelector('.subtab[data-sub="' + sp.dataset.sub + '"]');
    if (subtab) {
      subtab.addEventListener('click', function () {
        if (sp._reset) sp._reset();
        ensure(sp);
      });
    }
    // 查了別檔或解除鎖定時，正在看的那一頁要立刻跟著換
    stockFocusWatchers.push(function () {
      if (!sp.hidden && cache[sp.dataset.sub]) fill(sp);
    });
  });
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
renderGroupBar();
selectGroup(curGroup, false);
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
            # 本機資料（筆記）沒有「最後更新日」可寫
            suffix = ("" if stats[p["id"]].get("local")
                      else f'<br>最後更新日：{stats[p["id"]]["latest"]}')
            head[p["id"]] = {"title": p["title"], "meta": f'{p["meta"]}{suffix}'}
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
        TPL.replace("__GROUPBAR__", _groupbar_html())
           .replace("__GROUPS__", json.dumps(_default_groups(), ensure_ascii=False))
           .replace("__TAB_LABELS__", json.dumps(
               {p["id"]: p["tab"] for p in PANELS}, ensure_ascii=False))
           .replace("__CHART_PANELS__", _panels_html(panel_data))
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
    _write_news_bodies(panel_data.get("news", {}))
    _write_stock_data(panel_data.get("stock", {}))
    return OUTPUT


def _write_stock_data(data: dict) -> None:
    """個股的三個資料集另存 docs/stock/{資料集}.json，進子分頁時才載。

    三份加起來三百多 KB，塞進 index.html 會讓每個人打開首頁都先扛這些，
    但真正會去看的人不多。
    """
    if not data:
        return
    STOCK_DIR.mkdir(parents=True, exist_ok=True)
    written = set()
    for key, rows in stock_datasets(data).items():
        path = STOCK_DIR / f"{key}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
        written.add(path.name)
    for stale in STOCK_DIR.glob("*.json"):
        if stale.name not in written:
            stale.unlink()


def _write_news_bodies(data: dict) -> None:
    """新聞內文另存 docs/news/{來源}.json，讀者點開某一則時才下載。"""
    if not data:
        return
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    written = set()
    for source_id, bodies in news_bodies(data).items():
        path = NEWS_DIR / f"{source_id}.json"
        path.write_text(json.dumps(bodies, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
        written.add(path.name)
    for stale in NEWS_DIR.glob("*.json"):        # 來源移除後不要留著孤兒檔
        if stale.name not in written:
            stale.unlink()


if __name__ == "__main__":
    path = build()
    print(f"[完成] 已產生 {path}（{path.stat().st_size // 1024} KB）")
