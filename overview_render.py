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
    ("today", "今日重點", "今日重點", "摘要、市場溫度、主流族群、自選股警示與市場數字"),
    ("market", "大盤", "大盤", "加權指數與法人買賣超（估算）"),
    ("sectors", "類股", "類股", "面積＝成交值，顏色＝所選區間的漲跌（紅漲綠跌）"),
    ("momentum", "強勢股", "強勢股", "哪些股票漲得越來越快：強度 × 加速度"),
    ("record", "強勢紀錄", "強勢紀錄", "每天強勢股的上漲原因、是否族群連動與同族群個股"),
    ("perf", "訊號績效", "訊號績效", "每個訊號之後 5／10／20 日的報酬、勝率與超額報酬"),
    ("flows", "法人籌碼", "法人籌碼", "外資、投信買賣超排行　·　期貨未平倉"),
]


def stats(data) -> dict:
    """設定頁的資料卡：由 intel_build 算好後塞進 data。"""
    info = data or {}
    rows = [
        ("最新交易日", info.get("latest", "無資料")),
        ("個股資料", f"{info.get('stocks', 0):,} 檔"),
        ("自選股", f"{info.get('watch', 0)} 檔"),
    ]
    q = info.get("quality") or {}
    issues = [c for c in q.get("checks", []) if c.get("level") in ("error", "warn", "info")]
    label = {"error": "錯誤", "warn": "注意", "info": "提醒"}
    rows.append(("資料品質", (f"{len(issues)} 項待處理" if issues else "正常")
                 + (f"（{q['generated']} 檢查）" if q.get("generated") else "")))
    for c in issues[:6]:
        rows.append((label[c["level"]], c["title"]))
    return {"latest": info.get("latest", "無資料"), "rows_html": rows}


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
        '    <section class="ck" aria-label="決策摘要">\n'
        '      <div class="ck-digest ov-card"></div>\n'
        '      <div class="ck-temp ov-card">\n'
        '        <div class="ck-gauge"></div>\n'
        '        <div class="ck-tiles"></div>\n'
        '        <div class="ichart" id="ov-temp"></div>\n'
        '      </div>\n'
        '      <div class="ck-grid">\n'
        '        <section class="ov-card ck-groups"><h3>主流族群</h3><div class="ov-body"></div></section>\n'
        '        <section class="ov-card ck-alerts"><h3>自選股警示</h3><div class="ov-body"></div></section>\n'
        '        <section class="ov-card ck-perf"><h3>訊號績效（持有 20 日、超額報酬）</h3>'
        '<div class="ov-body"></div></section>\n'
        '        <section class="ov-card ck-next"><h3>接下來兩天</h3><div class="ov-body"></div></section>\n'
        '      </div>\n'
        '      <p class="ck-quality sd-note"></p>\n'
        '    </section>\n'
        '    <h3 class="sd-h">市場數字</h3>\n'
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
        '    <div class="sec-bar">\n'
        '      <div class="mo-ext sec-period" role="group" aria-label="只看最極端">\n'
        '        <button type="button" class="chip" data-ext="0" aria-pressed="true">全部</button>\n'
        '        <button type="button" class="chip" data-ext="0.05" aria-pressed="false">最極端 5%</button>\n'
        '        <button type="button" class="chip" data-ext="0.1" aria-pressed="false">10%</button>\n'
        '        <button type="button" class="chip" data-ext="0.2" aria-pressed="false">20%</button>\n'
        '      </div>\n'
        '    </div>\n'
        '    <p class="sd-note mo-ext-note" hidden>最極端＝強度與加速度各自扣掉全體中位數、換成同一把尺後，'
        '離中心最遠的那幾 %（暴漲、暴跌、急轉強、急轉弱都算），比例以目前產業與成交值門檻篩完的檔數為準。'
        '播放時每一天各自重算，進出名單的點會淡入淡出；下方排行與曲線看的是今天的名單。</p>\n'
        '    <div class="mo-play">\n'
        '      <button type="button" class="chip mo-btn" aria-label="播放近 20 個交易日的變化">▶ 播放</button>\n'
        '      <input type="range" class="mo-slider" min="0" max="0" step="any" value="0"'
        ' aria-label="日期">\n'
        '      <span class="mo-date"></span>\n'
        '    </div>\n'
        '    <p class="sd-note zoom-hint"></p>\n'
        '    <div class="ichart ichart-lg" id="ov-momentum"></div>\n'
        '    <div class="mo-pick" hidden></div>\n'
        '    <h3 class="sd-h">越來越強排行</h3>\n'
        '    <p class="sd-note">條件：近 20 日上漲，而且近 5 日漲得比前 5 日多。點表頭可以排序；'
        '點一列看近五日新聞與最可能的上漲原因。</p>\n'
        '    <p class="mo-count sec-sum"></p>\n'
        '    <p class="sd-note mo-news-meta" hidden></p>\n'
        '    <div class="mo-table"></div>\n'
        '    <h3 class="sd-h">前 10 名的近 20 日累積漲幅</h3>\n'
        '    <p class="sd-note">以 20 個交易日前的收盤為 0%；灰色虛線是加權指數。曲線越往上翹，代表最近漲得越快。</p>\n'
        '    <div class="ichart ichart-sm" id="ov-mo-lines"></div>\n'
        '  </div>',
        '  <div class="subpanel ov" data-sub="record" hidden>\n'
        '    <p class="ov-asof"></p>\n'
        '    <p class="mo-explain">每天盤後（開盤前再用新的新聞補一次）記下強勢股（越來越強前 60 檔＋自選股）'
        '最可能的上漲原因。<b>族群連動</b>：新聞說是族群行情、而且至少一檔同族群股票走勢同步'
        '（近 5 日上漲、近 20 日每日漲跌相關係數 ≥ 0.6）；或同一天有 3 檔以上強勢股被歸到同一族群。</p>\n'
        '    <h3 class="sd-h">族群輪動</h3>\n'
        '    <p class="sd-note rec-heat-note"></p>\n'
        '    <div class="ichart" id="ov-record-heat"></div>\n'
        '    <div class="sec-bar">\n'
        '      <select class="rec-date sec-pick" aria-label="日期"></select>\n'
        '      <input class="rec-search sec-pick" type="search" placeholder="查股票代號或名稱"'
        ' aria-label="查股票的上榜紀錄">\n'
        '    </div>\n'
        '    <p class="rec-sum sec-sum"></p>\n'
        '    <div class="rec-body"></div>\n'
        '  </div>',
        '  <div class="subpanel ov" data-sub="perf" hidden>\n'
        '    <p class="ov-asof"></p>\n'
        '    <p class="mo-explain">每個訊號「新進榜」的隔天開盤買進，持有 5／10／20 個交易日後以收盤計算；'
        '價格已還原權值，報酬已扣來回成本（手續費＋證交稅）。<b>超額報酬</b>＝訊號報酬 − 同期市場平均'
        '（均量 1 億以上股票等權）。<b>判讀</b>：至少 30 次，而且超額報酬的 t 值 ≥ 2 才算「優於大盤」。'
        '回測用過去一年的資料、只用當時就知道的資訊；追蹤是從開始記錄那天起累積。</p>\n'
        '    <div class="sec-bar"><div class="pf-h sec-period" role="group" aria-label="持有天數">\n'
        '      <button type="button" class="chip" data-h="5" aria-pressed="false">持有 5 日</button>\n'
        '      <button type="button" class="chip" data-h="10" aria-pressed="false">10 日</button>\n'
        '      <button type="button" class="chip" data-h="20" aria-pressed="true">20 日</button>\n'
        '    </div></div>\n'
        '    <h3 class="sd-h">平均超額報酬</h3>\n'
        '    <div class="ichart" id="ov-perf-bars"></div>\n'
        '    <div class="pf-table"></div>\n'
        '    <h3 class="sd-h">每月平均超額報酬</h3>\n'
        '    <p class="sd-note">看訊號是一直有效，還是只在某幾個月有用。點圖例可以隱藏某條線。</p>\n'
        '    <div class="ichart" id="ov-perf-monthly"></div>\n'
        '    <h3 class="sd-h pf-recent-h">最近的訊號</h3>\n'
        '    <p class="sd-note">點上面表格的一列切換訊號；點股票打開個股頁。</p>\n'
        '    <div class="pf-recent"></div>\n'
        '    <p class="sd-note">回測沒有考慮滑價、漲停買不到、已下市的股票；同一檔短期內反覆進榜時事件會重疊，'
        't 值會偏樂觀。結果只能當參考，不是投資建議。</p>\n'
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
