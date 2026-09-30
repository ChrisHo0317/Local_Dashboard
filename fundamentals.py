"""
基本面歷史（逐期累積，不會被新一期覆蓋）

    data/fundamental/revenue.parquet     月營收：code, year, month, revenue（千元）
    data/fundamental/income.parquet      單季損益：code, year, quarter,
                                         revenue, gross, operating, net（千元）, eps（元）
    data/fundamental/pe_monthly.parquet  月本益比：code, ym, close, eps_ttm, pe
    data/fundamental/announce.parquet    重大訊息：code, name, market, date, time, subject, body

歷史的起點由 export_from_market_db.py 一次匯出，之後由排程把官方每一期的
最新資料併進來：

    月營收   官方清單只有最新一個月，但每列帶著「上月營收」，順便補上一個月
    損益表   官方給的是「年初至今累計」，這裡減掉同年度前幾季換成單季；
             前面有缺季就先不算，免得算出錯的單季數字
    缺月     公開資訊觀測站的歷史彙總頁（mopsov）還能依月份查，用來補洞
"""
import logging
import re
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
FUND_DIR = BASE_DIR / "data" / "fundamental"
REVENUE_PATH = FUND_DIR / "revenue.parquet"
INCOME_PATH = FUND_DIR / "income.parquet"
PE_PATH = FUND_DIR / "pe_monthly.parquet"
ANNOUNCE_PATH = FUND_DIR / "announce.parquet"

REVENUE_COLS = ["code", "year", "month", "revenue"]
INCOME_COLS = ["code", "year", "quarter", "revenue", "gross", "operating", "net", "eps"]
ANNOUNCE_COLS = ["code", "name", "market", "date", "time", "subject", "body"]
MONEY = ["revenue", "gross", "operating", "net"]

ANNOUNCE_KEEP_DAYS = 400
MOPS_URL = "https://mopsov.twse.com.tw/nas/t21/{mkt}/t21sc03_{roc}_{month}_{kind}.html"


