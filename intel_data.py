"""
情報中心共用的資料準備：選股條件、推播、網頁都從這裡取資料，
確保三個地方看到的是同一份數字。

    daily_panel()   近 N 個交易日的全市場長表（歷史底稿＋修補＋之後的日期檔），
                    價格已還原權值（raw_close 是原始收盤）
    adjust()        還原權值：除權息、減資、分割前的價格乘上「參考價 ÷ 事件前收盤」
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
PRICE_COLS = ["open", "high", "low", "close"]

JUMP = 0.105            # 單日漲跌超過這個、又找不到權值事件 → 視為沒抓到的事件，不算報酬
REF_EVENT = 0.005       # 參考價與前一天收盤差超過 0.5% 才當成權值事件（避開四捨五入）
NEW_LISTING_DAYS = 5    # 新上市前 5 個交易日沒有漲跌幅限制
FREQUENT_JUMPS = 3      # 一檔有這麼多次找不到事件的大跳動，視為沒有漲跌幅限制，不調整


def _apply_patches(df: pd.DataFrame, base_end) -> pd.DataFrame:
    """歷史底稿的修補：零價（匯出時漏抓）與參考價，以官方重抓的資料為準。"""
    patch = md.load_patches()
    if patch.empty:
        return df
    patch = patch[patch["date"] <= base_end] if base_end is not None else patch
    patch = patch.drop_duplicates(["date", "code"], keep="last")
    m = df.merge(patch, on=["date", "code"], how="left", suffixes=("", "_p"))
    bad = m["close"].isna() | (m["close"] <= 0)
    for col in PRICE_COLS:
        m.loc[bad & m[col + "_p"].notna(), col] = m.loc[bad & m[col + "_p"].notna(), col + "_p"]
    m["ref"] = m["ref"].where(m["ref"].notna(), m["ref_p"])
    return m.drop(columns=[c + "_p" for c in PATCH_FIELDS])


PATCH_FIELDS = ["open", "high", "low", "close", "ref"]


def adjust(df: pd.DataFrame, events: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    還原權值（往回調整）：事件那天以前的開高低收都乘上這之後所有事件的「參考價 ÷ 事件前收盤」，
    最新一天的價格不變。事件來源依序是：

      1. 官方權值事件表（除權息、減資、變更面額）
      2. 當天參考價（收盤 − 漲跌）與前一天收盤差超過 0.5%
      3. 連續兩個交易日漲跌超過 ±10.5% 又找不到事件（ETF、新上市前 5 天、常常這樣的股票除外）
         → 當作沒抓到的事件，那天報酬記為 0，並在 jump 欄標記，資料品質檢查會列出來

    df 需依 code、date 排序。回傳多 raw_close（原始收盤）、jump（第 3 種）兩欄。
    """
    df = df.copy()
    for col in PRICE_COLS:
        df.loc[df[col] <= 0, col] = float("nan")           # 0 元是缺值，不是價格
    df["raw_close"] = df["close"]
    code = df["code"]
    prev = df.groupby("code")["close"].transform(lambda s: s.ffill().shift())
    f = pd.Series(1.0, index=df.index)
    has_event = pd.Series(False, index=df.index)

    events = md.load_events() if events is None else events
    if events is not None and not events.empty:
        ev = events.dropna(subset=["factor"]).assign(date=lambda e: pd.to_datetime(e["date"]))
        ev = ev.drop_duplicates(["date", "code"], keep="last")[["date", "code", "factor"]]
        hit = df[["date", "code"]].merge(ev, on=["date", "code"], how="left")["factor"]
        hit.index = df.index
        ok = hit.notna() & (hit > 0)
        f[ok] = hit[ok]
        has_event |= ok

    ref = df["ref"] if "ref" in df else pd.Series(float("nan"), index=df.index)
    by_ref = (~has_event & ref.notna() & prev.notna() & (ref > 0)
              & ((ref / prev - 1).abs() > REF_EVENT))
    f[by_ref] = (ref / prev)[by_ref]
    has_event |= by_ref

    first_day = df["date"].min()
    nth = df.groupby("code").cumcount()
    listed_late = df.groupby("code")["date"].transform("min") > first_day
    new_listing = listed_late & (nth < NEW_LISTING_DAYS)
    ret = df["close"] / (prev * f) - 1
    # 只看連續兩個交易日：中間停牌好幾天的話，累積的漲跌超過 10.5% 是正常的
    adjacent = df.groupby("code")["close"].shift().notna()
    jump = (~has_event & ret.abs().gt(JUMP) & ~code.str.startswith("00") & ~new_listing
            & df["close"].notna() & prev.notna() & adjacent)
    # 權值事件一檔一年頂多一兩次；常常單日超過 10% 的（新掛牌、沒有漲跌幅限制的板塊）是真的漲跌
    jump &= jump.groupby(code).transform("sum") < FREQUENT_JUMPS
    f[jump] = (df["close"] / prev)[jump]
    df["jump"] = jump

    # 每一列的乘數＝之後（不含當天）所有事件因子的乘積
    rev = f.iloc[::-1].groupby(code.iloc[::-1]).cumprod().iloc[::-1]
    mult = rev / f
    for col in PRICE_COLS:
        df[col] = df[col] * mult
    return df


def daily_panel(days: int = 260, adjusted: bool = True) -> pd.DataFrame:
    """
    近 days 個交易日（歷史底稿＋修補＋之後的日期檔），依 code、date 排序。
    adjusted：開高低收還原權值（預設）；raw_close 一律是原始收盤。
    """
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
    df = _apply_patches(df, base_end)
    keep = sorted(df["date"].unique())[-days:]
    df = df[df["date"].isin(keep)]
    df = df.sort_values(["code", "date"]).reset_index(drop=True)
    if adjusted:
        return adjust(df)
    for col in PRICE_COLS:
        df.loc[df[col] <= 0, col] = float("nan")
    df["raw_close"] = df["close"]
    df["jump"] = False
    return df


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
    price = "raw_close" if "raw_close" in panel else "close"     # 本益比對應的是當時的實際股價
    live = panel.dropna(subset=["per", price])
    if live.empty:
        return hist
    live = live.assign(ym=live["date"].dt.to_period("M").astype(str))
    live = live.sort_values("date").groupby(["code", "ym"]).tail(1)
    live = live[["code", "ym", price, "per"]].rename(columns={"per": "pe", price: "close"})
    merged = pd.concat([hist, live], ignore_index=True)
    return merged.drop_duplicates(["code", "ym"], keep="last").sort_values(["code", "ym"])


def today_taipei() -> date:
    return pd.Timestamp.now(tz="Asia/Taipei").date()
