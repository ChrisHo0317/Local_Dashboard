"""
個股分頁的靜態 HTML

四個子分頁：

    查詢   輸入股號或公司名，當場向證交所查行情與評價指標（真的即時）
    營收   上市公司每月營業收入
    重訊   重大訊息，點開看全文
    財報   綜合損益表（單季）

只有「查詢」是即時的：證交所的 www.twse.com.tw/rwd/ 端點帶
Access-Control-Allow-Origin: *，頁面上的 JS 可以直接呼叫。另外三個
來自公開資訊觀測站的開放資料，那組沒有 CORS 標頭，瀏覽器連不了，
所以改成排程抓下來存成 docs/stock/{資料集}.json，進子分頁時才載。

表格內容全部由 JS 依 JSON 產生，這裡只鋪空殼。
"""
from html import escape

import pandas as pd

META = "資料來源：臺灣證券交易所　·　查詢為即時，其餘為每日更新"

# (id, 標籤, 頁面標題, 說明)
SUBTABS = [
    ("query", "查詢", "個股查詢",
     "資料來源：臺灣證券交易所　·　輸入股號或公司名，當場查詢"),
    ("revenue", "營收", "每月營收",
     "資料來源：公開資訊觀測站　·　上市公司每月營業收入"),
    ("announce", "重訊", "重大訊息",
     "資料來源：公開資訊觀測站　·　點標題可看全文"),
    ("income", "財報", "季報損益",
     "資料來源：公開資訊觀測站　·　綜合損益表（單季）"),
]


def _roc_month(value: str) -> str:
    """民國年月 11507 → 115/07。"""
    value = str(value)
    return f"{value[:3]}/{value[3:]}" if len(value) == 5 else value


def _roc_date(value: str) -> str:
    """民國日期 1150903 → 115/09/03。"""
    value = str(value)
    return f"{value[:3]}/{value[3:5]}/{value[5:]}" if len(value) == 7 else value


def stats(data: dict) -> dict:
    """設定分頁用的摘要。"""
    rev = data.get("revenue", pd.DataFrame())
    ann = data.get("announce", pd.DataFrame())
    inc = data.get("income", pd.DataFrame())
    if rev.empty and ann.empty and inc.empty:
        return {"rows": 0, "range": "無資料", "shown": 0, "latest": "無資料",
                "companies": 0}

    months = sorted({m for m in rev["month"] if m}) if not rev.empty else []
    dates = sorted({d for d in ann["date"] if d}) if not ann.empty else []
    quarter = ""
    if not inc.empty:
        pairs = sorted({(r["year"], r["quarter"]) for _, r in inc.iterrows()
                        if r["year"] and r["quarter"]})
        if pairs:
            quarter = f"{pairs[-1][0]} 年第 {pairs[-1][1]} 季"

    span = []
    if months:
        span.append(f"營收 {_roc_month(months[-1])}")
    if quarter:
        span.append(f"財報 {quarter}")
    return {
        "rows": len(rev) + len(ann) + len(inc),
        "companies": int(rev["code"].nunique()) if not rev.empty else 0,
        "range": "　·　".join(span) if span else "無資料",
        "shown": len(rev) + len(ann) + len(inc),
        "latest": _roc_date(dates[-1]) if dates else (
            _roc_month(months[-1]) if months else "無資料"),
    }


def _subtabs_html() -> str:
    btns = []
    for i, (sid, label, title, meta) in enumerate(SUBTABS):
        btns.append(
            f'      <button type="button" class="subtab" data-sub="{sid}"'
            f' data-title="{escape(title)}" data-meta="{escape(meta)}"'
            f' aria-selected="{"true" if i == 0 else "false"}">{label}</button>'
        )
    return ('  <div class="subtabs" role="tablist" aria-label="個股子分頁">\n'
            + "\n".join(btns) + "\n  </div>")


def _query_html() -> str:
    """即時查詢：輸入框、建議清單、區間鈕、指標列、走勢圖。"""
    return (
        '  <div class="subpanel" data-sub="query">\n'
        '    <div class="sq-box">\n'
        '      <input class="sq-input" type="search" inputmode="search"'
        ' placeholder="輸入股號或公司名，例如 2330 或 台積電"'
        ' aria-label="股票代號或公司名" autocomplete="off">\n'
        '      <div class="sq-suggest" hidden role="listbox"></div>\n'
        '    </div>\n'
        '    <div class="sq-range" role="group" aria-label="查詢區間" hidden>\n'
        '      <button type="button" class="chip" data-months="3" aria-pressed="true">3 個月</button>\n'
        '      <button type="button" class="chip" data-months="6" aria-pressed="false">6 個月</button>\n'
        '      <button type="button" class="chip" data-months="12" aria-pressed="false">1 年</button>\n'
        '    </div>\n'
        '    <p class="sq-hint">還沒查詢。輸入股號或公司名，資料當場向證交所取得。</p>\n'
        '    <div class="sq-result" hidden>\n'
        '      <div class="sq-name"></div>\n'
        '      <div class="sq-stats"></div>\n'
        '      <div class="chart sq-chart" id="chart-stockquery"></div>\n'
        '    </div>\n'
        '  </div>'
    )


def _list_html(sub: str, hint: str) -> str:
    """營收／重訊／財報共用的空殼：搜尋框 + 由 JS 填的內容。"""
    return (
        f'  <div class="subpanel" data-sub="{sub}" hidden>\n'
        f'    <div class="sq-box">\n'
        f'      <input class="sl-filter" type="search" inputmode="search"'
        f' placeholder="{escape(hint)}" aria-label="{escape(hint)}" autocomplete="off">\n'
        f'    </div>\n'
        f'    <div class="sl-body" data-set="{sub}">\n'
        f'      <p class="cal-empty">載入中…</p>\n'
        f'    </div>\n'
        f'  </div>'
    )


def panel_html(data: dict) -> str:
    return "\n".join([
        _subtabs_html(),
        _query_html(),
        _list_html("revenue", "篩選公司或產業"),
        _list_html("announce", "篩選公司或主旨"),
        _list_html("income", "篩選公司"),
    ])


def datasets(data: dict) -> dict:
    """輸出成 docs/stock/{資料集}.json 的內容，進子分頁時才載。"""
    out = {}
    for key in ("revenue", "announce", "income"):
        df = data.get(key, pd.DataFrame())
        out[key] = [] if df.empty else df.to_dict("records")
    return out
