"""
底部分頁的版面（v0.3.063 起）：原本的「總覽」拆成今日、市場、選股，新聞＋行事曆合成資訊

    今日   決策首頁（沒有子分頁）
    市場   台股／類股／籌碼／國際／走勢／總經
    選股   強勢股／強勢紀錄／條件選股／訊號績效
    個股   查詢／我的持股／營收／重訊／財報
    資訊   熱門分析／重點新聞／各家新聞（孫分頁是各來源）／行事曆

各子分頁的內容沿用原本的產生函式（overview_render、stock_render、news_render、calendar_render），
這裡只負責分配到哪個分頁、排順序、產生子分頁列；data-sub 不變，前端程式照舊用它找面板。
"""
from __future__ import annotations

import re
from html import escape

import pandas as pd

import calendar_render
import news_render
import overview_render
import stock_render

# 原本總覽子分頁的頁面標題與說明（id → (標題, 說明)）
_OV = {sid: (title, meta) for sid, _label, title, meta in overview_render.SUBTABS}
_OV["live"] = ("盤中強勢族群", "開盤後每分鐘更新：當日強勢族群與連動個股")
_ST = {sid: (title, meta) for sid, _label, title, meta in stock_render.SUBTABS}

# 各分頁的子分頁：(id, 標籤)
MARKET = [("market", "台股"), ("sectors", "類股"), ("flows", "籌碼"), ("global", "國際"),
          ("trend", "走勢"), ("macro", "總經"), ("live", "盤中")]
# 盤中：設定好盤中服務才顯示（intraday.js 會把它移到第一個）
HIDDEN_SUBS = {"live"}
PICKS = [("momentum", "強勢股"), ("record", "強勢紀錄"), ("screen", "條件選股"), ("perf", "訊號績效")]
STOCK = [("query", "查詢"), ("hold", "我的持股"), ("revenue", "營收"), ("announce", "重訊"),
         ("income", "財報")]
INFO = [("hot", "熱門分析"), ("digest", "重點新聞"), ("sources", "各家新聞"), ("calendar", "行事曆")]

CAL_META = ("資料來源：FXStreet、證交所、櫃買中心　·　中／高影響總經事件與台股事件"
            "　·　時間為台北時間（UTC+8）")
_OPEN = re.compile(r'<div class="(subpanel[^"]*)" data-sub="(\w+)"( hidden)?>')


def _sub_of(pane: str) -> str:
    m = _OPEN.search(pane)
    return m.group(2) if m else ""


def _show(pane: str, visible: bool) -> str:
    """把子分頁外框的 hidden 調成要的狀態（只改第一個開頭標籤）。"""
    return _OPEN.sub(lambda m: f'<div class="{m.group(1)}" data-sub="{m.group(2)}"'
                               f'{"" if visible else " hidden"}>', pane, count=1)


def _bar(items: list[tuple], meta: dict, label: str) -> str:
    btns = []
    for i, (sid, text) in enumerate(items):
        title, desc = meta.get(sid, (text, ""))
        btns.append(f'      <button type="button" class="subtab" data-sub="{sid}"'
                    f' data-title="{escape(title)}" data-meta="{escape(desc)}"'
                    f' aria-selected="{"true" if i == 0 else "false"}"'
                    f'{" hidden" if sid in HIDDEN_SUBS else ""}>{escape(text)}</button>')
    return (f'  <div class="subtabs" role="tablist" aria-label="{escape(label)}">\n'
            + "\n".join(btns) + "\n  </div>")


def _assemble(items: list[tuple], panes: dict, meta: dict, label: str) -> str:
    body = [_show(panes[sid], i == 0) for i, (sid, _) in enumerate(items) if sid in panes]
    return _bar([x for x in items if x[0] in panes], meta, label) + "\n" + "\n".join(body)


def _overview_panes(data) -> dict:
    return {_sub_of(p): p for p in overview_render.panes(data)}


# ── 今日、市場、選股、個股 ─────────────────────────────────

