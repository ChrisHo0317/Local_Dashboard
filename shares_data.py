"""
已發行股數（python update_data.py shares）：市場熱度「權值股」分項用，市值＝收盤價 × 股數

    上市  證交所 OpenAPI opendata/t187ap03_L（上市公司基本資料）的「已發行普通股數或TDR原股發行股數」
    上櫃  櫃買中心 OpenAPI mopsfin_t187ap03_O（上櫃公司基本資料）的 IssueShares

存 data/market/shares.csv：code、shares、date（抓到的日期）。股數很少變（增資、減資、轉換公司債），
每天早上重抓一次；某個市場抓不到（或筆數太少，像是被擋）就沿用舊資料，不會讓排程失敗。
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from market_scraper import TPEX_OPENAPI, TWSE_OPENAPI

BASE_DIR = Path(__file__).resolve().parent
PATH = BASE_DIR / "data" / "market" / "shares.csv"
MIN_ROWS = 300            # 一個市場少於這麼多筆，當作沒抓到

SOURCES = {
    "twse": (TWSE_OPENAPI + "opendata/t187ap03_L", "公司代號", "已發行普通股數或TDR原股發行股數"),
    "tpex": (TPEX_OPENAPI + "mopsfin_t187ap03_O", "SecuritiesCompanyCode", "IssueShares"),
}


def parse(rows, code_key: str, share_key: str) -> dict[str, float]:
    out = {}
    for r in rows or []:
        code = str(r.get(code_key, "")).strip()
        try:
            n = float(str(r.get(share_key, "")).replace(",", "").strip())
        except ValueError:
            continue
        if code and n > 0:
            out[code] = n
    return out


def load(path: Path = PATH) -> pd.Series:
    """代號 → 股數；沒有檔案就是空的（權值股分項會略過）。"""
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path, dtype={"code": str})
    return df.set_index("code")["shares"].astype(float)


def update(log: logging.Logger | None = None, path: Path = PATH) -> int:
    from intel_data import today_taipei
    from market_scraper import MarketScraper

    log = log or logging.getLogger("shares")
    scraper = MarketScraper(logger=log)
    merged = load(path).to_dict()
    changed = 0
    for market, (url, code_key, share_key) in SOURCES.items():
        got = parse(scraper._get(url, market + "-open", 1.0), code_key, share_key)
        if len(got) < MIN_ROWS:
            log.warning(f"股數：{market} 只拿到 {len(got)} 筆，沿用舊資料")
            continue
        changed += sum(1 for c, n in got.items() if merged.get(c) != n)
        merged.update(got)
    if not changed:
        log.info("股數：沒有變動")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"code": list(merged), "shares": list(merged.values())}).sort_values("code")
    df["shares"] = df["shares"].astype("int64")
    df["date"] = today_taipei().isoformat()
    df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    log.info(f"股數：{len(df)} 檔，{changed} 檔有變動")
    return changed
