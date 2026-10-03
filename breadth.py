"""
市場溫度（廣度）：從全市場日資料算，不需要其他來源

    上漲家數比     當天上漲的家數 ÷ 有成交的家數
    站上 20／60 日線  收盤高於 20／60 日均線的比例
    52 週新高／新低   收盤創近 250 個交易日新高／新低的家數
    漲停／跌停       單日漲跌 ≥ 9.5%（還原權值後）

溫度（0～100）＝ 站上 20 日線比例、站上 60 日線比例、近 5 日平均上漲家數比、
新高 ÷（新高＋新低）四項的平均。65 以上偏多、35 以下偏空，其他中性。
ETF（00 開頭）不列入。
"""
import pandas as pd

HOT, COLD = 65, 35


def label(temp) -> str:
    if temp is None or temp != temp:
        return "—"
    return "偏多" if temp >= HOT else "偏空" if temp <= COLD else "中性"


def breadth(panel: pd.DataFrame, days: int = 120) -> pd.DataFrame:
    """每天一列：adv_ratio, above20, above60, nh, nl, limit_up, limit_down, n, temp。"""
    if panel.empty:
        return pd.DataFrame()
    p = panel[~panel["code"].str.startswith("00")]
    c = p.pivot_table(index="date", columns="code", values="close").sort_index()
    traded = c.notna()
    c = c.ffill()
    ret = c.pct_change().where(traded)
    ma20 = c.rolling(20, min_periods=20).mean()
    ma60 = c.rolling(60, min_periods=60).mean()
    hi = c.rolling(250, min_periods=120).max()
    lo = c.rolling(250, min_periods=120).min()
    valid = ret.notna()
    out = pd.DataFrame(index=c.index)
    out["n"] = valid.sum(axis=1)
    out["adv"] = (ret > 0).sum(axis=1)
    out["dec"] = (ret < 0).sum(axis=1)
    out["adv_ratio"] = out["adv"] / out["n"].where(out["n"] > 0) * 100
    ok20, ok60 = traded & ma20.notna(), traded & ma60.notna()
    out["above20"] = ((c > ma20) & ok20).sum(axis=1) / ok20.sum(axis=1).where(ok20.sum(axis=1) > 0) * 100
    out["above60"] = ((c > ma60) & ok60).sum(axis=1) / ok60.sum(axis=1).where(ok60.sum(axis=1) > 0) * 100
    out["nh"] = ((c >= hi) & traded & hi.notna()).sum(axis=1)
    out["nl"] = ((c <= lo) & traded & lo.notna()).sum(axis=1)
    out["limit_up"] = (ret >= 0.095).sum(axis=1)
    out["limit_down"] = (ret <= -0.095).sum(axis=1)
    hl = (out["nh"] / (out["nh"] + out["nl"]).where(out["nh"] + out["nl"] > 0) * 100).fillna(50)
    parts = pd.concat([out["above20"], out["above60"], out["adv_ratio"].rolling(5, min_periods=1).mean(), hl],
                      axis=1)
    out["temp"] = parts.mean(axis=1, skipna=True)
    return out.tail(days)


def summary(panel: pd.DataFrame) -> dict:
    """最新一天的溫度與各項，加上近 60 天的走勢（首頁用）。"""
    b = breadth(panel)
    if b.empty or b["temp"].isna().all():
        return {}
    b = b.dropna(subset=["temp"])
    last = b.iloc[-1]
    prev = b.iloc[-6] if len(b) > 5 else b.iloc[0]
    r = lambda v, n=1: None if v != v else round(float(v), n)
    tail = b.tail(60)
    return {
        "date": b.index[-1].strftime("%Y-%m-%d"),
        "temp": r(last["temp"]), "label": label(last["temp"]), "temp_5d": r(prev["temp"]),
        "adv_ratio": r(last["adv_ratio"]), "adv": int(last["adv"]), "dec": int(last["dec"]),
        "above20": r(last["above20"]), "above60": r(last["above60"]),
        "nh": int(last["nh"]), "nl": int(last["nl"]),
        "limit_up": int(last["limit_up"]), "limit_down": int(last["limit_down"]),
        "series": {"t": [d.strftime("%Y-%m-%d") for d in tail.index],
                   "temp": [r(v) for v in tail["temp"]],
                   "above20": [r(v) for v in tail["above20"]],
                   "adv": [r(v) for v in tail["adv_ratio"]]},
    }
