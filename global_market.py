"""
國際市場（總覽「國際」子分頁）：美股、期貨、亞股、供應鏈龍頭、原物料、匯率、美債利率。

資料來源都是已經存在的 CSV：
    data/xmarket_prices.csv   Yahoo Finance（xmarket_data.SYMBOLS）
    data/gold_prices.csv      COMEX 黃金期貨
    data/bond_yields.csv      美債殖利率（2 年、10 年 → 10 年 − 2 年利差）

輸出 site/data/global.json：
    asof     最新的資料日期
    groups   [{name, note, items: [項目]}]
             項目 = {name, date, last, dec, unit, d1, d5, d20, d60, ytd, corr, mode, spark}
             d1…ytd 是漲跌幅（%）；殖利率與利差是變動（百分點），unit="pt"
             corr 是和台股的相關係數（近 120 個台股交易日）；mode="lead" 代表用
             前一晚的漲跌對隔天台股（美股、歐美交易的商品），"sync" 是同一天（亞洲）
    series   {名稱: [[日期…], [值…]]}，近一年，點一列畫走勢
    key      首頁「國際市場」卡片的重點項目（名稱、最新、日漲跌、日期）
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from xmarket_data import load_xmarket

CORR_DAYS = 120
SERIES_DAYS = 260
SPARK_DAYS = 60

# (名稱, 小數位數, 和台股比的方式)；lead＝前一晚對隔天、sync＝同一天
GROUPS = [
    ("美股大盤", "前一晚收盤", [
        ("標普500", 2, "lead"), ("道瓊工業", 2, "lead"), ("那斯達克", 2, "lead"),
        ("費城半導體", 2, "lead"), ("羅素2000", 2, "lead"), ("VIX", 2, "lead"),
    ]),
    ("美股期貨", "台灣白天也在交易，可以看美股開盤前的方向", [
        ("標普期貨", 2, "lead"), ("那斯達克期貨", 2, "lead"),
    ]),
    ("亞洲股市", "和台股同一個時段交易", [
        ("加權指數", 2, "sync"), ("日經225", 2, "sync"), ("韓國綜合", 2, "sync"),
        ("恒生指數", 2, "sync"), ("上證指數", 2, "sync"),
    ]),
    ("供應鏈龍頭", "台積電 ADR 與美、韓半導體／蘋果", [
        ("台積電ADR", 2, "lead"), ("輝達", 2, "lead"), ("超微", 2, "lead"), ("博通", 2, "lead"),
        ("蘋果", 2, "lead"), ("美光", 2, "lead"), ("艾司摩爾", 2, "lead"),
        ("三星電子", 0, "sync"), ("SK海力士", 0, "sync"),
    ]),
    ("原物料", "期貨近月", [
        ("COMEX 黃金期貨", 1, "lead"), ("WTI原油", 2, "lead"), ("布蘭特原油", 2, "lead"),
        ("銅", 3, "lead"), ("天然氣", 3, "lead"),
    ]),
    ("匯率", "美元兌台幣上升＝台幣貶值", [
        ("美元指數", 2, "lead"), ("美元兌台幣", 3, "sync"), ("美元兌日圓", 2, "sync"),
        ("美元兌人民幣", 4, "sync"), ("美元兌韓元", 1, "sync"), ("歐元兌美元", 4, "lead"),
    ]),
    ("美債利率", "殖利率與利差的變動是百分點；利差轉負（倒掛）常被視為景氣轉弱的訊號", [
        ("美債2年", 2, "lead"), ("美債10年", 2, "lead"), ("10年−2年利差", 2, "lead"),
    ]),
]
RATE_ITEMS = {"美債2年", "美債10年", "10年−2年利差"}
KEY_ITEMS = ["標普500", "那斯達克", "費城半導體", "台積電ADR", "輝達", "標普期貨",
             "VIX", "美元兌台幣", "美債10年", "WTI原油"]


def _r(v, d=2):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), d)


def _sig(v, digits=5):
    """走勢圖用：保留有效位數就好，檔案小一點。"""
    if v is None or not np.isfinite(v):
        return None
    if v == 0:
        return 0.0
    return round(float(v), max(0, digits - 1 - int(math.floor(math.log10(abs(v))))))


def load_series() -> dict[str, pd.Series]:
    """名稱 → 依日期排序的收盤（或殖利率）序列。"""
    out: dict[str, pd.Series] = {}
    xm = load_xmarket()
    for name, g in xm.groupby("item"):
        s = g.set_index("price_date")["price"].astype(float)
        s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
        # Yahoo 的匯率週末偶爾會多一根幾乎不動的 K 棒，日漲跌會變成 0，拿掉
        out[name] = s[s.index.dayofweek < 5]
    try:
        from gold_data import load_gold
        gd = load_gold()
        for name, g in gd.groupby("item", observed=True):
            s = g.set_index(pd.to_datetime(g["price_date"]))["price_usd"].astype(float)
            out[str(name)] = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    except Exception:
        pass
    try:
        from bond_data import load_bonds
        bd = load_bonds()
    except Exception:
        bd = pd.DataFrame()
    if not bd.empty:
        def bond(term):
            g = bd[bd["item"] == term]
            s = g.set_index(pd.to_datetime(g["price_date"]))["yield_pct"].astype(float)
            return s[~s.index.duplicated(keep="last")].sort_index().dropna()
        y2, y10 = bond("2年期"), bond("10年期")
        if len(y2):
            out["美債2年"] = y2
        if len(y10):
            out["美債10年"] = y10
        if len(y2) and len(y10):
            both = pd.concat([y10, y2], axis=1, join="inner").dropna()
            out["10年−2年利差"] = both.iloc[:, 0] - both.iloc[:, 1]
    return out


def _change(s: pd.Series, n: int, rate: bool):
    if len(s) <= n:
        return None
    a, b = float(s.iloc[-1 - n]), float(s.iloc[-1])
    if rate:
        return b - a
    return (b / a - 1) * 100 if a else None


def _ytd(s: pd.Series, rate: bool):
    last = s.index[-1]
    before = s[s.index < pd.Timestamp(last.year, 1, 1)]
    if before.empty:
        return None
    a, b = float(before.iloc[-1]), float(s.iloc[-1])
    if rate:
        return b - a
    return (b / a - 1) * 100 if a else None


def _corr(s: pd.Series, tw: pd.Series, mode: str, rate: bool):
    """和台股（加權指數日報酬）的相關係數。lead：每個台股交易日配「前一個日期以前」的最後一筆。"""
    if len(tw) < 30 or len(s) < 30:
        return None
    tw_ret = tw.pct_change().dropna().tail(CORR_DAYS)
    move = s.diff() if rate else s.pct_change()
    move = move.dropna()
    if mode == "lead":
        # 美股 d 日收盤在台灣時間 d+1 清晨，對應的是 d 日之後的第一個台股交易日
        idx = move.index.searchsorted(tw_ret.index, side="left") - 1
        ok = idx >= 0
        x = pd.Series(np.where(ok, move.values[np.clip(idx, 0, None)], np.nan), index=tw_ret.index)
        # 太舊的（停盤很久）不要配
        gap = pd.Series(tw_ret.index, index=tw_ret.index) - pd.Series(
            np.where(ok, move.index.values[np.clip(idx, 0, None)], np.datetime64("NaT")),
            index=tw_ret.index)
        x[gap > pd.Timedelta(days=5)] = np.nan
    else:
        x = move.reindex(tw_ret.index)
    both = pd.concat([x, tw_ret], axis=1).dropna()
    if len(both) < 30:
        return None
    c = both.iloc[:, 0].corr(both.iloc[:, 1])
    return _r(c, 2)


def build() -> dict:
    series = load_series()
    tw = series.get("加權指數", pd.Series(dtype=float))
    groups, plot, asof = [], {}, None
    for gname, note, items in GROUPS:
        rows = []
        for name, dec, mode in items:
            s = series.get(name)
            if s is None or s.empty:
                continue
            rate = name in RATE_ITEMS
            last_date = s.index[-1]
            asof = max(asof, last_date) if asof is not None else last_date
            row = {"name": name, "date": last_date.strftime("%Y-%m-%d"),
                   "last": _r(s.iloc[-1], dec), "dec": dec, "unit": "pt" if rate else "%",
                   "d1": _r(_change(s, 1, rate)),
                   "d5": _r(_change(s, 5, rate)), "d20": _r(_change(s, 20, rate)),
                   "d60": _r(_change(s, 60, rate)), "ytd": _r(_ytd(s, rate)),
                   "corr": None if name == "加權指數" else _corr(s, tw, mode, rate),
                   "mode": mode,
                   "spark": [_sig(v) for v in s.tail(SPARK_DAYS)]}
            rows.append(row)
            tail = s.tail(SERIES_DAYS)
            plot[name] = [[d.strftime("%Y-%m-%d") for d in tail.index], [_sig(v) for v in tail]]
        if rows:
            groups.append({"name": gname, "note": note, "items": rows})
    flat = {r["name"]: r for g in groups for r in g["items"]}
    key = [{"name": n, "last": flat[n]["last"], "dec": flat[n]["dec"], "d1": flat[n]["d1"],
            "unit": flat[n]["unit"], "date": flat[n]["date"]} for n in KEY_ITEMS if n in flat]
    return {"asof": asof.strftime("%Y-%m-%d") if asof is not None else "",
            "groups": groups, "series": plot, "key": key, "corr_days": CORR_DAYS}


def digest_lines(g: dict | None = None) -> list[str]:
    """給盤前／盤後摘要的國際市場重點（Claude 讀的文字）。"""
    g = g or build()
    out = []
    for grp in g.get("groups", []):
        parts = []
        for r in grp["items"]:
            if r["d1"] is None:
                continue
            chg = f"{r['d1']:+.2f}{'個百分點' if r['unit'] == 'pt' else '%'}"
            parts.append(f"{r['name']} {r['last']:,.{r['dec']}f}（{chg}，{r['date'][5:]}）")
        if parts:
            out.append(f"{grp['name']}：" + "、".join(parts))
    return out
