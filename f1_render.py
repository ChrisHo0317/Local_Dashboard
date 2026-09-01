"""
把 F1 賽程轉成靜態 HTML（表格）

依「大獎賽」分組，一個賽事週末一組 —— 練習賽、排位賽、正賽本來就是同一個
週末的事，照日期拆開反而看不出整體。組標題顯示輪次、賽事、地點與日期區間，
每一列則是單一場次。

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
    """
    取出要顯示的場次：近幾天內的，加上之後整季。

    以「整個大獎賽」為單位保留 —— 若某一站的正賽還沒到，就算它的練習賽
    已經過了，也要一起顯示，否則組裡會缺角。
    """
    if df.empty or "_ts" not in df:
        return df
    lo = pd.Timestamp(datetime.now(TAIPEI).date() - timedelta(days=PAST_DAYS), tz=TAIPEI)
    keep = df.groupby("race")["_ts"].transform("max") >= lo
    return df[keep]


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
    # 依輪次排序（round 是字串，要轉數字），同一站的場次照時間排
    view = view.assign(_round=pd.to_numeric(view["round"], errors="coerce"))
    for (_, race), group in view.sort_values(["_round", "_ts"]).groupby(
            ["_round", "race"], sort=False):
        group = group.sort_values("_ts")
        first_day = _local(group["_ts"].min()).date()
        last_day = _local(group["_ts"].max()).date()
        rnd = str(group["round"].iloc[0])
        location = group["location"].iloc[0]

        span = f"{first_day.month}/{first_day.day:02d}"
        if last_day != first_day:
            span += f" – {last_day.month}/{last_day.day:02d}"

        rows = [
            '      <tr class="cal-day-row"><th colspan="3" scope="rowgroup">\n'
            f'        <div class="grp-main">R{escape(rnd)}　{escape(race)}</div>\n'
            f'        <div class="grp-sub">{escape(location)} · {span}</div>\n'
            '      </th></tr>'
        ]
        for _, e in group.iterrows():
            local = _local(e["_ts"])
            rank = SESSION_RANK.get(e["session_key"], 1)
            day = f"{local.month}/{local.day:02d}（{WEEKDAYS[local.weekday()]}）"

            rows.append(
                f'      <tr class="cal-row" data-impact="{rank}"'
                f' data-ts="{int(e["_ts"].timestamp() * 1000)}"'
                f' data-day="{local.strftime("%Y-%m-%d")}">\n'
                f'        <td class="cal-when">\n'
                f'          <div class="w-date">{day}</div>\n'
                f'          <div class="w-time">{local.strftime("%H:%M")}</div>\n'
                f'        </td>\n'
                f'        <td class="cal-imp"><span class="dot {RANK_CLASS.get(rank, "i-low")}"'
                f' title="{escape(e["session"])}"></span></td>\n'
                f'        <td class="cal-ev"><div class="cal-title">{escape(e["session"])}</div></td>\n'
                f'      </tr>'
            )

        # data-date 給「已過去」判斷用：整站最後一個場次的日期
        bodies.append(
            f'    <tbody class="cal-day" data-date="{last_day.isoformat()}">\n'
            + "\n".join(rows) + "\n    </tbody>"
        )

    table = (
        '  <table class="cal-table">\n'
        '    <thead>\n'
        '      <tr><th class="cal-when">日期時間</th>'
        '<th class="cal-imp"><span class="sr">場次類型</span></th>'
        '<th class="cal-ev">場次</th></tr>\n'
        '    </thead>\n'
        + "\n".join(bodies) + "\n  </table>"
    )
    return head + "\n" + table
