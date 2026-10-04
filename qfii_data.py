"""
外資持股比率（python update_data.py qfii）

    上市  證交所 fund/MI_QFIIS（外資及陸資投資持股統計，可指定日期）
    上櫃  櫃買中心 insti/qfii（僑外資及陸資持股比例排行表，可指定日期）

存 data/chips/qfii.parquet：date（YYYY-MM-DD）、code、market（twse／tpex）、pct（全體外資及陸資持股比率 %）。
每次補最近還沒有的交易日（交易日以 data/market/daily 的日期檔與加權指數的收盤日為準）；第一次回補 BACKFILL 個交易日。
留 KEEP_DAYS 個交易日。
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from market_scraper import TPEX_OPENAPI

BASE_DIR = Path(__file__).resolve().parent
PATH = BASE_DIR / "data" / "chips" / "qfii.parquet"
COLUMNS = ["date", "code", "market", "pct"]
BACKFILL = 60
PER_RUN = 20
KEEP_DAYS = 300

log = logging.getLogger("qfii")


def _pct(v):
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def parse_twse(payload: dict | None) -> list[tuple]:
    if not payload or payload.get("stat") != "OK":
        return []
    fields = payload.get("fields") or []
    try:
        ci = fields.index("證券代號")
        pi = fields.index("全體外資及陸資持股比率")
    except ValueError:
        return []
    out = []
    for r in payload.get("data") or []:
        code, pct = str(r[ci]).strip(), _pct(r[pi])
        if code and pct is not None:
            out.append((code, pct))
    return out


def parse_tpex(payload: dict | None) -> list[tuple]:
    tables = (payload or {}).get("tables") or []
    if not tables:
        return []
    t = tables[0]
    fields = t.get("fields") or []
    ci = next((i for i, f in enumerate(fields) if f.startswith("代號")), None)
    pi = next((i for i, f in enumerate(fields) if f.startswith("僑外資及陸資持股比率")), None)
    if ci is None or pi is None:
        return []
    out = []
    for r in t.get("data") or []:
        code, pct = str(r[ci]).strip(), _pct(r[pi])
        if code and pct is not None:
            out.append((code, pct))
    return out


def load() -> pd.DataFrame:
    if not PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_parquet(PATH)


def fetch_market(scraper, day: date, market: str) -> list[tuple]:
    if market == "twse":
        return parse_twse(scraper._twse(f"fund/MI_QFIIS?date={day:%Y%m%d}&selectType=ALLBUT0999&response=json"))
    return parse_tpex(scraper._tpex(f"insti/qfii?type=Daily&date={day:%Y/%m/%d}&response=json"))


def tpex_latest(scraper) -> tuple[str, list[tuple]]:
    """櫃買 openapi（只有最新一天）：www 擋下時的備援。"""
    rows = scraper._get(TPEX_OPENAPI + "tpex_3insti_qfii", "tpex", 1.0) or []
    day, out = "", []
    for r in rows:
        roc = str(r.get("Date") or "")
        if len(roc) == 7 and roc.isdigit():
            day = f"{int(roc[:3]) + 1911}-{roc[3:5]}-{roc[5:]}"
        code, pct = str(r.get("SecuritiesCompanyCode") or "").strip(), _pct(r.get("PercentageOfSharesOC/FMIHeld"))
        if code and pct is not None:
            out.append((code, pct))
    return day, out


def trading_days() -> list[date]:
    """交易日：日期檔（9 月起）＋加權指數有收盤的日子（較早的歷史）。"""
    import market_data as md
    from xmarket_data import load_xmarket
    tw = load_xmarket(["加權指數"])
    days = set(md.dates()) | {d.date() for d in pd.to_datetime(tw["price_date"])}
    return sorted(d for d in days if d <= date.today())


def update(logger: logging.Logger | None = None, backfill: int = BACKFILL, per_run: int = PER_RUN) -> int:
    """上市、上櫃分開補：一邊被擋（櫃買 www 常回 520）不影響另一邊，下次排程再補。"""
    from market_scraper import MarketScraper
    lg = logger or log
    have = load()
    days = trading_days()[-backfill:]
    scraper = MarketScraper(logger=lg)
    frames, added = [], 0
    for market in ("twse", "tpex"):
        done = set(have[have["market"] == market]["date"]) if not have.empty else set()
        want = [d for d in days if d.isoformat() not in done]
        if done:
            want = want[-per_run:]                     # 第一次整段回補，之後一次最多 per_run 天
        fails = 0
        for d in reversed(want):                       # 新的先抓
            rows = fetch_market(scraper, d, market)
            if not rows:
                fails += 1
                if fails >= 3:
                    lg.warning(f"外資持股：{market} 連續失敗，下次再補")
                    break
                continue
            fails = 0
            frames.append(pd.DataFrame([(d.isoformat(), c, market, p) for c, p in rows], columns=COLUMNS))
            added += 1
        if market == "tpex" and want and (not frames or all(f["market"].iloc[0] != "tpex" for f in frames)):
            day, rows = tpex_latest(scraper)
            if day and rows and day not in done:
                frames.append(pd.DataFrame([(day, c, "tpex", p) for c, p in rows], columns=COLUMNS))
                added += 1
                lg.info(f"外資持股：櫃買 www 抓不到，用 openapi 補 {day}")
    if not frames:
        lg.info("外資持股：沒有新資料")
        return 0
    out = pd.concat([have] + frames, ignore_index=True).drop_duplicates(["date", "code"], keep="last")
    keep = sorted(out["date"].unique())[-KEEP_DAYS:]
    out = out[out["date"].isin(keep)].sort_values(["date", "code"]).reset_index(drop=True)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PATH, index=False, compression="zstd")
    lg.info(f"外資持股：新增 {added} 個市場日")
    return added


def matrix(days: int = 130) -> pd.DataFrame:
    """日期 × 代號 的持股比率。"""
    df = load()
    if df.empty:
        return pd.DataFrame()
    keep = sorted(df["date"].unique())[-days:]
    df = df[df["date"].isin(keep)]
    return df.pivot_table(index="date", columns="code", values="pct", aggfunc="last").sort_index()


def changes(names: dict, industries: dict, liquid: set | None = None, window: int = 20,
            top: int = 20) -> dict:
    """外資持股比率近 window 日增加／減少最多（百分點）。"""
    m = matrix(window + 1)
    if len(m) < 2:
        return {"asof": "", "window": window, "up": [], "down": []}
    # 各檔用自己視窗內最早、最新的一筆（上櫃可能比上市晚開始累積、或少抓幾天）
    first = m.bfill().iloc[0]
    last = m.ffill().iloc[-1]
    chg = (last - first).dropna()
    chg = chg[m.notna().sum() >= 2]
    if liquid is not None:
        chg = chg[chg.index.isin(liquid)]
    chg = chg[chg.index.isin(names.keys())]

    def rows(s):
        return [[c, names.get(c, ""), industries.get(c, ""), round(float(last[c]), 2), round(float(v), 2)]
                for c, v in s.items()]
    return {"asof": m.index[-1], "from": m.index[0], "window": len(m) - 1,
            "up": rows(chg.sort_values(ascending=False).head(top)),
            "down": rows(chg.sort_values().head(top))}
