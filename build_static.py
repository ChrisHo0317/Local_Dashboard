"""
產生 GitHub Pages 用的靜態網站 site/

    site/index.html         頁面骨架與各分頁的 HTML（約 200 KB）
    site/app.css、app.js    樣式與主要程式（原本寫在這個檔的字串裡，搬到 web/）
    site/intel.js           情報中心（總覽、個股深度頁、選股）的程式
    site/data/charts/       走勢圖的線條資料，第一次顯示那張圖時才下載
    site/data/…             情報中心的資料（intel_build.py 產生）
    site/news/、site/stock/ 新聞內文、個股清單

網站不進 git：GitHub Actions 建置後用 deploy-pages 直接發布（見 .github/workflows/）。

沒有伺服器端 callback，由前端 Plotly.react 繪製；hover、縮放、時間軸縮圖都保留。
版面由底部懸浮式標籤列切換，分頁分三種（PANELS 的 kind）：
  chartgroup  多張走勢圖合併成一個分頁，子分頁切換（原本的「走勢圖」分頁，已搬進總覽，目前沒有用到）
  calendar    在這裡直接產生 HTML（各 *_render.py 負責），名稱沿用最早的行事曆分頁
  chart       單張走勢圖（目前沒有用到，保留給之後）

走勢圖（TREND_CHARTS：DRAM、美債、黃金、BTC、美股、匯率）放在總覽的「走勢」子分頁：
上方是 trend_cards.py 產生的精簡卡片（data/trend.json），點卡片展開原本的完整圖（data/charts/{key}.json）。

要新增分頁：在 PANELS 加一筆即可，標籤列、分頁、圖例、設定頁的資料卡片都會跟著生成。

    python build_static.py
"""
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import plotly.io as pio

import intel_build
import layout_render
import trend_cards
from bond_data import CSV_PATH as BOND_CSV, latest_date as bond_latest, load_bonds
from btc_data import CSV_PATH as BTC_CSV, latest_date as btc_latest, load_btc
from calendar_data import CSV_PATH as CAL_CSV, load_events
from calendar_render import panel_html as cal_panel_html, stats as cal_stats
from chart import (build_bond_figure, build_btc_figure, build_figure, build_fx_figure,
                   build_gold_figure, build_points_figure, build_us_index_figure,
                   series_colors)
from dram_data import BASE_DIR, CSV_PATH as DRAM_CSV, latest_date as dram_latest, load_dram
from f1_data import CSV_PATH as F1_CSV, load_all as load_f1_all, load_points_series
from f1_render import panel_html as f1_panel_html, stats as f1_stats
from gold_data import CSV_PATH as GOLD_CSV, latest_date as gold_latest, load_gold
from news_data import CSV_PATH as NEWS_CSV, load_all as load_news_all
from news_render import (bodies as news_bodies, lists as news_lists,
                         panel_html as news_panel_html, stats as news_stats)
from notes_render import (META as NOTES_META, panel_html as notes_panel_html,
                          stats as notes_stats)
from overview_render import (META as OVERVIEW_META, panel_html as overview_panel_html,
                             stats as overview_stats)
from stock_data import CSV_PATHS as STOCK_CSVS, load_all as load_stock_all
from stock_render import (META as STOCK_META, datasets as stock_datasets,
                          panel_html as stock_panel_html, stats as stock_stats)
from spacex_data import CSV_PATH as SPACEX_CSV, load_all as load_spacex_all
from spacex_render import panel_html as spacex_panel_html, stats as spacex_stats
from tw_events import with_tw_events
from version import __version__
from xmarket_data import CSV_PATH as XMARKET_CSV, latest_date as xmarket_latest, load_xmarket

WEB_DIR = BASE_DIR / "web"
SITE_DIR = BASE_DIR / "site"
OUTPUT = SITE_DIR / "index.html"
NEWS_DIR = SITE_DIR / "news"
STOCK_DIR = SITE_DIR / "stock"
CHART_DIR = SITE_DIR / "data" / "charts"

