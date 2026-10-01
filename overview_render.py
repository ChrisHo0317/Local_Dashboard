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
    ("momentum", "強勢股", "強勢股", "哪些股票漲得越來越快：強度 × 加速度"),
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
        '  <div class="subpanel ov" data-sub="momentum" hidden>\n'
        '    <p class="ov-asof"></p>\n'
        '    <p class="mo-explain"><b>強度</b>＝近 20 日漲幅；<b>加速度</b>＝近 5 日漲幅 − 前 5 日漲幅'
        '（百分點）。右上角是已經在漲、而且最近漲得比之前更快的股票，也就是「越來越強」。'
        '前 10 名畫出最近 5 天的移動軌跡（箭頭是當天），往右上走代表還在變強。'
        '按「播放」看近 20 個交易日每一天的變化（軌跡跟著的是今天的前 10 名）。</p>\n'
        '    <div class="sec-bar">\n'
        '      <select class="mo-ind sec-pick" aria-label="產業"></select>\n'
        '      <div class="mo-liq sec-sort" role="group" aria-label="成交值門檻">\n'
        '        <button type="button" class="chip" data-min="0.3" aria-pressed="false">均量 0.3 億↑</button>\n'
        '        <button type="button" class="chip" data-min="1" aria-pressed="true">1 億↑</button>\n'
        '        <button type="button" class="chip" data-min="5" aria-pressed="false">5 億↑</button>\n'
        '      </div>\n'
        '    </div>\n'
        '    <div class="mo-play">\n'
        '      <button type="button" class="chip mo-btn" aria-label="播放近 20 個交易日的變化">▶ 播放</button>\n'
        '      <input type="range" class="mo-slider" min="0" max="0" step="1" value="0"'
        ' aria-label="日期">\n'
        '      <span class="mo-date"></span>\n'
        '    </div>\n'
        '    <p class="sd-note zoom-hint"></p>\n'
        '    <div class="ichart ichart-lg" id="ov-momentum"></div>\n'
        '    <div class="mo-pick" hidden></div>\n'
        '    <h3 class="sd-h">越來越強排行</h3>\n'
        '    <p class="sd-note">條件：近 20 日上漲，而且近 5 日漲得比前 5 日多。點表頭可以排序。</p>\n'
        '    <p class="mo-count sec-sum"></p>\n'
        '    <div class="mo-table"></div>\n'
        '    <h3 class="sd-h">前 10 名的近 20 日累積漲幅</h3>\n'
        '    <p class="sd-note">以 20 個交易日前的收盤為 0%；灰色虛線是加權指數。曲線越往上翹，代表最近漲得越快。</p>\n'
        '    <div class="ichart ichart-sm" id="ov-mo-lines"></div>\n'
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
