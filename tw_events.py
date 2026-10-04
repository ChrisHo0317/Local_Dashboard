"""
台股事件：併進財經行事曆，一起用月曆格與清單呈現

    除權息       自選股的除權、除息日（證交所、櫃買中心的預告表）
    營收公布     上市櫃公司每月 10 日前公布上月營收
    法說會       自選股＋近 20 日平均成交值前 100 名（公開資訊觀測站法人說明會一覽表）
    指數調整     MSCI、FTSE（0050）、0056、00878 的調整生效日（依慣例推算的預估日）

影響程度用 "TW"（標籤「台股」、紫色圓點），和總經事件分開勾選。
"""
from datetime import timedelta, timezone

import pandas as pd

from calendar_data import COLUMNS
from intel_data import stock_master, today_taipei
from stock_data import load as load_stock_list
from watchlist import load_watchlist

TAIPEI = timezone(timedelta(hours=8))
CALL_TOP = 100          # 法說會：成交值前幾名的股票會列進行事曆
CALL_DAYS = 45


def big_codes(top: int = CALL_TOP) -> set:
    """近 20 個交易日平均成交值前 top 名的股票（不含 ETF）。"""
    import market_data as md
    days = md.dates()[-20:]
    if not days:
        return set()
    df = md.load_days(days)
    df = df[~df["code"].str.startswith("00")]
    avg = df.groupby("code")["turnover"].mean().sort_values(ascending=False)
    return set(avg.head(top).index)


def _roc(v: str):
    v = str(v)
    if len(v) == 7 and v.isdigit():
        return pd.Timestamp(int(v[:3]) + 1911, int(v[3:5]), int(v[5:]))
    return None


def tw_events() -> pd.DataFrame:
    rows = []
    codes = {w["code"] for w in load_watchlist()}
    if codes:
        master = stock_master()
        names = dict(zip(master["code"], master["name"]))
        ex = load_stock_list("exdiv")
        for _, r in ex[ex["code"].isin(codes)].iterrows():
            day = _roc(r["date"])
            if day is None:
                continue
            kind = "除" + str(r["kind"]).replace("除", "")
            cash = pd.to_numeric(r["cash"], errors="coerce")
            rows.append({"day": day, "title": f"{r['code']} {names.get(r['code'], r['name'])} {kind}",
                         "forecast": f"{cash:g} 元" if pd.notna(cash) and cash > 0 else ""})
    today = today_taipei()
    import earnings_calls
    import index_events
    want = codes | big_codes()
    calls = earnings_calls.upcoming(want, (today - timedelta(days=14)).isoformat(), CALL_DAYS + 14)
    if not calls.empty:
        master = stock_master()
        names = dict(zip(master["code"], master["name"]))
        for _, r in calls.iterrows():
            hm = str(r["time"])[:5]
            day = pd.Timestamp(r["date"])
            if len(hm) == 5 and hm[2] == ":" and hm.replace(":", "").isdigit():
                day = day + pd.Timedelta(hours=int(hm[:2]), minutes=int(hm[3:]))
            rows.append({"day": day, "title": f"{r['code']} {names.get(r['code'], r['name'])} 法說會",
                         "forecast": ""})
    for e in index_events.events(today - timedelta(days=14), today + timedelta(days=CALL_DAYS)):
        rows.append({"day": pd.Timestamp(e["date"]), "title": e["title"] + "（預估）", "forecast": ""})
    for months in (0, 1):
        y, m = today.year, today.month + months
        if m > 12:
            y, m = y + 1, m - 12
        rows.append({"day": pd.Timestamp(y, m, 10), "title": "上市櫃公司上月營收公布截止",
                     "forecast": ""})
    if not rows:
        return pd.DataFrame(columns=COLUMNS + ["_ts"])
    df = pd.DataFrame(rows)
    # 全日事件：台北時間 00:00（清單會顯示「全日」）；法說會有時間
    df["_ts"] = [pd.Timestamp(d.year, d.month, d.day, getattr(d, "hour", 0), getattr(d, "minute", 0),
                              tz=TAIPEI).tz_convert("UTC")
                 for d in df["day"]]
    df["event_time"] = df["_ts"].map(lambda t: t.isoformat())
    df["country"] = "TW"
    df["impact"] = "TW"
    for col in COLUMNS:
        if col not in df:
            df[col] = ""
    return df[COLUMNS + ["_ts"]]


def with_tw_events(df: pd.DataFrame) -> pd.DataFrame:
    tw = tw_events()
    if tw.empty:
        return df
    out = pd.concat([df, tw], ignore_index=True)
    return out.sort_values("_ts").reset_index(drop=True)
