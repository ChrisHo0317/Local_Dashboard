"""
個股分頁的靜態 HTML

五個子分頁：

    個股   深度頁：K 線、三大法人、融資、月營收、EPS、本益比河流圖、集保、重訊
    選股   四個條件每天掃一次全市場的命中清單（全部「未驗證」：尚未回測）
    營收   上市櫃每月營業收入（最新一期）
    重訊   重大訊息，點開看全文
    財報   綜合損益表（最新一季，年初至今累計）

資料都是排程抓下來、產生頁面時整理好的 JSON（data/stock/{代號}.json、
data/screen.json、stock/{資料集}.json），進子分頁或查某一檔時才下載。
這裡只鋪空殼，內容由前端 JS 依 JSON 產生。
"""
from html import escape

import pandas as pd

META = "資料來源：證交所、櫃買、公開資訊觀測站、集保　·　盤後更新"

# (id, 標籤, 頁面標題, 說明)
SUBTABS = [
    ("query", "個股", "個股",
     "上市櫃都查得到　·　盤後資料"),
    ("screen", "選股", "選股（未驗證）",
     "每天盤後掃描全市場　·　尚未回測，只當觀察名單"),
    ("revenue", "營收", "每月營收",
     "資料來源：公開資訊觀測站　·　上市櫃公司每月營業收入（最新一期）"),
    ("announce", "重訊", "重大訊息",
     "資料來源：公開資訊觀測站　·　點標題可看全文"),
    ("income", "財報", "季報損益",
     "資料來源：公開資訊觀測站　·　綜合損益表，年初至今累計（不是單季）"),
]


def _roc_month(value: str) -> str:
    """民國年月 11507 → 115/07。"""
    value = str(value)
    return f"{value[:3]}/{value[3:]}" if len(value) == 5 else value


def _roc_date(value: str) -> str:
    """民國日期 1150903 → 2026-09-03（與其他分頁的「最後更新日」同一種寫法）。"""
    value = str(value)
    if len(value) == 7 and value.isdigit():
        return f"{int(value[:3]) + 1911}-{value[3:5]}-{value[5:]}"
    return value


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
    """個股深度頁：搜尋框、標頭數字、區間鈕、五張圖、重訊時間軸。"""
    sections = [
        ("sd-price", "價量與籌碼", "K 線與 5／20／60 日均線、成交量、三大法人買賣超、融資餘額共用時間軸"),
        ("sd-rev", "月營收", "近 36 個月，長條是營收（億元），折線是年增率"),
        ("sd-eps", "季 EPS 與利潤率", "近 12 季單季 EPS，折線是毛利率與營益率"),
        ("sd-pe", "本益比河流圖", "月底股價疊在歷史本益比區間帶上"),
        ("sd-tdcc", "千張大戶持股比例", "集保結算所每週公布，從 2026 年 9 月開始累積"),
    ]
    blocks = "".join(
        f'      <section class="sd-sec" data-sec="{sid}">\n'
        f'        <h3 class="sd-h">{title}</h3>\n'
        f'        <p class="sd-note">{note}</p>\n'
        f'        <div class="ichart ichart-{"lg" if sid == "sd-price" else "sm"}" id="{sid}"></div>\n'
        f'      </section>\n'
        for sid, title, note in sections
    )
    return (
        '  <div class="subpanel" data-sub="query">\n'
        '    <div class="sq-box">\n'
        '      <input class="sq-input" id="sd-input" type="search" inputmode="search"'
        ' placeholder="輸入股號或公司名，例如 2330 或 環球晶"'
        ' aria-label="股票代號或公司名" autocomplete="off">\n'
        '      <div class="sq-suggest" hidden role="listbox"></div>\n'
        '    </div>\n'
        '    <div class="sd-watch" hidden></div>\n'
        '    <p class="sq-hint">輸入代號或名稱，上市、上櫃都查得到。也可以點上面的自選股。</p>\n'
        '    <div class="sd" hidden>\n'
        '      <div class="sd-top">\n'
        '        <div>\n'
        '          <div class="sq-name"></div>\n'
        '          <div class="sd-sub"></div>\n'
        '          <div class="sd-tags"></div>\n'
        '        </div>\n'
        '        <a class="sd-edit" target="_blank" rel="noopener">編輯自選清單 ↗</a>\n'
        '      </div>\n'
        '      <div class="sq-stats"></div>\n'
        '      <div class="sq-range" role="group" aria-label="顯示區間">\n'
        '        <button type="button" class="chip" data-days="22" aria-pressed="false">1 個月</button>\n'
        '        <button type="button" class="chip" data-days="66" aria-pressed="true">3 個月</button>\n'
        '        <button type="button" class="chip" data-days="130" aria-pressed="false">6 個月</button>\n'
        '        <button type="button" class="chip" data-days="0" aria-pressed="false">1 年</button>\n'
        '      </div>\n'
        '      <p class="sd-note zoom-hint"></p>\n'
        f'{blocks}'
        '      <section class="sd-sec" data-sec="sd-ann">\n'
        '        <h3 class="sd-h">重大訊息與法說會</h3>\n'
        '        <ul class="sd-ann"></ul>\n'
        '      </section>\n'
        '    </div>\n'
        '  </div>'
    )


def _screen_html() -> str:
    """選股：每個條件一張卡，內容由 JS 讀 data/screen.json 產生。"""
    return (
        '  <div class="subpanel" data-sub="screen" hidden>\n'
        '    <p class="scr-warn"><b>未驗證</b>　這些條件還沒有回測過，只能當觀察名單，'
        '不能當成買賣依據。</p>\n'
        '    <div class="scr-body"><p class="cal-empty">載入中…</p></div>\n'
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
        _screen_html(),
        _list_html("revenue", "篩選公司或產業"),
        _list_html("announce", "篩選公司或主旨"),
        _list_html("income", "篩選公司"),
    ])


def datasets(data: dict) -> dict:
    """輸出成 site/stock/{資料集}.json 的內容，進子分頁時才載。"""
    out = {}
    for key in ("revenue", "announce", "income"):
        df = data.get(key, pd.DataFrame())
        out[key] = [] if df.empty else df.to_dict("records")
    return out
