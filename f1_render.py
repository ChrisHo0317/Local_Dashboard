"""
把 F1 賽程與積分榜轉成靜態 HTML

分頁內的層次：
    賽程          依大獎賽分組的場次表（一個賽事週末一組）
    積分 → 車手   冠軍積分走勢圖 + 車手積分榜
         → 車隊   冠軍積分走勢圖 + 車隊積分榜

賽程沿用財經行事曆那一套 class（cal-table / cal-day / cal-row …），
樣式與「今天」標記、現在時間標示線、篩選都能直接共用；
積分榜用另一組 class（rank-table），沒有時間概念。

時間換算成台北時間（UTC+8，固定位移，不依賴系統的 tz 資料庫）。
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

# (id, 標籤, 頁面標題, 說明)。切換分頁時頁面標頭會跟著換。
SUBTABS = [
    ("sched", "賽程", "F1 賽程表",
     "資料來源：F1 Calendar　·　時間為台北時間（UTC+8）"),
    ("points", "積分", "F1 積分榜", "資料來源：f1-boxbox"),
]

# 積分底下的孫分頁：(id, 標籤, 圖表 key, 積分榜的 kind, 名稱欄標題, 頁面標題)
GRANDTABS = [
    ("drivers", "車手", "f1drivers", "driver", "車手", "F1 車手積分榜"),
    ("teams", "車隊", "f1teams", "constructor", "車隊", "F1 車隊積分榜"),
]

STANDINGS_META = "資料來源：f1-boxbox　·　上圖為逐站累積積分，名次升降為與上一站比較"


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


def stats(data: dict) -> dict:
    """設定分頁用的摘要。"""
    df = data.get("schedule", pd.DataFrame())
    standings = data.get("standings", pd.DataFrame())
    if df.empty or "_ts" not in df:
        return {"rows": 0, "range": "無資料", "shown": 0, "latest": "無資料",
                "races": 0, "drivers": 0}
    first = _local(df["_ts"].min()).strftime("%Y-%m-%d")
    last = _local(df["_ts"].max()).strftime("%Y-%m-%d")
    return {
        "rows": len(df),
        "races": df["race"].nunique(),
        "drivers": int((standings["kind"] == "driver").sum()) if not standings.empty else 0,
        "range": f"{first} ～ {last}",
        "shown": len(window(df)),
        "latest": last,
    }


def _subtabs_html() -> str:
    btns = []
    for i, (sid, label, title, meta) in enumerate(SUBTABS):
        btns.append(
            f'      <button type="button" class="subtab" data-sub="{sid}"'
            f' data-title="{escape(title)}" data-meta="{escape(meta)}"'
            f' aria-selected="{"true" if i == 0 else "false"}">{label}</button>'
        )
    return ('  <div class="subtabs" role="tablist" aria-label="F1 子分頁">\n'
            + "\n".join(btns) + "\n  </div>")


def _grandtabs_html() -> str:
    btns = []
    for i, (gid, label, _chart, _kind, _hdr, title) in enumerate(GRANDTABS):
        btns.append(
            f'        <button type="button" class="grandtab" data-grand="{gid}"'
            f' data-title="{escape(title)}" data-meta="{escape(STANDINGS_META)}"'
            f' aria-selected="{"true" if i == 0 else "false"}">{label}</button>'
        )
    return ('    <div class="grandtabs" role="tablist" aria-label="積分子分頁">\n'
            + "\n".join(btns) + "\n    </div>")


def _schedule_html(df: pd.DataFrame) -> str:
    head = (
        '    <div class="cal-bar">\n'
        '      <div class="cal-filter" role="group" aria-label="場次篩選">\n'
        '        <button type="button" class="chip" data-min="0" aria-pressed="true">全部</button>\n'
        '        <button type="button" class="chip" data-min="2" aria-pressed="false">排位＋正賽</button>\n'
        '        <button type="button" class="chip" data-min="3" aria-pressed="false">僅正賽</button>\n'
        '      </div>\n'
        '      <div class="cal-clock" aria-live="off">—</div>\n'
        '    </div>'
    )

    view = window(df)
    if view.empty:
        return head + '\n    <p class="cal-empty">本季賽程已結束或尚未公布。</p>'

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
            '        <tr class="cal-day-row"><th colspan="3" scope="rowgroup">\n'
            f'          <div class="grp-main">R{escape(rnd)}　{escape(race)}</div>\n'
            f'          <div class="grp-sub">{escape(location)} · {span}</div>\n'
            '        </th></tr>'
        ]
        for _, e in group.iterrows():
            local = _local(e["_ts"])
            rank = SESSION_RANK.get(e["session_key"], 1)
            day = f"{local.month}/{local.day:02d}（{WEEKDAYS[local.weekday()]}）"

            rows.append(
                f'        <tr class="cal-row" data-impact="{rank}"'
                f' data-ts="{int(e["_ts"].timestamp() * 1000)}"'
                f' data-day="{local.strftime("%Y-%m-%d")}">\n'
                f'          <td class="cal-when">\n'
                f'            <div class="w-date">{day}</div>\n'
                f'            <div class="w-time">{local.strftime("%H:%M")}</div>\n'
                f'          </td>\n'
                f'          <td class="cal-imp"><span class="dot {RANK_CLASS.get(rank, "i-low")}"'
                f' title="{escape(e["session"])}"></span></td>\n'
                f'          <td class="cal-ev"><div class="cal-title">{escape(e["session"])}</div></td>\n'
                f'        </tr>'
            )

        # data-date 給「已過去」判斷用：整站最後一個場次的日期
        bodies.append(
            f'      <tbody class="cal-day" data-date="{last_day.isoformat()}">\n'
            + "\n".join(rows) + "\n      </tbody>"
        )

    table = (
        '    <table class="cal-table">\n'
        '      <thead>\n'
        '        <tr><th class="cal-when">日期時間</th>'
        '<th class="cal-imp"><span class="sr">場次類型</span></th>'
        '<th class="cal-ev">場次</th></tr>\n'
        '      </thead>\n'
        + "\n".join(bodies) + "\n    </table>"
    )
    return head + "\n" + table


def _gained_html(value: str) -> str:
    """名次升降：正數往上、負數往下、0 不顯示。"""
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return ""
    if n > 0:
        return f'<span class="gain up">▲{n}</span>'
    if n < 0:
        return f'<span class="gain down">▼{abs(n)}</span>'
    return ""


def _standings_html(df: pd.DataFrame, kind: str, name_header: str) -> str:
    part = df[df["kind"] == kind] if not df.empty else df
    if part.empty:
        return '    <p class="cal-empty">尚無積分榜資料。</p>'

    rows = []
    for _, e in part.iterrows():
        sub = (f'<div class="cal-sub">{escape(e["team"])}</div>'
               if kind == "driver" and e["team"] else "")
        rows.append(
            '      <tr>\n'
            f'        <td class="rk-pos">{escape(e["position"])}{_gained_html(e["gained"])}</td>\n'
            f'        <td class="rk-name">\n'
            f'          <div class="cal-title">{escape(e["name"])}</div>\n'
            f'          {sub}\n'
            f'        </td>\n'
            f'        <td class="rk-pts">{escape(e["points"])}</td>\n'
            f'        <td class="rk-num">{escape(e["wins"])}</td>\n'
            f'        <td class="rk-num">{escape(e["podiums"])}</td>\n'
            '      </tr>'
        )

    return (
        '    <table class="rank-table">\n'
        '      <thead>\n'
        f'        <tr><th class="rk-pos">名次</th><th class="rk-name">{name_header}</th>'
        '<th class="rk-pts">積分</th><th class="rk-num">勝場</th>'
        '<th class="rk-num">頒獎台</th></tr>\n'
        '      </thead>\n'
        '      <tbody>\n'
        + "\n".join(rows) + "\n      </tbody>\n    </table>"
    )


def _points_panel_html(standings: pd.DataFrame) -> str:
    """積分子分頁：孫分頁（車手／車隊），各自是走勢圖 + 積分榜。"""
    parts = [_grandtabs_html()]
    for i, (gid, _label, chart_key, kind, header, _title) in enumerate(GRANDTABS):
        hidden = "" if i == 0 else " hidden"
        parts.append(
            f'    <div class="grandpanel" data-grand="{gid}"{hidden}>\n'
            f'      <div class="chart chart-sm" id="chart-{chart_key}"></div>\n'
            f'      <div class="legend-bar" data-chart="{chart_key}"></div>\n'
            f'{_standings_html(standings, kind, header)}\n'
            f'    </div>'
        )
    return "\n".join(parts)


def panel_html(data: dict) -> str:
    """產生 F1 分頁的內容（不含 <section> 外框）。"""
    schedule = data.get("schedule", pd.DataFrame())
    standings = data.get("standings", pd.DataFrame())

    panels = [
        ("sched", _schedule_html(schedule)),
        ("points", _points_panel_html(standings)),
    ]
    body = []
    for i, (sid, content) in enumerate(panels):
        hidden = "" if i == 0 else " hidden"
        body.append(f'  <div class="subpanel" data-sub="{sid}"{hidden}>\n{content}\n  </div>')

    return _subtabs_html() + "\n" + "\n".join(body)