def today_html(data) -> str:
    return _show(_overview_panes(data)["today"], True)


def market_html(data) -> str:
    return _assemble(MARKET, _overview_panes(data), _OV, "市場子分頁")


def picks_html(data) -> str:
    panes = _overview_panes(data)
    panes["screen"] = stock_render._screen_html()
    return _assemble(PICKS, panes, {**_OV, **_ST}, "選股子分頁")


def stock_html(data) -> str:
    panes = {
        "query": stock_render._query_html(),
        "hold": _overview_panes({})["hold"],
        "revenue": stock_render._list_html("revenue", "篩選公司或產業"),
        "announce": stock_render._list_html("announce", "篩選公司或主旨"),
        "income": stock_render._list_html("income", "篩選公司"),
    }
    meta = {**_ST, "query": ("個股", _ST["query"][1]), "hold": _OV["hold"]}
    return _assemble(STOCK, panes, meta, "個股子分頁")


def market_stats(data) -> dict:
    info = data or {}
    return {"latest": info.get("latest", "無資料"),
            "rows_html": [("最新交易日", info.get("latest", "無資料")),
                          ("內容", "台股、類股、籌碼、國際、走勢、總經")]}


def picks_stats(data) -> dict:
    info = data or {}
    return {"latest": info.get("latest", "無資料"),
            "rows_html": [("最新交易日", info.get("latest", "無資料")),
                          ("內容", "強勢股、強勢紀錄、條件選股、訊號績效")]}


# ── 資訊：新聞＋行事曆 ─────────────────────────────────────

def info_html(data: dict) -> str:
    news = data.get("news") or {}
    df = news.get("news", pd.DataFrame())
    cal = data.get("cal", pd.DataFrame())
    grand = []
    for i, s in enumerate(news_render.SOURCES):
        grand.append(f'        <button type="button" class="grandtab" data-grand="{s["id"]}"'
                     f' data-title="{escape(s["label"])}" data-meta="{escape(news_render.META)}"'
                     f' aria-selected="{"true" if i == 0 else "false"}">{escape(s["label"])}</button>')
    lists = []
    for i, s in enumerate(news_render.SOURCES):
        part = df[df["source"] == s["id"]] if not df.empty else df
        lists.append(f'    <div class="grandpanel" data-grand="{s["id"]}"{"" if i == 0 else " hidden"}>\n'
                     f'{news_render._source_html(s, part)}\n    </div>')
    sources = ('  <div class="subpanel" data-sub="sources" hidden>\n'
               '    <div class="grandtabs" role="tablist" aria-label="新聞來源">\n'
               + "\n".join(grand) + "\n    </div>\n" + "\n".join(lists) + "\n  </div>")
    cal_latest = calendar_render.stats(cal).get("latest", "")
    calendar = ('  <div class="subpanel" data-sub="calendar" hidden>\n'
                + calendar_render.panel_html(cal) + "\n  </div>")
    panes = {"hot": news_render._hot_html(news.get("hot") or {}),
             "digest": news_render._digest_html(df), "sources": sources, "calendar": calendar}
    meta = {"hot": ("熱門新聞分析", news_render.HOT_META),
            "digest": ("新聞重點", news_render.DIGEST_META),
            "sources": ("各家新聞", news_render.META),
            "calendar": ("財經行事曆", CAL_META + (f"<br>最後更新日：{cal_latest}" if cal_latest else ""))}
    return _assemble(INFO, panes, meta, "資訊子分頁")


def info_stats(data: dict) -> dict:
    n = news_render.stats(data.get("news") or {})
    c = calendar_render.stats(data.get("cal", pd.DataFrame()))
    rows = [("新聞最後更新", n.get("latest", "無資料")),
            ("新聞來源", f"{n.get('sources', 0)} 個"),
            ("行事曆事件", f"{c.get('rows', 0)} 筆（{c.get('range', '無資料')}）")]
    return {"latest": n.get("latest", "無資料"), "rows_html": rows}
