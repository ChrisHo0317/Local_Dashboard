"""
市場熱度（廣度）：從全市場日資料算，權值股分項另外要已發行股數（shares_data.py）

    上漲家數比     當天上漲的家數 ÷ 有成交的家數
    站上 20／60 日線  收盤高於 20／60 日均線的比例
    52 週新高／新低   收盤創近 250 個交易日新高／新低的家數
    漲停／跌停       單日漲跌 ≥ 9.5%（還原權值後）

每個分項（0～100）＝ 站上 20 日線比例、站上 60 日線比例、近 5 日平均上漲比例、
新高 ÷（新高＋新低）四項的平均，差別在誰算進來、怎麼加權：

    全市場  每檔一樣重（原本的市場溫度）
    權值股  依市值加權，單一股票最多算 CAP_MAX（台積電一檔就占上市櫃市值近四成，不設上限就變成台積電溫度）
    高價股  收盤 HIGH_PRICE 元以上的股票，每檔一樣重
            （試過「價格越高越重」和 1 萬／5 千／1 千元分級加權，結果和等權幾乎一樣，分級只拿來顯示檔數）

市場熱度＝全市場 50%＋權值股 30%＋高價股 20%（WEIGHTS；缺的分項不算，其餘按比例）。
65 以上偏多、35 以下偏空，其他中性。權值股或高價股比全市場高 GAP 以上、或反過來，另外標分歧。
ETF（00 開頭）不列入。
"""
import numpy as np
import pandas as pd

HOT, COLD = 65, 35
WEIGHTS = {"temp_all": 0.5, "temp_cap": 0.3, "temp_hp": 0.2}
CAP_MAX = 0.10
HIGH_PRICE = 1000
TIERS = (10000, 5000, 1000)        # 高價股分級（收盤價）
GAP = 25


def label(temp) -> str:
    if temp is None or temp != temp:
        return "—"
    return "偏多" if temp >= HOT else "偏空" if temp <= COLD else "中性"


def divergence(all_, cap, hp) -> str:
    """分項之間差太多時的提示；沒有就是空字串。"""
    lead = max([v for v in (cap, hp) if v is not None and v == v], default=None)
    if lead is None or all_ is None or all_ != all_:
        return ""
    if lead - all_ >= GAP:
        return "權值撐盤、多數個股弱"
    if all_ - lead >= GAP:
        return "中小型股強、權值股弱"
    return ""


