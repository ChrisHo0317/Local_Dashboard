"""
把行事曆事件轉成靜態 HTML

時間一律換算成台北時間（UTC+8，台灣沒有日光節約時間，直接用固定位移即可，
不必依賴系統的 tz 資料庫）。事件名稱、國別、影響程度由 calendar_i18n 中文化。

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

IMPACT_CLASS = {"High": "i-high", "Medium": "i-mid", "Low": "i-low", "Holiday": "i-hol"}


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


def panel_html(df: pd.DataFrame) -> str:
    """產生行事曆分頁的內容（不含 <section> 外框）。"""
    chips = (
        '  <div class="cal-filter" role="group" aria-label="影響程度篩選">\n'
        '    <button type="button" class="chip" data-min="0" aria-pressed="true">全部</button>\n'
        '    <button type="button" class="chip" data-min="2" aria-pressed="false">中以上</button>\n'
        '    <button type="button" class="chip" data-min="3" aria-pressed="false">僅高影響</button>\n'
        '  </div>'
    )

    view = window(df)
    if view.empty:
        return chips + '\n  <p class="cal-empty">目前沒有事件資料。</p>'

    out = [chips]
    for day, group in view.groupby(view["_ts"].dt.tz_convert(TAIPEI).dt.date, sort=True):
        head = f"{day.month}/{day.day:02d}（{WEEKDAYS[day.weekday()]}）"
        rows = []
        for _, e in group.iterrows():
            local = _local(e["_ts"])
            impact = e["impact"]
            rank = IMPACT_ORDER.get(impact, 1)
            # 來源把全日事件標成 00:00；那種顯示「全日」比顯示 00:00 清楚
            when = "全日" if (local.hour == 0 and local.minute == 0) else local.strftime("%H:%M")

            nums = []
            if e["forecast"]:
                nums.append(f'<span>預估 {escape(e["forecast"])}</span>')
            if e["previous"]:
                nums.append(f'<span>前值 {escape(e["previous"])}</span>')
            nums_html = f'<div class="cal-nums">{"".join(nums)}</div>' if nums else ""

            zh = translate_title(e["title"])
            en = e["title"]
            # 副標一行帶過國別與英文原名；查不到對照時 zh 就等於原文，不必重複顯示
            sub = escape(translate_country(e["country"]))
            if zh != en:
                sub += " · " + escape(en)

            rows.append(
                f'    <div class="cal-row" data-impact="{rank}">\n'
                f'      <span class="cal-time">{when}</span>\n'
                f'      <span class="dot {IMPACT_CLASS.get(impact, "i-low")}"'
                f' title="影響 {translate_impact(impact)}"></span>\n'
                f'      <div class="cal-main">\n'
                f'        <div class="cal-title">{escape(zh)}</div>\n'
                f'        <div class="cal-sub">{sub}</div>\n'
                f'      </div>\n'
                f'      {nums_html}\n'
                f'    </div>'
            )

        out.append(
            f'  <div class="cal-day" data-date="{day.isoformat()}">\n'
            f'    <div class="cal-day-h">{head}</div>\n'
            + "\n".join(rows) + "\n  </div>"
        )

    return "\n".join(out)
