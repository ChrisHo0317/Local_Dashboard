"""
總覽分頁的靜態 HTML

四個子分頁：

    今日重點   市場數字、自選股異動、近期事件、選股條件命中數、重點新聞
    大盤       加權指數一年走勢＋外資、投信買賣超（估算）與成交值
    類股       各產業成交值與漲跌（面積＝成交值，顏色＝漲跌，紅漲綠跌）
    法人籌碼   外資、投信買賣超排行，期貨三大法人未平倉

內容全部由前端讀 data/overview.json 產生，這裡只鋪空殼。
「今天」「本週」都是產生資料當下算好的；新聞排程每十分鐘會重建一次，所以不會舊太久。
"""
from html import escape

META = "資料來源：證交所、櫃買、期交所、集保　·　盤後更新"

# (id, 標籤, 頁面標題, 說明)。說明要短：手機上標頭只留兩三行，太長會被切掉
SUBTABS = [
    ("today", "今日重點", "今日重點", "市場數字、自選股、近期事件、重點新聞"),
    ("market", "大盤", "大盤", "加權指數與法人買賣超（估算）"),
    ("sectors", "類股", "類股", "面積＝成交值，顏色＝所選區間的漲跌（紅漲綠跌）"),
    ("flows", "法人籌碼", "法人籌碼", "外資、投信買賣超排行　·　期貨未平倉"),
]


def stats(data) -> dict:
    """設定頁的資料卡：由 intel_build 算好後塞進 data。"""
    info = data or {}
    return {
        "latest": info.get("latest", "無資料"),
        "rows_html": [
            ("最新交易日", info.get("latest", "無資料")),
            ("個股資料", f"{info.get('stocks', 0):,} 檔"),
            ("自選股", f"{info.get('watch', 0)} 檔"),
        ],
    }


def _range_chips(cls: str, default: int) -> str:
    """顯示區間鈕（交易日數；0＝全部）。"""
    opts = [(22, "1 個月"), (66, "3 個月"), (130, "6 個月"), (0, "1 年")]
    btns = "".join(
        f'      <button type="button" class="chip" data-days="{d}"'
        f' aria-pressed="{"true" if d == default else "false"}">{label}</button>\n'
        for d, label in opts)
    return (f'    <div class="sq-range {cls}" role="group" aria-label="顯示區間">\n'
            f'{btns}    </div>\n')


def panel_html(data) -> str:
    btns = []
    for i, (sid, label, title, meta) in enumerate(SUBTABS):
        btns.append(
            f'      <button type="button" class="subtab" data-sub="{sid}"'
            f' data-title="{escape(title)}" data-meta="{escape(meta)}"'
            f' aria-selected="{"true" if i == 0 else "false"}">{label}</button>'
        )
    subtabs = ('  <div class="subtabs" role="tablist" aria-label="總覽子分頁">\n'
               + "\n".join(btns) + "\n  </div>")
    panes = [
        '  <div class="subpanel ov" data-sub="today">\n'
        '    <p class="ov-asof"></p>\n'
        '    <div class="ov-kpis"></div>\n'
        '    <div class="ov-grid">\n'
        '      <section class="ov-card ov-watch"><h3>自選股今日異動</h3><div class="ov-body"></div></section>\n'
        '      <section class="ov-card ov-events"><h3>近期事件</h3><div class="ov-body"></div></section>\n'
        '      <section class="ov-card ov-signals"><h3>選股條件命中'
        ' <span class="tag-warn">未驗證</span></h3><div class="ov-body"></div></section>\n'
        '      <section class="ov-card ov-news"><h3>重點新聞</h3><div class="ov-body"></div></section>\n'
        '    </div>\n'
        '  </div>',
        '  <div class="subpanel ov" data-sub="market" hidden>\n'
        f'{_range_chips("ov-range", 130)}'
        '    <p class="sd-note zoom-hint"></p>\n'
        '    <div class="ichart ichart-lg" id="ov-market"></div>\n'
        '    <p class="sd-note">法人買賣超是用每一檔的買賣超股數乘以收盤價加總估算，'
        '與交易所公布的金額會有些微差距；總覽第一頁的數字是交易所公布的金額。</p>\n'
        '  </div>',
        '  <div class="subpanel ov" data-sub="sectors" hidden>\n'
        '    <p class="ov-asof"></p>\n'
        '    <div class="ichart ichart-lg" id="ov-sectors"></div>\n'
        '    <div class="sec-bar">\n'
        '      <div class="sec-period" role="group" aria-label="漲跌區間">\n'
        '        <button type="button" class="chip" data-period="0" aria-pressed="true">1 日</button>\n'
        '        <button type="button" class="chip" data-period="1" aria-pressed="false">5 日</button>\n'
        '        <button type="button" class="chip" data-period="2" aria-pressed="false">10 日</button>\n'
        '        <button type="button" class="chip" data-period="3" aria-pressed="false">20 日</button>\n'
        '        <button type="button" class="chip" data-period="4" aria-pressed="false">60 日</button>\n'
        '      </div>\n'
        '    </div>\n'
        '    <div class="sec-bar">\n'
        '      <select class="sec-pick" aria-label="產業"></select>\n'
        '      <div class="sec-sort" role="group" aria-label="排序">\n'
        '        <button type="button" class="chip" data-sort="turnover" aria-pressed="true">成交值</button>\n'
        '        <button type="button" class="chip" data-sort="up" aria-pressed="false">漲幅</button>\n'
        '        <button type="button" class="chip" data-sort="down" aria-pressed="false">跌幅</button>\n'
        '      </div>\n'
        '    </div>\n'
        '    <p class="sec-sum"></p>\n'
        '    <div class="sec-table"></div>\n'
        '  </div>',
        '  <div class="subpanel ov" data-sub="flows" hidden>\n'
        '    <div class="ov-flow-tabs" role="group" aria-label="法人">\n'
        '      <button type="button" class="chip" data-flow="fi" aria-pressed="true">外資</button>\n'
        '      <button type="button" class="chip" data-flow="tr" aria-pressed="false">投信</button>\n'
        '    </div>\n'
        '    <div class="ov-flow-grid">\n'
        '      <section class="ov-card"><h3>買超前 20</h3><div class="ov-flow" data-side="buy"></div></section>\n'
        '      <section class="ov-card"><h3>賣超前 20</h3><div class="ov-flow" data-side="sell"></div></section>\n'
        '    </div>\n'
        '    <h3 class="sd-h">期貨三大法人未平倉（臺股期貨，口）</h3>\n'
        '    <p class="sd-note">從 2026 年 9 月開始累積。</p>\n'
        '    <div class="ichart ichart-sm" id="ov-futures"></div>\n'
        '  </div>',
    ]
    return subtabs + "\n" + "\n".join(panes)
