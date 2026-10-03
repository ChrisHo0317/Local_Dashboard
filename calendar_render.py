"""
把行事曆事件轉成靜態 HTML（表格）

時間一律換算成台北時間（UTC+8，台灣沒有日光節約時間，直接用固定位移即可，
不必依賴系統的 tz 資料庫）。事件名稱、國別、影響程度由 calendar_i18n 中文化。

輸出成單一 <table>，每天一個 <tbody>，欄位固定寬度，各天的欄位才會對齊。
每列帶 data-ts（epoch 毫秒），前端據此插入「現在」標示線 —— 頁面會被 CDN
快取，時間相關的東西一律在瀏覽器端算，不能在產生頁面時寫死。

只輸出一段時間窗內的事件：CSV 會逐週累積下去，全部塞進頁面會愈來愈肥。
"""
from datetime import datetime, timedelta, timezone
from html import escape

import pandas as pd

from calendar_i18n import IMPACT_ORDER, translate_country, translate_impact, translate_title

TAIPEI = timezone(timedelta(hours=8))

# 顯示窗：往回幾天、往後幾天
PAST_DAYS = 3
FUTURE_DAYS = 45

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

IMPACT_CLASS = {"High": "i-high", "Medium": "i-mid", "Low": "i-low", "Holiday": "i-hol",
                "TW": "i-tw"}


def _local(ts: pd.Timestamp) -> datetime:
    return ts.tz_convert(TAIPEI).to_pydatetime()


def window(df: pd.DataFrame) -> pd.DataFrame:
    """取出要顯示的時間窗內事件。"""
    if df.empty or "_ts" not in df:
        return df
    now = datetime.now(TAIPEI)
    lo = pd.Timestamp(now.date() - timedelta(days=PAST_DAYS), tz=TAIPEI)
    hi = pd.Timestamp(now.date() + timedelta(days=FUTURE_DAYS + 1), tz=TAIPEI)
    return df[(df["_ts"] >= lo) & (df["_ts"] < hi)]


def stats(df: pd.DataFrame) -> dict:
    """設定分頁用的摘要。"""
    if df.empty or "_ts" not in df:
        return {"rows": 0, "range": "無資料", "shown": 0, "latest": "無資料"}
    first = _local(df["_ts"].min()).strftime("%Y-%m-%d")
    last = _local(df["_ts"].max()).strftime("%Y-%m-%d")
    return {
        "rows": len(df),
        "range": f"{first} ～ {last}",
        "shown": len(window(df)),
        "latest": last,
    }


