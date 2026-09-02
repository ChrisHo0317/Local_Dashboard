"""
把 SpaceX 發射資料轉成靜態 HTML（表格）

分頁內目前只有一個子分頁「發射排程」，之後要加（例如任務統計）在
SUBTABS 補一筆即可。

依「月份」分組並可摺疊，預設展開本月 —— 官網一次只公布一場即將發射的任務，
所以這張表實際上是「一場即將發射 + 近期發射紀錄」。

沿用財經行事曆那一套 class（cal-table / cal-day / cal-row …），
樣式與「今天」標記、現在時間標示線、篩選都能直接共用。

時間換算成台北時間（UTC+8，固定位移，不依賴系統的 tz 資料庫）。
"""
from datetime import datetime, timedelta, timezone
from html import escape

import pandas as pd

from spacex_i18n import (translate_launch_site, translate_return_site, translate_return_time,
                         translate_status, translate_title, translate_vehicle)

TAIPEI = timezone(timedelta(hours=8))

# 往回顯示幾天（未來全收）
PAST_DAYS = 90

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]

SUBTABS = [
    ("sched", "發射排程", "SpaceX 發射排程",
     "資料來源：SpaceX　·　時間為台北時間（UTC+8）"),
]


def _local(ts: pd.Timestamp) -> datetime:
    return ts.tz_convert(TAIPEI).to_pydatetime()


def _rank(row) -> int:
    """
    篩選用的重要性：即將發射／進行中最高，一般任務次之，星鏈最低。

    720 筆裡有 421 筆是星鏈，全部混在一起會蓋掉其他任務，
    所以讓「星鏈以外」可以單獨篩出來。
    """
    if row["status"] in ("upcoming", "in-progress"):
        return 3
    return 1 if row["mission_type"] == "starlink" else 2


def window(df: pd.DataFrame) -> pd.DataFrame:
    """近 PAST_DAYS 天內的發射，加上之後全部。"""
    if df.empty or "_ts" not in df:
        return df
    lo = pd.Timestamp(datetime.now(TAIPEI).date() - timedelta(days=PAST_DAYS), tz=TAIPEI)
    return df[df["_ts"] >= lo]


