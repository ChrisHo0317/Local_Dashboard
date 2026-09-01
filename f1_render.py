"""
把 F1 賽程轉成靜態 HTML（表格）

沿用財經行事曆那一套 class（cal-table / cal-day / cal-row …），
樣式與「今天」標記、現在時間標示線、篩選都能直接共用。

時間換算成台北時間（UTC+8，固定位移，不依賴系統的 tz 資料庫）。
賽事與場次名稱來源本身就是繁體中文，不需要另外翻譯。
"""
from datetime import datetime, timedelta, timezone
from html import escape

import pandas as pd

from f1_data import SESSION_RANK

TAIPEI = timezone(timedelta(hours=8))

# 賽季表要看的是「接下來還有哪些場次」，所以往回只留幾天，往後整季都顯示
PAST_DAYS = 7

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

RANK_CLASS = {3: "i-high", 2: "i-mid", 1: "i-low"}


def _local(ts: pd.Timestamp) -> datetime:
    return ts.tz_convert(TAIPEI).to_pydatetime()


def window(df: pd.DataFrame) -> pd.DataFrame:
    """取出要顯示的場次：近幾天內的，加上之後整季。"""
    if df.empty or "_ts" not in df:
        return df
    lo = pd.Timestamp(datetime.now(TAIPEI).date() - timedelta(days=PAST_DAYS), tz=TAIPEI)
    return df[df["_ts"] >= lo]


def stats(df: pd.DataFrame) -> dict:
    """設定分頁用的摘要。"""
    if df.empty or "_ts" not in df:
        return {"rows": 0, "range": "無資料", "shown": 0, "latest": "無資料", "races": 0}
    first = _local(df["_ts"].min()).strftime("%Y-%m-%d")
    last = _local(df["_ts"].max()).strftime("%Y-%m-%d")
    return {
        "rows": len(df),
        "races": df["race"].nunique(),
        "range": f"{first} ～ {last}",
        "shown": len(window(df)),
        "latest": last,
    }


def panel_html(df: pd.DataFrame) -> str:
    """產生 F1 分頁的內容（不含 <section> 外框）。"""
    head = (
        '  <div class="cal-bar">\n'
        '    <div class="cal-filter" role="group" aria-label="場次篩選">\n'
        '      <button type="button" class="chip" data-min="0" aria-pressed="true">全部</button>\n'
        '      <button type="button" class="chip" data-min="2" aria-pressed="false">排位＋正賽</button>\n'
        '      <button type="button" class="chip" data-min="3" aria-pressed="false">僅正賽</button>\n'
        '    </div>\n'
        '    <div class="cal-clock" aria-live="off">—</div>\n'
        '  </div>'
    )

    view = window(df)
    if view.empty:
        return head + '\n  <p class="cal-empty">本季賽程已結束或尚未公布。</p>'

    bodies = []
    for day, group in view.groupby(view["_ts"].dt.tz_convert(TAIPEI).dt.date, sort=True):
        label = f"{day.month}/{day.day:02d}（{WEEKDAYS[day.weekday()]}）"
        rows = [
            f'      <tr class="cal-day-row"><th colspan="4" scope="rowgroup">{label}</th></tr>'
        ]
        for _, e in group.iterrows():
            local = _local(e["_ts"])
            rank = SESSION_RANK.get(e["session_key"], 1)
            sub = f'R{escape(str(e["round"]))} · {escape(e["location"])}'

            rows.append(
                f'      <tr class="cal-row" data-impact="{rank}"'
                f' data-ts="{int(e["_ts"].timestamp() * 1000)}">\n'
                f'        <td class="cal-time">{local.strftime("%H:%M")}</td>\n'
                f'        <td class="cal-imp"><span class="dot {RANK_CLASS.get(rank, "i-low")}"'
                f' title="{escape(e["session"])}"></span></td>\n'
                f'        <td class="cal-ev">\n'
                f'          <div class="cal-title">{escape(e["race"])}</div>\n'
                f'          <div class="cal-sub">{sub}</div>\n'
                f'        </td>\n'
                f'        <td class="cal-sess">{escape(e["session"])}</td>\n'
                f'      </tr>'
            )

        bodies.append(
            f'    <tbody class="cal-day" data-date="{day.isoformat()}">\n'
            + "\n".join(rows) + "\n    </tbody>"
        )

    table = (
        '  <table class="cal-table">\n'
        '    <thead>\n'
        '      <tr><th class="cal-time">時間</th><th class="cal-imp"><span class="sr">場次類型</span></th>'
        '<th class="cal-ev">賽事</th><th class="cal-sess">場次</th></tr>\n'
        '    </thead>\n'
        + "\n".join(bodies) + "\n  </table>"
    )
    return head + "\n" + table