def _capped(w: pd.DataFrame, top: float = CAP_MAX) -> pd.DataFrame:
    """每天各股的權重比例，單一股票最多 top，超出的部分按比例分給其他股票。"""
    share = w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    for _ in range(8):
        share = share.clip(upper=top)
        share = share.div(share.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    return share


def _score(c, ma20, ma60, hi, lo, up, traded, valid, w=None) -> pd.Series:
    """四項的平均（0～100）；w 是權重（None＝每檔一樣重），traded／valid 決定誰算進來。"""
    def frac(flag, ok):
        if w is None:
            return (flag & ok).sum(axis=1) / ok.sum(axis=1).where(ok.sum(axis=1) > 0) * 100
        ww = w.where(ok).fillna(0)
        tot = ww.sum(axis=1)
        return (ww * flag.where(ok, False)).sum(axis=1) / tot.where(tot > 0) * 100
    a20 = frac(c > ma20, traded & ma20.notna())
    a60 = frac(c > ma60, traded & ma60.notna())
    adv = frac(up, valid)
    nh = frac(c >= hi, traded & hi.notna())
    nl = frac(c <= lo, traded & lo.notna())
    hl = (nh / (nh + nl).where(nh + nl > 0) * 100).fillna(50)
    parts = pd.concat([a20, a60, adv.rolling(5, min_periods=1).mean(), hl], axis=1)
    return parts.mean(axis=1, skipna=True)


def breadth(panel: pd.DataFrame, days: int = 120, shares: pd.Series | None = None) -> pd.DataFrame:
    """每天一列：家數、各項比例、三個分項與市場熱度（temp）、高價股分級檔數。"""
    if panel.empty:
        return pd.DataFrame()
    p = panel[~panel["code"].str.startswith("00")]
    c = p.pivot_table(index="date", columns="code", values="close").sort_index()
    price = (p.pivot_table(index="date", columns="code", values="raw_close").reindex_like(c)
             if "raw_close" in p else c.copy())
    traded = c.notna()
    c = c.ffill()
    price = price.ffill()
    ret = c.pct_change().where(traded)
    ma20 = c.rolling(20, min_periods=20).mean()
    ma60 = c.rolling(60, min_periods=60).mean()
    hi = c.rolling(250, min_periods=120).max()
    lo = c.rolling(250, min_periods=120).min()
    valid = ret.notna()
    up = ret > 0
    out = pd.DataFrame(index=c.index)
    out["n"] = valid.sum(axis=1)
    out["adv"] = (ret > 0).sum(axis=1)
    out["dec"] = (ret < 0).sum(axis=1)
    out["flat"] = (ret == 0).sum(axis=1)
    out["adv_ratio"] = out["adv"] / out["n"].where(out["n"] > 0) * 100
    ok20, ok60 = traded & ma20.notna(), traded & ma60.notna()
    out["above20"] = ((c > ma20) & ok20).sum(axis=1) / ok20.sum(axis=1).where(ok20.sum(axis=1) > 0) * 100
    out["above60"] = ((c > ma60) & ok60).sum(axis=1) / ok60.sum(axis=1).where(ok60.sum(axis=1) > 0) * 100
    out["nh"] = ((c >= hi) & traded & hi.notna()).sum(axis=1)
    out["nl"] = ((c <= lo) & traded & lo.notna()).sum(axis=1)
    out["limit_up"] = (ret >= 0.095).sum(axis=1)
    out["limit_down"] = (ret <= -0.095).sum(axis=1)

    # 全市場：每檔一樣重
    out["temp_all"] = _score(c, ma20, ma60, hi, lo, up, traded, valid)
    # 權值股：前一天的市值（收盤價 × 已發行股數）加權，單一股票上限 CAP_MAX
    out["temp_cap"] = np.nan
    if shares is not None and len(shares):
        cap = price.shift(1) * shares.reindex(c.columns)
        if cap.notna().any().any():
            w = _capped(cap.where(traded), CAP_MAX)
            out["temp_cap"] = _score(c, ma20, ma60, hi, lo, up, traded, valid, w)
            out.loc[w.sum(axis=1) == 0, "temp_cap"] = np.nan
    # 高價股：當天收盤 HIGH_PRICE 元以上
    hp = price >= HIGH_PRICE
    out["temp_hp"] = _score(c, ma20, ma60, hi, lo, up, traded & hp, valid & hp)
    for t in TIERS:
        out[f"p{t}"] = (traded & (price >= t)).sum(axis=1)
    out["hp_up"] = (up & valid & hp).sum(axis=1)
    out["hp_dn"] = ((ret < 0) & valid & hp).sum(axis=1)

    parts = out[list(WEIGHTS)]
    wts = pd.Series(WEIGHTS)
    have = parts.notna().astype(float).mul(wts, axis=1)
    out["temp"] = (parts.fillna(0).mul(wts, axis=1).sum(axis=1)
                   / have.sum(axis=1).where(have.sum(axis=1) > 0))
    return out.tail(days)


def summary(panel: pd.DataFrame, shares: pd.Series | None = None, names: dict | None = None) -> dict:
    """最新一天的市場熱度、三個分項與各項家數，加上近 60 天的走勢（首頁用）。"""
    if shares is None:
        from shares_data import load
        shares = load()
    b = breadth(panel, shares=shares)
    if b.empty or b["temp"].isna().all():
        return {}
    b = b.dropna(subset=["temp"])
    last = b.iloc[-1]
    prev = b.iloc[-6] if len(b) > 5 else b.iloc[0]
    before = b.iloc[-21] if len(b) > 20 else b.iloc[0]
    r = lambda v, n=1: None if v is None or v != v else round(float(v), n)
    tail = b.tail(60)
    tiers = {}
    if names is not None and "raw_close" in panel:
        day = panel[(panel["date"] == panel["date"].max()) & ~panel["code"].str.startswith("00")]
        day = day.dropna(subset=["raw_close"]).sort_values("raw_close", ascending=False)
        for hi_t, lo_t in ((None, TIERS[0]), (TIERS[0], TIERS[1]), (TIERS[1], TIERS[2])):
            sel = day[(day["raw_close"] >= lo_t) & ((day["raw_close"] < hi_t) if hi_t else True)]
            tiers[str(lo_t)] = [[c, names.get(c, c), round(float(v))] for c, v in zip(sel["code"], sel["raw_close"])]
    return {
        "date": b.index[-1].strftime("%Y-%m-%d"),
        "temp": r(last["temp"]), "label": label(last["temp"]), "temp_5d": r(prev["temp"]),
        "temp_all": r(last["temp_all"]), "temp_cap": r(last["temp_cap"]), "temp_hp": r(last["temp_hp"]),
        "divergence": divergence(last["temp_all"], last["temp_cap"], last["temp_hp"]),
        "adv_ratio": r(last["adv_ratio"]), "adv": int(last["adv"]), "dec": int(last["dec"]),
        "flat": int(last["flat"]),
        "above20": r(last["above20"]), "above60": r(last["above60"]),
        "nh": int(last["nh"]), "nl": int(last["nl"]),
        "limit_up": int(last["limit_up"]), "limit_down": int(last["limit_down"]),
        # 高價股：各級檔數（累計：1000 元以上包含 5000、10000 以上）、20 個交易日前的檔數、今天漲跌
        "hp": {"counts": {str(t): int(last[f"p{t}"]) for t in TIERS},
               "counts_20d": {str(t): int(before[f"p{t}"]) for t in TIERS},
               "up": int(last["hp_up"]), "down": int(last["hp_dn"]), "tiers": tiers},
        "series": {"t": [d.strftime("%Y-%m-%d") for d in tail.index],
                   "temp": [r(v) for v in tail["temp"]],
                   "temp_all": [r(v) for v in tail["temp_all"]],
                   "temp_cap": [r(v) for v in tail["temp_cap"]],
                   "temp_hp": [r(v) for v in tail["temp_hp"]],
                   "above20": [r(v) for v in tail["above20"]],
                   "adv": [r(v) for v in tail["adv_ratio"]]},
    }
