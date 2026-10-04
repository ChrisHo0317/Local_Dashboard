"""
法人說明會（python update_data.py calls）

來源：公開資訊觀測站「法人說明會一覽表」（mopsov.twse.com.tw 的 ajax_t100sb02_1，上市 sii、上櫃 otc，
依年月查詢）。每次抓上個月、這個月、下個月，同一個（市場, 年月）整批取代（公司會改期或取消）。

存 data/earnings_calls.csv：code, name, market, date（YYYY-MM-DD）, time, place, summary；留 2 年。
"""
from __future__ import annotations

import html
import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "earnings_calls.csv"
URL = "https://mopsov.twse.com.tw/mops/web/ajax_t100sb02_1"
COLUMNS = ["code", "name", "market", "date", "time", "place", "summary"]
MARKETS = {"twse": "sii", "tpex": "otc"}
KEEP_DAYS = 730

log = logging.getLogger("calls")

_ROW = re.compile(r"<tr[^>]*data-type='body'[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_ROC = re.compile(r"(\d{2,3})/(\d{1,2})/(\d{1,2})")


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", cell))).strip()


def parse(page: str, market: str) -> list[dict]:
    out = []
    for row in _ROW.findall(page or ""):
        cells = [_text(c) for c in _CELL.findall(row)]
        if len(cells) < 6:
            continue
        m = _ROC.search(cells[2])
        code = cells[0].strip()
        if not m or not code:
            continue
        y, mo, d = int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))
        try:
            day = date(y, mo, d).isoformat()
        except ValueError:
            continue
        out.append({"code": code, "name": cells[1], "market": market, "date": day,
                    "time": cells[3][:20], "place": cells[4][:80], "summary": cells[5][:300]})
    return out


def _months(today: date) -> list[tuple[int, int]]:
    out = []
    for k in (-1, 0, 1):
        y, m = today.year, today.month + k
        if m < 1:
            y, m = y - 1, m + 12
        elif m > 12:
            y, m = y + 1, m - 12
        out.append((y, m))
    return out


def load() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(CSV_PATH, dtype=str).fillna("")


def update(logger: logging.Logger | None = None, today: date | None = None) -> int:
    from curl_cffi import requests as cr
    lg = logger or log
    today = today or date.today()
    s = cr.Session(impersonate="chrome124")
    got: dict[tuple, list[dict]] = {}
    for market, typek in MARKETS.items():
        for y, m in _months(today):
            try:
                r = s.post(URL, data={"encodeURIComponent": "1", "step": "1", "firstin": "1", "off": "1",
                                      "TYPEK": typek, "year": str(y - 1911), "month": f"{m:02d}", "co_id": ""},
                           timeout=60)
                page = r.content.decode("utf-8", "replace")
            except Exception as e:
                lg.warning(f"法說會：{market} {y}-{m:02d} 讀取失敗 {e.__class__.__name__}")
                continue
            if r.status_code != 200 or "myTable" not in page and "查無" not in page and "無符合" not in page:
                lg.warning(f"法說會：{market} {y}-{m:02d} 回應不符（HTTP {r.status_code}）")
                continue
            got[(market, f"{y:04d}-{m:02d}")] = parse(page, market)
    if not got:
        lg.warning("法說會：全部失敗，本次不更新")
        return 0
    old = load()
    if not old.empty:
        ym = old["date"].str[:7]
        drop = pd.Series(False, index=old.index)
        for market, month in got:
            drop |= (old["market"] == market) & (ym == month)
        old = old[~drop]
    new = pd.DataFrame([r for rows in got.values() for r in rows], columns=COLUMNS)
    out = pd.concat([old, new], ignore_index=True).drop_duplicates(["code", "date", "time"], keep="last")
    cutoff = (pd.Timestamp(today) - pd.Timedelta(days=KEEP_DAYS)).date().isoformat()
    out = out[out["date"] >= cutoff].sort_values(["date", "time", "code"]).reset_index(drop=True)
    before = load()
    changed = len(before) != len(out) or not before.reset_index(drop=True).equals(out)
    if changed:
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(CSV_PATH, index=False, encoding="utf-8", lineterminator="\n")
    lg.info(f"法說會：{sum(len(v) for v in got.values())} 場（{len(got)} 個市場月）")
    return int(changed)


def upcoming(codes: set | None = None, start: str | None = None, days: int = 30) -> pd.DataFrame:
    """接下來 days 天的法說會；codes 給了就只留那些股票。"""
    df = load()
    if df.empty:
        return df
    start = start or date.today().isoformat()
    end = (pd.Timestamp(start) + pd.Timedelta(days=days)).date().isoformat()
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    if codes is not None:
        df = df[df["code"].isin(codes)]
    return df.sort_values(["date", "time"])