# 走勢圖：總覽「走勢」子分頁裡的完整圖（原本是底部的「走勢圖」分頁）。
# 各項目沿用原本各自的欄位定義。
TREND_CHARTS = [
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
    },
    {
        "id": "bond",
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
    },
    {
        "id": "gold",
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
    },
    {
        "id": "btc",
        "tab": "BTC",
        "title": "比特幣走勢",
        "meta": "資料來源：Yahoo Finance　·　單位：USD",
        "item_label": "幣別",
        "source_name": "Yahoo Finance",
        "source_url": "https://finance.yahoo.com/quote/BTC-USD/",
        "csv": BTC_CSV,
        "load": load_btc,
        "figure": build_btc_figure,
        "latest": btc_latest,
    },
    {
        "id": "usidx",
        "tab": "美股",
        "title": "費城半導體與那斯達克",
        "meta": "資料來源：Yahoo Finance　·　收盤指數（美東時間）",
        "item_label": "指數",
        "source_name": "Yahoo Finance",
        "source_url": "https://finance.yahoo.com/quote/%5ESOX/",
        "csv": XMARKET_CSV,
        "load": lambda: load_xmarket(["費城半導體", "那斯達克"]),
        "figure": build_us_index_figure,
        "latest": xmarket_latest,
    },
    {
        "id": "fx",
        "tab": "匯率",
        "title": "美元兌台幣",
        "meta": "資料來源：Yahoo Finance　·　1 美元可兌換的新台幣",
        "item_label": "幣別",
        "source_name": "Yahoo Finance",
        "source_url": "https://finance.yahoo.com/quote/TWD%3DX/",
        "csv": XMARKET_CSV,
        "load": lambda: load_xmarket(["美元兌台幣"]),
        "figure": build_fx_figure,
        "latest": xmarket_latest,
    },
]

_INTEL: dict = {}


def _intel() -> dict:
    """情報中心的資料（intel_build.build）只產生一次，今日、市場、選股三個分頁共用。"""
    if "d" not in _INTEL:
        _INTEL["d"] = intel_build.build(SITE_DIR)
    return _INTEL["d"]