def _num(text: str):
    try:
        return float(str(text).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def surprise(actual: str, forecast: str) -> int:
    """公布值和預估比：1 高於、-1 低於、0 相同或無法比。"""
    a, f = _num(actual), _num(forecast)
    if a is None or f is None or a == f:
        return 0
    return 1 if a > f else -1


def _actual(e) -> str:
    """公布值：▲▼ 是和預估比的高低；顏色是來源判斷對經濟偏好（紅）或偏壞（綠）。"""
    actual = str(e.get("actual", "") or "")
    if not actual:
        return ""
    s = surprise(actual, e.get("forecast", ""))
    better = str(e.get("better", "") or "")
    cls = {"1": " cal-good", "0": " cal-bad"}.get(better, "")
    arrow = {1: "▲", -1: "▼"}.get(s, "")
    tip = {1: "高於預期", -1: "低於預期", 0: "符合預期" if e.get("forecast") else "沒有預估值"}[s]
    tip += {"1": "（對經濟偏正面）", "0": "（對經濟偏負面）"}.get(better, "")
    return f'<b class="cal-act{cls}" title="{tip}">{escape(actual)}{arrow}</b>'


def panel_html(df: pd.DataFrame) -> str:
    """產生行事曆分頁的內容（不含 <section> 外框）。"""
    # 每個影響程度一顆，各自開關（不是互斥的「以上」級距）。
    # 只列資料裡真的有的等級 —— 來源只給中／高，多一顆按了沒反應的「低」很怪。
    present = {IMPACT_ORDER.get(v, 1) for v in window(df)["impact"]} if not df.empty else set()
    levels = [(3, "高", "i-high"), (2, "中", "i-mid"),
              (1, "低", "i-low"), (0, "假日", "i-hol"), (4, "台股", "i-tw")]
    chips = "".join(
        f'      <button type="button" class="chip chip-tick" data-impact="{rank}"'
        f' aria-pressed="true"><span class="dot {cls}"></span>{label}</button>\n'
        for rank, label, cls in levels if rank in present
    )
    head = (
        '  <div class="cal-bar">\n'
        '    <div class="cal-filter" role="group" aria-label="影響程度篩選">\n'
        + chips +
        '    </div>\n'
        '    <div class="cal-clock" id="cal-clock" aria-live="off">—</div>\n'
        '  </div>'
    )

    # 月曆格狀圖：完全由前端 JS 產生（今天是哪一天、月份怎麼排都是瀏覽器端算的），
    # 這裡只留容器殼，理由與「現在時間標示線」相同——頁面會被 CDN 快取。
    month_grid = (
        '  <div class="cal-month" id="cal-month">\n'
        '    <div class="cal-month-head">\n'
        '      <button type="button" class="iconbtn cal-month-prev" aria-label="上個月">&#8249;</button>\n'
        '      <span class="cal-month-label">—</span>\n'
        '      <button type="button" class="iconbtn cal-month-next" aria-label="下個月">&#8250;</button>\n'
        '    </div>\n'
        '    <div class="cal-month-wd">\n'
        + "".join(f'      <span>{w}</span>\n' for w in WEEKDAYS) +
        '    </div>\n'
        '    <div class="cal-month-grid"></div>\n'
        '  </div>'
    )

    view = window(df)
    if view.empty:
        return head + "\n" + month_grid + '\n  <p class="cal-empty">目前沒有事件資料。</p>'

    bodies = []
    for day, group in view.groupby(view["_ts"].dt.tz_convert(TAIPEI).dt.date, sort=True):
        label = f"{day.month}/{day.day:02d}（{WEEKDAYS[day.weekday()]}）"
        rows = [
            f'      <tr class="cal-day-row"><th colspan="6" scope="rowgroup">{label}</th></tr>'
        ]
        for _, e in group.iterrows():
            local = _local(e["_ts"])
            impact = e["impact"]
            rank = IMPACT_ORDER.get(impact, 1)
            # 來源把全日事件標成 00:00；那種顯示「全日」比顯示 00:00 清楚
            when = "全日" if (local.hour == 0 and local.minute == 0) else local.strftime("%H:%M")

            zh = translate_title(e["title"])
            en = e["title"]
            # 副標一行帶過國別與英文原名；查不到對照時 zh 就等於原文，不必重複顯示
            sub = escape(translate_country(e["country"]))
            if zh != en:
                sub += " · " + escape(en)

            rows.append(
                f'      <tr class="cal-row" data-impact="{rank}"'
                f' data-ts="{int(e["_ts"].timestamp() * 1000)}">\n'
                f'        <td class="cal-time">{when}</td>\n'
                f'        <td class="cal-imp"><span class="dot {IMPACT_CLASS.get(impact, "i-low")}"'
                f' title="影響 {translate_impact(impact)}"></span></td>\n'
                f'        <td class="cal-ev">\n'
                f'          <div class="cal-title">{escape(zh)}</div>\n'
                f'          <div class="cal-sub">{sub}</div>\n'
                f'        </td>\n'
                f'        <td class="cal-num">{_actual(e)}</td>\n'
                f'        <td class="cal-num">{escape(e["forecast"])}</td>\n'
                f'        <td class="cal-num">{escape(e["previous"])}</td>\n'
                f'      </tr>'
            )

        bodies.append(
            f'    <tbody class="cal-day" data-date="{day.isoformat()}">\n'
            + "\n".join(rows) + "\n    </tbody>"
        )

    table = (
        '  <table class="cal-table">\n'
        '    <thead>\n'
        '      <tr><th class="cal-time">時間</th><th class="cal-imp"><span class="sr">影響</span></th>'
        '<th class="cal-ev">事件</th><th class="cal-num">公布</th><th class="cal-num">預估</th>'
        '<th class="cal-num">前值</th></tr>\n'
        '    </thead>\n'
        + "\n".join(bodies) + "\n  </table>"
    )
    return head + "\n" + month_grid + "\n" + table
