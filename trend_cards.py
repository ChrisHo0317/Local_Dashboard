"""
總覽「走勢」子分頁的精簡卡片（site/data/trend.json）

原本底部的「走勢圖」分頁（DRAM、美債、黃金、BTC、美股、匯率）搬進總覽：
上方每個商品一張卡（最新值、日／週／月變化、近 60 筆小走勢線），點卡片在下方展開原本的完整圖。
完整圖的資料仍是 build_static 產生的 data/charts/{key}.json，這裡只做卡片要的摘要。

    [{id, tab, title, date, rows: [{name, last, dec, unit, d1, d5, d20}], spark, more}]
    unit：% 是漲跌幅；pt 是殖利率的變動（百分點）
"""
from __future__ import annotations

import math

import pandas as pd

SPARK = 60
# 各卡片要列的項目（沒列的話取前幾項）、小數位數
PICK = {
    "dram": ["DDR5 16Gb (2Gx8) 4800/5600", "DDR4 16Gb (1Gx16)3200", "DDR4 8Gb (1Gx8) 3200"],
    "bond": ["2年期", "10年期", "30年期"],
    "usidx": ["費城半導體", "那斯達克"],
}
DEC = {"dram": 3, "bond": 2, "gold": 1, "btc": 0, "usidx": 2, "fx": 3}
RATE = {"bond"}
# 卡片很窄，名稱要短（完整名稱在下方的完整圖）
SHORT = {"DDR5 16Gb (2Gx8) 4800/5600": "DDR5 16G", "DDR4 16Gb (1Gx16)3200": "DDR4 16G",
         "DDR4 8Gb (1Gx8) 3200": "DDR4 8G", "COMEX 黃金期貨": "黃金", "費城半導體": "費半",
         "美元兌台幣": "美元/台幣", "2年期": "2 年", "10年期": "10 年", "30年期": "30 年"}


def _r(v, d=2):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), d)


def _value_col(df: pd.DataFrame) -> str:
    return next(c for c in df.columns if c not in ("item", "price_date"))


def _chg(s: pd.Series, n: int, rate: bool):
    if len(s) <= n:
        return None
    a, b = float(s.iloc[-1 - n]), float(s.iloc[-1])
    if rate:
        return b - a
    return (b / a - 1) * 100 if a else None


def card(member: dict, df: pd.DataFrame) -> dict:
    key = member["id"]
    out = {"id": key, "tab": member["tab"], "title": member["title"], "date": "", "rows": [],
           "spark": [], "more": 0}
    if df is None or df.empty:
        return out
    col = _value_col(df)
    df = df.dropna(subset=[col])
    items = [str(x) for x in pd.unique(df["item"])]
    names = [n for n in PICK.get(key, []) if n in items] or items[:3]
    rate, dec = key in RATE, DEC.get(key, 2)
    series = {}
    for name in names:
        g = df[df["item"] == name].sort_values("price_date")
        s = pd.Series(g[col].astype(float).values, index=pd.to_datetime(g["price_date"]))
        series[name] = s[~s.index.duplicated(keep="last")]
    for name, s in series.items():
        if s.empty:
            continue
        out["rows"].append({"name": SHORT.get(name, name), "last": _r(s.iloc[-1], dec), "dec": dec,
                            "unit": "pt" if rate else "%", "d1": _r(_chg(s, 1, rate)),
                            "d5": _r(_chg(s, 5, rate)), "d20": _r(_chg(s, 20, rate)),
                            "date": s.index[-1].strftime("%Y-%m-%d")})
    if key == "bond" and "2年期" in series and "10年期" in series:
        both = pd.concat([series["10年期"], series["2年期"]], axis=1, join="inner").dropna()
        spread = both.iloc[:, 0] - both.iloc[:, 1]
        if len(spread):
            out["rows"].append({"name": "10−2 利差", "last": _r(spread.iloc[-1], 2), "dec": 2,
                                "unit": "pt", "d1": _r(_chg(spread, 1, True)), "d5": _r(_chg(spread, 5, True)),
                                "d20": _r(_chg(spread, 20, True)),
                                "date": spread.index[-1].strftime("%Y-%m-%d")})
    first = next(iter(series.values()), pd.Series(dtype=float))
    out["spark"] = [_r(v, 4) for v in first.tail(SPARK)]
    out["date"] = max((r["date"] for r in out["rows"]), default="")
    out["more"] = max(0, len(items) - len(names))
    return out


def build(members: list[dict], frames: dict) -> list[dict]:
    """members：build_static.TREND_CHARTS；frames：{id: 該項目的 DataFrame}。"""
    return [card(m, frames.get(m["id"])) for m in members]
