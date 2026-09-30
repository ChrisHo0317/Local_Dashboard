"""
情報中心共用的資料準備：選股條件、推播、網頁都從這裡取資料，
確保三個地方看到的是同一份數字。

    daily_panel()   近 N 個交易日的全市場長表（歷史底稿＋之後的日期檔）
    stock_master()  股票清單，產業名稱以官方營收清單為準
    pe_series()     月本益比：匯出的歷史＋之後每月最後一天的官方本益比
"""
from datetime import date
from pathlib import Path

import pandas as pd

import market_data as md
from fundamentals import load_pe
from stock_data import load as load_stock_list

BASE_DIR = Path(__file__).resolve().parent
HISTORY_BASE = BASE_DIR / "data" / "market" / "history_base.parquet"

PANEL_COLS = ["date"] + md.COLUMNS


def daily_panel(days: int = 260) -> pd.DataFrame:
    """近 days 個交易日（依日期檔與歷史底稿合併），依 code、date 排序。"""
    frames = []
    base_end = None
    if HISTORY_BASE.exists():
        base = pd.read_parquet(HISTORY_BASE)
        base_end = base["date"].max()
        frames.append(base)
    later = [d for d in md.dates() if base_end is None or pd.Timestamp(d) > base_end]
    if later:
        frames.append(md.load_days(later))
    if not frames:
        return pd.DataFrame(columns=PANEL_COLS)
    df = pd.concat([f.reindex(columns=PANEL_COLS) for f in frames], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["code"] = df["code"].astype(str)
    df["market"] = df["market"].astype(str)
    for col in md.VALUE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    keep = sorted(df["date"].unique())[-days:]
    df = df[df["date"].isin(keep)]
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def trading_days(panel: pd.DataFrame) -> list[pd.Timestamp]:
    return sorted(panel["date"].unique())


def stock_master() -> pd.DataFrame:
    """code, name, market, industry。官方營收清單的產業名稱優先。"""
    stocks = md.load_stocks()
    rev = load_stock_list("revenue")
    if not rev.empty:
        official = rev[["code", "name", "market", "industry"]].drop_duplicates("code", keep="last")
        stocks = stocks.set_index("code")
        for _, r in official.iterrows():
            if r["code"] in stocks.index:
                if r["industry"]:
                    stocks.at[r["code"], "industry"] = r["industry"]
            else:
                stocks.loc[r["code"]] = [r["name"], r["market"], r["industry"]]
        stocks = stocks.reset_index().rename(columns={"index": "code"})
    return stocks.fillna("").sort_values("code").reset_index(drop=True)


def pe_series(panel: pd.DataFrame) -> pd.DataFrame:
    """
    code, ym, close, pe。歷史之後的月份用該月最後一個交易日的收盤與官方本益比
    （官方本益比用的是最新一季財報，比匯出時的推算更準，重疊的月份以它為準）。
    """
    hist = load_pe().reindex(columns=["code", "ym", "close", "pe"])
    if panel.empty or "per" not in panel:
        return hist
    live = panel.dropna(subset=["per", "close"])
    if live.empty:
        return hist
    live = live.assign(ym=live["date"].dt.to_period("M").astype(str))
    live = live.sort_values("date").groupby(["code", "ym"]).tail(1)
    live = live[["code", "ym", "close", "per"]].rename(columns={"per": "pe"})
    merged = pd.concat([hist, live], ignore_index=True)
    return merged.drop_duplicates(["code", "ym"], keep="last").sort_values(["code", "ym"])


def today_taipei() -> date:
    return pd.Timestamp.now(tz="Asia/Taipei").date()