def stats(data: dict) -> dict:
    """設定分頁用的摘要。"""
    df = data.get("launches", pd.DataFrame())
    if df.empty or "_ts" not in df:
        return {"rows": 0, "range": "無資料", "shown": 0, "latest": "無資料", "upcoming": 0}
    first = _local(df["_ts"].min()).strftime("%Y-%m-%d")
    last = _local(df["_ts"].max()).strftime("%Y-%m-%d")
    return {
        "rows": len(df),
        "upcoming": int(df["status"].isin(["upcoming", "in-progress"]).sum()),
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
    return ('  <div class="subtabs" role="tablist" aria-label="SpaceX 子分頁">\n'
            + "\n".join(btns) + "\n  </div>")


def _row_html(e, rank: int) -> str:
    """單一發射列。進行中的任務多顯示一行預計返回時間。"""
    local = _local(e["_ts"])
    day = f"{local.month}/{local.day:02d}（{WEEKDAYS[local.weekday()]}）"
    dot = "i-high" if rank == 3 else ("i-mid" if rank == 2 else "i-low")

    bits = [translate_vehicle(e["vehicle"]), translate_launch_site(e["launch_site"])]
    if e["status"] == "in-progress" and e.get("return_time"):
        bits.append("預計返回 " + translate_return_time(e["return_time"]))
    sub = " · ".join(x for x in bits if x)

    tag = (f'<span class="sx-tag">{escape(translate_status(e["status"]))}</span>'
           if rank == 3 else "")

    return (
        f'        <tr class="cal-row" data-impact="{rank}"'
        f' data-ts="{int(e["_ts"].timestamp() * 1000)}"'
        f' data-day="{local.strftime("%Y-%m-%d")}">\n'
        f'          <td class="cal-when">\n'
        f'            <div class="w-date">{day}</div>\n'
        f'            <div class="w-time">{local.strftime("%H:%M")}</div>\n'
        f'          </td>\n'
        f'          <td class="cal-imp"><span class="dot {dot}"'
        f' title="{escape(translate_status(e["status"]))}"></span></td>\n'
        f'          <td class="cal-ev">\n'
        f'            <div class="cal-title">{escape(translate_title(e["title"]))}{tag}</div>\n'
        f'            <div class="cal-sub">{escape(sub)}</div>\n'
        f'          </td>\n'
        f'          <td class="cal-sess">{escape(translate_return_site(e["return_site"]))}</td>\n'
        f'        </tr>'
    )


def _schedule_html(df: pd.DataFrame) -> str:
    head = (
        '    <div class="cal-bar">\n'
        '      <div class="cal-filter" role="group" aria-label="任務篩選">\n'
        '        <button type="button" class="chip" data-min="0" aria-pressed="true">全部</button>\n'
        '        <button type="button" class="chip" data-min="2" aria-pressed="false">星鏈以外</button>\n'
        '        <button type="button" class="chip" data-min="3" aria-pressed="false">即將發射</button>\n'
        '      </div>\n'
        '      <div class="cal-clock" aria-live="off">—</div>\n'
        '    </div>'
    )

    # 進行中的任務不受時間窗限制：那是「現在的狀態」而不是歷史。
    # Crew-12 是 2026-02 發射、目前仍在軌，照日期會被 90 天的窗濾掉。
    ongoing = df[df["status"] == "in-progress"].sort_values("_ts") if not df.empty else df
    view = window(df)
    if not view.empty:
        view = view[view["status"] != "in-progress"]
    if view.empty and ongoing.empty:
        return head + '\n    <p class="cal-empty">目前沒有發射資料。</p>'

    view = view.sort_values("_ts")
    bodies = []

    # 進行中的任務獨立成一區置頂（官網也是分開列的），不摺疊、不套「已過去」淡化
    if not ongoing.empty:
        rows = [
            '        <tr class="cal-day-row"><th colspan="4" scope="rowgroup">\n'
            '          <div class="grp-head">\n'
            '            <div>\n'
            '              <div class="grp-main">進行中的任務</div>\n'
            f'              <div class="grp-sub">{len(ongoing)} 項任務執行中</div>\n'
            '            </div>\n'
            '          </div>\n'
            '        </th></tr>'
        ]
        rows += [_row_html(e, 3) for _, e in ongoing.iterrows()]
        bodies.append(
            '      <tbody class="cal-day pinned" data-pinned="1">\n'
            + "\n".join(rows) + "\n      </tbody>"
        )
    for (year, month), group in view.groupby(
            [view["_ts"].dt.tz_convert(TAIPEI).dt.year,
             view["_ts"].dt.tz_convert(TAIPEI).dt.month], sort=True):
        last_day = _local(group["_ts"].max()).date()

        rows = [
            '        <tr class="cal-day-row"><th colspan="4" scope="rowgroup"'
            ' role="button" tabindex="0" aria-expanded="true">\n'
            '          <div class="grp-head">\n'
            '            <div>\n'
            f'              <div class="grp-main">{year} 年 {month} 月</div>\n'
            f'              <div class="grp-sub">{len(group)} 次發射</div>\n'
            '            </div>\n'
            '            <span class="grp-chev">&#9660;</span>\n'
            '          </div>\n'
            '        </th></tr>'
        ]
        for _, e in group.iterrows():
            rows.append(_row_html(e, _rank(e)))

        bodies.append(
            f'      <tbody class="cal-day collapsible" data-date="{last_day.isoformat()}">\n'
            + "\n".join(rows) + "\n      </tbody>"
        )

    table = (
        '    <table class="cal-table">\n'
        '      <thead>\n'
        '        <tr><th class="cal-when">日期時間</th>'
        '<th class="cal-imp"><span class="sr">狀態</span></th>'
        '<th class="cal-ev">任務</th><th class="cal-sess">回收</th></tr>\n'
        '      </thead>\n'
        + "\n".join(bodies) + "\n    </table>"
    )
    return head + "\n" + table


def panel_html(data: dict) -> str:
    """產生 SpaceX 分頁的內容（不含 <section> 外框）。"""
    launches = data.get("launches", pd.DataFrame())
    body = (f'  <div class="subpanel" data-sub="sched">\n'
            f'{_schedule_html(launches)}\n  </div>')
    return _subtabs_html() + "\n" + body