# 圖表分頁定義。新增一組資料只要在這裡加一筆。
PANELS = [
    {
        "id": "today",
        "group": "finance",
        "kind": "calendar",
        "tab": "今日",
        "title": "今日重點",
        "meta": OVERVIEW_META,
        "source_name": "證交所、櫃買中心",
        "source_url": "https://www.twse.com.tw/",
        "csv": None,
        # 產生情報中心的資料（市場、選股、個股也用同一份），回傳設定頁要用的摘要
        "load": lambda: _intel(),
        "render": layout_render.today_html,
        "stats": overview_stats,
        # 儀表圖示
        "icon": '<path d="M4.5 16.5a7.5 7.5 0 1 1 15 0"/>'
                '<line x1="12" y1="16.5" x2="15.6" y2="11.4"/>'
                '<circle cx="12" cy="16.5" r="1.3" fill="currentColor" stroke="none"/>'
                '<line x1="4" y1="20" x2="20" y2="20"/>',
    },
    {
        "id": "market",
        "group": "finance",
        "kind": "calendar",
        "tab": "市場",
        "title": "台股大盤",
        "meta": "加權指數、法人買賣超與融資維持率",
        "source_name": "證交所、櫃買中心、Yahoo Finance、國發會、FRED",
        "source_url": "https://www.twse.com.tw/",
        "csv": None,
        "load": lambda: _intel(),
        "render": layout_render.market_html,
        "stats": layout_render.market_stats,
        # 折線圖示
        "icon": '<path d="M3 3v16.5A1.5 1.5 0 0 0 4.5 21H21"/>'
                '<path d="M7 15l3.5-4 3 2.5L20 7"/>'
                '<circle cx="20" cy="7" r="1.4" fill="currentColor" stroke="none"/>',
    },
    {
        "id": "picks",
        "group": "finance",
        "kind": "calendar",
        "tab": "選股",
        "title": "強勢股",
        "meta": "哪些股票漲得越來越快：強度 × 加速度",
        "source_name": "證交所、櫃買中心",
        "source_url": "https://www.twse.com.tw/",
        "csv": None,
        "load": lambda: _intel(),
        "render": layout_render.picks_html,
        "stats": layout_render.picks_stats,
        # 火焰（強勢）圖示
        "icon": '<path d="M12 21c-3.6 0-6.5-2.6-6.5-6.2 0-3.4 2.4-5.4 3.6-7.8.3 1.9 1.3 3 2.4 3.6'
                '-.2-3.2 1.1-6.1 3.5-8.1.2 3.1 3.5 5.6 3.5 10.9 0 4.2-2.9 7.6-6.5 7.6z"/>'
                '<path d="M12 21c-1.5 0-2.7-1.2-2.7-2.9 0-1.8 1.4-2.7 2.1-4 .9 1.4 3.3 2.2 3.3 4.2'
                ' 0 1.6-1.2 2.7-2.7 2.7z"/>',
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
        # 財經分類加了「總覽」，SpaceX 移到個人追蹤，底部標籤列才不會變擠
        "group": "personal",
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
        "render": layout_render.stock_html,
        "stats": stock_stats,
        # 放大鏡加一段走勢
        "icon": '<circle cx="10.5" cy="10.5" r="6.5"/>'
                '<line x1="15.4" y1="15.4" x2="20.5" y2="20.5"/>'
                '<polyline points="7.6 12.2 9.6 9.6 11.6 11.2 13.6 8"/>',
    },
    {
        "id": "info",
        "group": "finance",
        "kind": "calendar",
        "tab": "資訊",
        "title": "熱門新聞分析",
        "meta": "新聞、熱門分析與財經行事曆",
        "source_name": "各新聞網站、FXStreet",
        "source_url": "https://www.fxstreet.com/economic-calendar",
        "csv": NEWS_CSV,
        # 新聞＋行事曆（總經事件＋台股事件）
        "load": lambda: {"news": load_news_all(), "cal": with_tw_events(load_events())},
        "render": layout_render.info_html,
        "stats": layout_render.info_stats,
        # 報紙圖示
        "icon": '<path d="M4 5.5h13v13H4z"/>'
                '<path d="M17 9h3v7.5a2 2 0 0 1-2 2H4"/>'
                '<line x1="7" y1="9" x2="14" y2="9"/>'
                '<line x1="7" y1="12" x2="14" y2="12"/>'
                '<line x1="7" y1="15" x2="11" y2="15"/>',
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
    btns.append(_tab_button("settings", "設定", SETTINGS_ICON, False).replace(
        'class="tab"', 'class="tab" hidden', 1))
    return ('<nav class="tabbar" role="tablist" aria-label="主要分頁">\n'
            '    <span class="tab-pill" id="tab-pill" aria-hidden="true"></span>\n'
            + "\n".join(btns) + "\n  </nav>")


def _groupbar_html() -> str:
    # 按鈕由 JS 依使用者的分組設定產生，這裡只留外框與滑動指示器
    return ('<nav class="groupbar" id="groupbar" role="tablist" aria-label="分類">\n'
            '    <span class="grp-pill" id="grp-pill" aria-hidden="true"></span>\n'
            '  </nav>')


def _trend_group_html(members: list, head: dict) -> str:
    """走勢圖分頁：子分頁列 + 各一個圖表空殼（由前端 Plotly 繪製）。

    子分頁的標頭沿用各自算好的 head（含最後更新日），與合併前一致。
    """
    sub_btns = []
    sub_panels = []
    for i, m in enumerate(members):
        selected = "true" if i == 0 else "false"
        h = head[m["id"]]
        # meta 裡含 <br>，是刻意讓前端當 HTML 插入（setHead 用 innerHTML）——
        # 這裡只跳脫屬性值本身需要的 & 與 "，不跳脫 <br>。
        meta_attr = h["meta"].replace("&", "&amp;").replace('"', "&quot;")
        sub_btns.append(
            f'    <button type="button" class="subtab" data-sub="{m["id"]}"'
            f' data-title="{escape(h["title"])}" data-meta="{meta_attr}"'
            f' aria-selected="{selected}">{m["tab"]}</button>'
        )
        hidden = "" if i == 0 else " hidden"
        sub_panels.append(
            f'  <div class="subpanel" data-sub="{m["id"]}"{hidden}>\n'
            f'    <div class="chart" id="chart-{m["id"]}"></div>\n'
            f'    <div class="legend-bar" data-chart="{m["id"]}"></div>\n'
            f'  </div>'
        )
    subtabs = ('  <div class="subtabs" role="tablist" aria-label="走勢圖子分頁">\n'
               + "\n".join(sub_btns) + "\n  </div>")
    return subtabs + "\n" + "\n".join(sub_panels)


def _panels_html(panel_data, head: dict) -> str:
    """各分頁的內容。圖表分頁留空殼由 JS 繪製，行事曆分頁在此直接產生 HTML。"""
    out = []
    for i, p in enumerate(PANELS):
        hidden = "" if i == 0 else " hidden"
        kind = p.get("kind", "chart")
        if kind == "calendar":
            body = p["render"](panel_data[p["id"]])
        elif kind == "chartgroup":
            body = _trend_group_html(p["members"], head)
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


def _trend_settings_card(p: dict, stats: dict, switch: bool = True) -> str:
    """走勢圖的資料卡片：一張卡彙整底下每個項目的來源與更新日。
    switch=False：沒有自己的頂層分頁（嵌在總覽裡），不放顯示開關。"""
    rows = []
    for m in p["members"]:
        s = stats[m["id"]]
        rows.append(
            f'      <div class="row"><span>{m["tab"]}　最後更新日</span><b>{s["latest"]}</b></div>\n'
            f'      <div class="row"><span>{m["tab"]}　資料來源</span>'
            f'<a href="{m["source_url"]}" target="_blank" rel="noopener">{m["source_name"]}</a></div>'
        )
    body = "\n".join(rows)
    toggle = (f'''
        <button class="switch sw-sm" type="button" role="switch" data-panel="{p["id"]}"
                aria-checked="true" aria-label="顯示{p["tab"]}分頁"><span class="knob"></span></button>'''
              if switch else "")
    return f'''    <div class="card fold" data-card="{p["id"]}">
      <div class="card-h">
        <button type="button" class="card-t" aria-expanded="false"
                aria-controls="cardbody-{p["id"]}">
          <span class="card-chev">&#9656;</span><span>{p["tab"]}　資料</span>
        </button>{toggle}
      </div>
      <div class="card-body" id="cardbody-{p["id"]}">
{body}
      </div>
    </div>'''


TREND_CARD = {"id": "trend", "tab": "市場 › 走勢", "members": TREND_CHARTS}


def _settings_cards(stats: dict) -> str:
    cards = []
    for p in PANELS:
        if p.get("kind") == "chartgroup":
            cards.append(_trend_settings_card(p, stats))
            continue
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
        if s.get("rows_html"):
            # 自己決定要列哪幾列的分頁（總覽）
            rows = "\n".join(f'      <div class="row"><span>{escape(k)}</span><b>{escape(str(v))}</b></div>'
                             for k, v in s["rows_html"])
            cards.append(f'''    <div class="card fold" data-card="{p["id"]}">
      <div class="card-h">
        <button type="button" class="card-t" aria-expanded="false"
                aria-controls="cardbody-{p["id"]}">
          <span class="card-chev">&#9656;</span><span>{p["tab"]}　資料</span>
        </button>
        <button class="switch sw-sm" type="button" role="switch" data-panel="{p["id"]}"
                aria-checked="true" aria-label="顯示{p["tab"]}分頁"><span class="knob"></span></button>
      </div>
      <div class="card-body" id="cardbody-{p["id"]}">
{rows}
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
    # 走勢圖嵌在市場分頁裡，資料卡片接在市場後面
    at = next((i + 1 for i, c in enumerate(cards) if 'data-card="market"' in c), len(cards))
    cards.insert(at, _trend_settings_card(TREND_CARD, stats, switch=False))
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
<link rel="stylesheet" href="app.css?v=__VERSION__">
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
      <h1 id="page-title">__TITLE0__</h1>
      <button id="meta-btn" class="iconbtn info-btn" type="button" aria-expanded="false"
              aria-controls="page-meta" aria-label="這一頁的說明">i</button>
    </div>
    <div class="head-right">
      __GROUPBAR__
      <button id="settings-btn" class="iconbtn" type="button" aria-label="設定" aria-pressed="false">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">__SETTINGS_ICON__</svg>
      </button>
    </div>
    <div class="meta" id="page-meta"><span id="page-meta-text">__META0__</span>
      <span class="ver">__VERSION__</span></div>
  </header>

  <div class="ptr" id="ptr" aria-hidden="true"><span class="ptr-box"></span></div>

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
// 頁面產生時才知道的資料；程式本體在 app.js、intel.js。
// 圖表只嵌名稱與顏色（圖例要用），線條資料另存 data/charts/，第一次顯示時才下載。
const CHARTS = __CHARTS__;
const HEAD   = __HEAD__;           // 各分頁的標題與說明
const PANEL_IDS = __PANEL_IDS__;   // 可切換顯示的分頁（設定分頁不可關）
const DEFAULT_GROUPS = __GROUPS__; // 出廠的分組與歸屬（使用者可在設定裡改）
const TAB_LABELS = __TAB_LABELS__; // 分頁 id → 標籤文字
const VERSION = '__VERSION__';
</script>
<script src="app.js?v=__VERSION__"></script>
<script src="intel.js?v=__VERSION__"></script>
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


def _write_charts(charts: dict) -> dict:
    """
    線條資料寫成 data/charts/{key}.json，第一次顯示那張圖時才下載；
    頁面裡只留圖例要用的名稱與顏色。
    """
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    meta = {}
    for key, c in charts.items():
        (CHART_DIR / f"{key}.json").write_text(
            json.dumps({"traces": c["traces"], "layout": c["layout"]},
                       ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        meta[key] = {"series": c["series"], "itemLabel": c["itemLabel"]}
    return meta


def _copy_web() -> None:
    """web/ 底下的樣式、程式、圖示原樣複製到輸出目錄。"""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    for src in WEB_DIR.iterdir():
        if src.is_file():
            shutil.copy2(src, SITE_DIR / src.name)


def build() -> Path:
    """讀各資料集、產生 site/，回傳 index.html 的路徑。"""
    charts = {}
    stats = {}
    head = {}

    panel_data = {}
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    for p in PANELS:
        kind = p.get("kind", "chart")
        if kind == "calendar":
            panel_data[p["id"]] = p["load"]()
            stats[p["id"]] = p["stats"](panel_data[p["id"]])
            # 本機資料（筆記）沒有「最後更新日」可寫
            suffix = ("" if stats[p["id"]].get("local")
                      else f'<br>最後更新日：{stats[p["id"]]["latest"]}')
            head[p["id"]] = {"title": p["title"], "meta": f'{p["meta"]}{suffix}'}
            continue

        if kind == "chartgroup":
            # 走勢圖分頁：底下每個子分頁各自算圖表／統計／標頭，
            # 分頁本身的標頭沿用第一個子分頁的（切到子分頁後前端會立刻換掉）。
            for m in p["members"]:
                df = m["load"]()
                fig_light = m["figure"](df, dark=False, showlegend=False)
                fig_dark = m["figure"](df, dark=True, showlegend=False)

                charts[m["id"]] = _chart_entry(m["id"], fig_light, fig_dark, m["item_label"])
                stats[m["id"]] = _stats(m)
                head[m["id"]] = {
                    "title": m["title"],
                    "meta": f'{m["meta"]}<br>最後更新日：{stats[m["id"]]["latest"]}',
                }
            head[p["id"]] = head[p["members"][0]["id"]]
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

    # 總覽「走勢」子分頁：完整圖＋精簡卡片
    frames = {}
    for m in TREND_CHARTS:
        df = m["load"]()
        frames[m["id"]] = df
        charts[m["id"]] = _chart_entry(m["id"], m["figure"](df, dark=False, showlegend=False),
                                       m["figure"](df, dark=True, showlegend=False), m["item_label"])
        stats[m["id"]] = _stats(m)
        head[m["id"]] = {"title": m["title"],
                         "meta": f'{m["meta"]}<br>最後更新日：{stats[m["id"]]["latest"]}'}
    (SITE_DIR / "data").mkdir(parents=True, exist_ok=True)
    (SITE_DIR / "data" / "trend.json").write_text(
        json.dumps(trend_cards.build(TREND_CHARTS, frames), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    if isinstance(panel_data.get("market"), dict):
        panel_data["market"]["trend"] = [
            {"id": m["id"], "tab": m["tab"], "title": head[m["id"]]["title"], "meta": head[m["id"]]["meta"]}
            for m in TREND_CHARTS]

    head["settings"] = {"title": "設定", "meta": "外觀、資料集資訊與版本"}

    built = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M (UTC+8)")
    first = PANELS[0]

    html = (
        TPL.replace("__GROUPBAR__", _groupbar_html())
           .replace("__GROUPS__", json.dumps(_default_groups(), ensure_ascii=False))
           .replace("__TAB_LABELS__", json.dumps(
               {p["id"]: p["tab"] for p in PANELS}, ensure_ascii=False))
           .replace("__CHART_PANELS__", _panels_html(panel_data, head))
           .replace("__SETTINGS_CARDS__", _settings_cards(stats))
           .replace("__TABBAR__", _tabbar_html())
           .replace("__SETTINGS_ICON__", SETTINGS_ICON)
           .replace("__CHARTS__", json.dumps(_write_charts(charts), ensure_ascii=False,
                                             separators=(",", ":")))
           .replace("__HEAD__", json.dumps(head, ensure_ascii=False))
           .replace("__PANEL_IDS__", json.dumps([p["id"] for p in PANELS]))
           .replace("__TITLE0__", head[first["id"]]["title"])
           .replace("__META0__", head[first["id"]]["meta"])
           .replace("__BUILT__", built)
           .replace("__VERSION__", __version__)
    )

    # 行首縮排只是為了原始碼好讀，對畫面沒有作用，拿掉可以省下六、七十 KB。
    # 頁面裡沒有 <pre>，唯一的 <textarea>（筆記）是空的，所以可以放心整份處理。
    html = re.sub(r"\n[ \t]+", "\n", html)
    OUTPUT.write_text(html, encoding="utf-8")
    _copy_web()
    _write_news_bodies((panel_data.get("info") or {}).get("news", {}))
    _write_stock_data(panel_data.get("stock", {}))
    return OUTPUT


def _write_stock_data(data: dict) -> None:
    """個股的三個資料集另存 site/stock/{資料集}.json，進子分頁時才載。

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
    """新聞內文另存 site/news/{來源}.json，讀者點開某一則時才下載。"""
    if not data:
        return
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    written = set()
    for source_id, bodies in news_bodies(data).items():
        path = NEWS_DIR / f"{source_id}.json"
        path.write_text(json.dumps(bodies, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
        written.add(path.name)
    for source_id, rows in news_lists(data).items():
        path = NEWS_DIR / f"list-{source_id}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
        written.add(path.name)
    for stale in NEWS_DIR.glob("*.json"):        # 來源移除後不要留著孤兒檔
        if stale.name not in written:
            stale.unlink()


if __name__ == "__main__":
    path = build()
    print(f"[完成] 已產生 {path}（{path.stat().st_size // 1024} KB）")