def _num(value):
    text = str(value if value is not None else "").replace(",", "").strip()
    if text in ("", "-", "--", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _load(path: Path, cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_parquet(path)
    df["code"] = df["code"].astype(str)
    return df


def _save(df: pd.DataFrame, path: Path) -> None:
    FUND_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression="zstd")


def load_revenue() -> pd.DataFrame:
    return _load(REVENUE_PATH, REVENUE_COLS)


def load_income() -> pd.DataFrame:
    return _load(INCOME_PATH, INCOME_COLS)


def load_pe() -> pd.DataFrame:
    return _load(PE_PATH, ["code", "ym", "close", "eps_ttm", "pe"])


def load_announce() -> pd.DataFrame:
    return _load(ANNOUNCE_PATH, ANNOUNCE_COLS)


# ── 月營收 ──────────────────────────────────────────────────
def upsert_revenue(rows: pd.DataFrame, overwrite: bool = True) -> int:
    """
    併入月營收。overwrite=False 時只補「原本沒有」的月份（用「上月營收」補洞時，
    不該蓋掉已經有的正式數字）。回傳新增或改變的筆數。
    """
    if rows is None or rows.empty:
        return 0
    rows = rows.dropna(subset=["revenue"]).copy()
    rows["code"] = rows["code"].astype(str)
    rows["year"] = rows["year"].astype(int)
    rows["month"] = rows["month"].astype(int)
    rows["revenue"] = rows["revenue"].astype(float)
    rows = rows[REVENUE_COLS].drop_duplicates(["code", "year", "month"], keep="last")

    old = load_revenue()
    key = ["code", "year", "month"]
    merged = old.merge(rows, on=key, how="outer", suffixes=("", "_new"), indicator=True)
    new_val = merged["revenue_new"]
    if overwrite:
        take = new_val.notna()
    else:
        take = merged["revenue"].isna() & new_val.notna()
    changed = int((take & (merged["revenue"] != new_val)).sum())
    if not changed:
        return 0
    merged.loc[take, "revenue"] = new_val[take]
    out = merged[REVENUE_COLS].sort_values(key).reset_index(drop=True)
    out["year"] = out["year"].astype(int)
    out["month"] = out["month"].astype(int)
    _save(out, REVENUE_PATH)
    return changed


def revenue_from_list(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """官方最新一期清單 → (當月營收, 上月營收)。資料年月是民國 YYYMM。"""
    if df is None or df.empty:
        empty = pd.DataFrame(columns=REVENUE_COLS)
        return empty, empty
    ym = df["month"].astype(str).str.strip()
    ok = ym.str.fullmatch(r"\d{5}")
    df, ym = df[ok], ym[ok]
    year = ym.str[:3].astype(int) + 1911
    month = ym.str[3:].astype(int)
    cur = pd.DataFrame({"code": df["code"].astype(str), "year": year, "month": month,
                        "revenue": df["revenue"].map(_num)})
    prev_year = year.where(month > 1, year - 1)
    prev_month = (month - 2) % 12 + 1
    prev = pd.DataFrame({"code": df["code"].astype(str), "year": prev_year,
                         "month": prev_month, "revenue": df["prev_month"].map(_num)})
    return cur, prev


def parse_mops_revenue(html: str) -> pd.DataFrame:
    """公開資訊觀測站營收彙總頁：每列 代號, 名稱, 當月營收, 上月營收, 去年當月營收, …"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        code = tds[0].get_text(strip=True)
        if not re.fullmatch(r"\d{4}", code):
            continue
        value = _num(tds[2].get_text(strip=True))
        if value is not None:
            rows.append({"code": code, "revenue": value})
    return pd.DataFrame(rows, columns=["code", "revenue"])


def fetch_mops_revenue(year: int, month: int, session, logger=None) -> pd.DataFrame:
    """抓某一個月上市＋上櫃（本國與 KY 公司各一頁）的營收。"""
    logger = logger or logging.getLogger("fundamentals")
    frames = []
    for mkt in ("sii", "otc"):
        for kind in (0, 1):
            url = MOPS_URL.format(mkt=mkt, roc=year - 1911, month=month, kind=kind)
            try:
                resp = session.get(url, timeout=60)
                if resp.status_code != 200:
                    continue
                df = parse_mops_revenue(resp.content.decode("big5", errors="replace"))
            except Exception as e:
                logger.warning(f"營收彙總頁讀取失敗 {url}：{e}")
                continue
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=REVENUE_COLS)
    df = pd.concat(frames, ignore_index=True).drop_duplicates("code", keep="last")
    return df.assign(year=year, month=month)[REVENUE_COLS]


def revenue_gaps(latest: tuple[int, int], lookback: int = 6, ratio: float = 0.8) -> list:
    """
    最近幾個月裡，資料筆數明顯少於「最新一個月」的月份（例如匯出之後、
    排程開始之前的那幾個月）。回傳 [(年, 月), …]。
    """
    rev = load_revenue()
    if rev.empty:
        return []
    counts = rev.groupby(["year", "month"])["code"].nunique()
    target = counts.get(latest, 0) or counts.max()
    y, m = latest
    gaps = []
    for _ in range(lookback):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        if counts.get((y, m), 0) < target * ratio:
            gaps.append((y, m))
    return gaps


# ── 損益表：累計 → 單季 ────────────────────────────────────────
def to_single_quarter(ytd: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """
    ytd：官方的年初至今累計（code, year, quarter, 各金額, eps）。
    history：已有的單季資料。第 1 季直接用；第 n 季 = 累計 − 同年前 n−1 季單季合計，
    前面缺任何一季就跳過那家公司。
    """
    if ytd is None or ytd.empty:
        return pd.DataFrame(columns=INCOME_COLS)
    hist = history.set_index(["code", "year", "quarter"]) if not history.empty else None
    out = []
    for _, r in ytd.iterrows():
        code, year, q = str(r["code"]), int(r["year"]), int(r["quarter"])
        row = {"code": code, "year": year, "quarter": q}
        if q == 1:
            for col in MONEY + ["eps"]:
                row[col] = r[col]
            out.append(row)
            continue
        if hist is None:
            continue
        prev = [(code, year, i) for i in range(1, q)]
        if not all(p in hist.index for p in prev):
            continue
        before = hist.loc[prev]
        for col in MONEY + ["eps"]:
            val = r[col]
            if val is None or pd.isna(val) or before[col].isna().any():
                row[col] = None
            else:
                row[col] = round(float(val) - float(before[col].sum()), 2)
        out.append(row)
    return pd.DataFrame(out, columns=INCOME_COLS)


def income_from_list(df: pd.DataFrame) -> pd.DataFrame:
    """官方損益表清單（民國年、元／千元字串）→ 累計數字的表。"""
    if df is None or df.empty:
        return pd.DataFrame(columns=INCOME_COLS)
    out = pd.DataFrame({
        "code": df["code"].astype(str),
        "year": pd.to_numeric(df["year"], errors="coerce") + 1911,
        "quarter": pd.to_numeric(df["quarter"].astype(str).str.extract(r"(\d)")[0],
                                 errors="coerce"),
    })
    for col in MONEY + ["eps"]:
        out[col] = df[col].map(_num)
    return out.dropna(subset=["year", "quarter"]).astype({"year": int, "quarter": int})


def upsert_income(single: pd.DataFrame) -> int:
    """併入單季損益，同一季以新資料為準。回傳新增或改變的筆數。"""
    if single is None or single.empty:
        return 0
    old = load_income()
    key = ["code", "year", "quarter"]
    single = single[INCOME_COLS].drop_duplicates(key, keep="last")
    if not old.empty:
        joined = single.merge(old, on=key, how="left", suffixes=("", "_old"), indicator=True)
        same = joined["_merge"] == "both"
        for col in MONEY + ["eps"]:
            a, b = joined[col].astype(float), joined[f"{col}_old"].astype(float)
            same &= (a.round(2) == b.round(2)) | (a.isna() & b.isna())
        changed = int((~same).sum())
    else:
        changed = len(single)
    if not changed:
        return 0
    rest = old.merge(single[key], on=key, how="left", indicator=True)
    rest = rest[rest["_merge"] == "left_only"][INCOME_COLS]
    out = pd.concat([rest, single], ignore_index=True).sort_values(key).reset_index(drop=True)
    _save(out, INCOME_PATH)
    return changed


# ── 重大訊息 ────────────────────────────────────────────────
def append_announce(df: pd.DataFrame, today: pd.Timestamp | None = None) -> int:
    """新的重訊加進歷史；太舊的刪掉。回傳新增筆數。"""
    if df is None or df.empty:
        return 0
    rows = df.reindex(columns=ANNOUNCE_COLS).fillna("").astype(str)
    old = load_announce()
    key = ["code", "date", "time", "subject"]
    merged = pd.concat([old, rows], ignore_index=True).drop_duplicates(key, keep="first")
    added = len(merged) - len(old)
    today = today or pd.Timestamp.now(tz="Asia/Taipei").tz_localize(None)
    cutoff = today - pd.Timedelta(days=ANNOUNCE_KEEP_DAYS)
    roc = merged["date"].astype(str)
    ok = roc.str.fullmatch(r"\d{7}")
    greg = pd.to_datetime(
        (roc[ok].str[:3].astype(int) + 1911).astype(str) + roc[ok].str[3:], format="%Y%m%d",
        errors="coerce")
    when = pd.Series(pd.NaT, index=merged.index)
    when[ok] = greg
    merged = merged[when.isna() | (when >= cutoff)]
    if added <= 0 and len(merged) == len(old):
        return 0
    merged = merged.sort_values(["date", "time"], ascending=False).reset_index(drop=True)
    _save(merged[ANNOUNCE_COLS], ANNOUNCE_PATH)
    return max(added, 0)
