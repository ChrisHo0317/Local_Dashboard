"""
全市場每日快照（上市＋上櫃）

    data/market/daily/YYYY-MM-DD.parquet   每個交易日一個檔
    data/market/summary.csv                每日大盤摘要，一天一列
    data/market/stocks.csv                 股票清單（代號、名稱、市場、產業）

日期檔當天會被補寫幾次（收盤行情傍晚出、融資融券晚上才出），補齊之後
就不再變動 —— git 只會多出新檔，舊檔不改，歷史才不會越長越肥。

日期檔欄位：
    code, market                  代號、twse／tpex
    open high low close           開高低收
    volume, turnover              成交股數、成交金額（元）
    foreign, trust, dealer        三大法人買賣超（股）
    margin_bal, short_bal         融資、融券餘額（張）
    per, yield_pct, pbr           本益比、殖利率（%）、股價淨值比
"""
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
MARKET_DIR = BASE_DIR / "data" / "market"
DAILY_DIR = MARKET_DIR / "daily"
SUMMARY_CSV = MARKET_DIR / "summary.csv"
STOCKS_CSV = MARKET_DIR / "stocks.csv"
EVENTS_CSV = MARKET_DIR / "adjust_events.csv"   # 除權息、減資、變更面額（還原權值）
FLAGS_CSV = MARKET_DIR / "flags.csv"            # 注意股、處置股
PATCH_DIR = MARKET_DIR / "patch"                # 歷史底稿的修補（零價、參考價），一天一個市場一檔

GROUPS = {
    # ref：參考價（收盤 − 漲跌），還原權值用；舊的日期檔沒有這欄
    "quotes": ["open", "high", "low", "close", "volume", "turnover", "ref"],
    "insti": ["foreign", "trust", "dealer"],
    "margin": ["margin_bal", "short_bal"],
    "valuation": ["per", "yield_pct", "pbr"],
}
VALUE_COLUMNS = [c for cols in GROUPS.values() for c in cols]
COLUMNS = ["code", "market"] + VALUE_COLUMNS

# 法人金額與融資金額上市、上櫃分開存：兩個市場可能在不同次排程才抓齊，
# 各自一欄才不會被只抓到一半的加總蓋掉。加總留到產生頁面時做。
SUMMARY_COLUMNS = [
    "date",
    "twse_index", "twse_index_chg", "tpex_index", "tpex_index_chg",
    "twse_turnover", "tpex_turnover",
    "twse_foreign_value", "tpex_foreign_value",
    "twse_trust_value", "tpex_trust_value",
    "twse_dealer_value", "tpex_dealer_value",
    "twse_margin_amount", "twse_margin_amount_prev",
    "tpex_margin_amount", "tpex_margin_amount_prev",
]
STOCK_COLUMNS = ["code", "name", "market", "industry"]

# 普通股是四碼；ETF 是 00 開頭的五、六碼（可能帶一個字母）。
# 權證、牛熊證、公司債、存託憑證都不收，檔案才不會被幾千檔權證撐大。
CODE_PATTERN = r"^(\d{4}|00\d{2,4}[A-Z]?)$"


def _path(day: date) -> Path:
    return DAILY_DIR / f"{day.isoformat()}.parquet"


def dates() -> list[date]:
    """已有日期檔的交易日，由舊到新。"""
    if not DAILY_DIR.exists():
        return []
    return sorted(date.fromisoformat(p.stem) for p in DAILY_DIR.glob("*.parquet"))


def load_day(day: date) -> pd.DataFrame:
    path = _path(day)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_parquet(path)


def load_days(days: list[date]) -> pd.DataFrame:
    """把多天的日期檔接成一張長表，多一個 date 欄。"""
    frames = []
    for d in days:
        df = load_day(d)
        if not df.empty:
            frames.append(df.assign(date=pd.Timestamp(d)))
    if not frames:
        return pd.DataFrame(columns=["date"] + COLUMNS)
    return pd.concat(frames, ignore_index=True)


def keep_codes(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["code"].astype(str).str.match(CODE_PATTERN)]


def present_groups(day: date) -> dict[str, set[str]]:
    """{市場: 已有資料的欄位組}，用來判斷還缺什麼要補抓。"""
    df = load_day(day)
    out = {"twse": set(), "tpex": set()}
    if df.empty:
        return out
    for market in out:
        part = df[df["market"] == market]
        for group, cols in GROUPS.items():
            if not part.empty and part[cols].notna().any().any():
                out[market].add(group)
    return out


def save_day(day: date, incoming: pd.DataFrame) -> bool:
    """
    把新抓到的欄位併進當天的檔。已有的值不會被空值蓋掉。
    回傳檔案內容是否有變。
    """
    if incoming is None or incoming.empty:
        return False
    incoming = keep_codes(incoming.copy())
    incoming["code"] = incoming["code"].astype(str)
    for col in COLUMNS:
        if col not in incoming.columns:
            incoming[col] = pd.NA
    incoming = incoming[COLUMNS].drop_duplicates("code", keep="last").set_index("code")

    old = load_day(day)
    if old.empty:
        merged = incoming
    else:
        old = old.set_index("code")
        merged = incoming.combine_first(old)
        # combine_first 以 incoming 為主；incoming 的空值才用舊值補
    merged = merged.reset_index()[COLUMNS]
    for col in VALUE_COLUMNS:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").astype("float64")
    merged["market"] = merged["market"].astype(str)
    merged = merged.sort_values("code").reset_index(drop=True)

    if not old.empty:
        before = old.reset_index()[COLUMNS].sort_values("code").reset_index(drop=True)
        for col in VALUE_COLUMNS:
            before[col] = pd.to_numeric(before[col], errors="coerce").astype("float64")
        before["market"] = before["market"].astype(str)
        if before.equals(merged):
            return False

    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(_path(day), index=False, compression="zstd")
    return True


# ── 大盤摘要 ────────────────────────────────────────────────
def load_summary() -> pd.DataFrame:
    if not SUMMARY_CSV.exists():
        return pd.DataFrame(columns=SUMMARY_COLUMNS)
    df = pd.read_csv(SUMMARY_CSV, dtype={"date": str})
    return df.reindex(columns=SUMMARY_COLUMNS)


def merge_summary(day: date, values: dict) -> bool:
    """更新某一天的摘要；只寫入有值的欄位。"""
    values = {k: v for k, v in values.items() if k in SUMMARY_COLUMNS and v is not None}
    if not values:
        return False
    df = load_summary()
    key = day.isoformat()
    if (df["date"] == key).any():
        idx = df.index[df["date"] == key][0]
        changed = False
        for k, v in values.items():
            old = df.at[idx, k]
            if pd.isna(old) or float(old) != float(v):
                df.at[idx, k] = v
                changed = True
        if not changed:
            return False
    else:
        row = {c: pd.NA for c in SUMMARY_COLUMNS}
        row.update(values)
        row["date"] = key
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df = df.sort_values("date").reset_index(drop=True)
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(SUMMARY_CSV, index=False, encoding="utf-8", lineterminator="\n")
    return True


# ── 股票清單 ────────────────────────────────────────────────
def load_stocks() -> pd.DataFrame:
    if not STOCKS_CSV.exists():
        return pd.DataFrame(columns=STOCK_COLUMNS)
    return pd.read_csv(STOCKS_CSV, dtype=str).fillna("").reindex(columns=STOCK_COLUMNS)


def merge_stocks(rows: pd.DataFrame) -> bool:
    """
    新名稱覆蓋舊名稱（公司會改名）；產業只在新資料有值時才覆蓋。
    清單只增不減 —— 下市的股票歷史資料還在，查詢時仍要找得到名字。
    """
    if rows is None or rows.empty:
        return False
    rows = rows.reindex(columns=STOCK_COLUMNS).fillna("").astype(str)
    rows = keep_codes(rows).drop_duplicates("code", keep="last").set_index("code")
    old = load_stocks().set_index("code")
    merged = old.copy()
    for code, r in rows.iterrows():
        if code in merged.index:
            for col in ("name", "market", "industry"):
                if r[col]:
                    merged.at[code, col] = r[col]
        else:
            merged.loc[code] = r
    merged = merged.reset_index().rename(columns={"index": "code"})
    merged = merged.reindex(columns=STOCK_COLUMNS).sort_values("code").reset_index(drop=True)
    before = old.reset_index().reindex(columns=STOCK_COLUMNS).sort_values("code").reset_index(drop=True)
    if before.equals(merged):
        return False
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(STOCKS_CSV, index=False, encoding="utf-8", lineterminator="\n")
    return True


# ── 權值事件、注意／處置、歷史修補 ──────────────────────────
EVENT_COLUMNS = ["date", "code", "market", "kind", "before", "ref", "factor"]
FLAG_COLUMNS = ["date", "code", "name", "market", "kind", "start", "end", "detail"]


def _load_csv(path: Path, cols: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=cols)
    return pd.read_csv(path, dtype=str).fillna("").reindex(columns=cols)


def load_events() -> pd.DataFrame:
    df = _load_csv(EVENTS_CSV, EVENT_COLUMNS)
    for col in ("before", "ref", "factor"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def merge_events(rows: list[dict]) -> int:
    """同一天同一檔只留一筆（後抓到的為準）。回傳新增筆數。"""
    if not rows:
        return 0
    old = _load_csv(EVENTS_CSV, EVENT_COLUMNS)
    new = pd.DataFrame(rows).reindex(columns=EVENT_COLUMNS).astype(str)
    merged = (pd.concat([old, new], ignore_index=True)
              .drop_duplicates(["date", "code"], keep="last")
              .sort_values(["date", "code"]).reset_index(drop=True))
    if len(merged) == len(old) and merged.equals(old.sort_values(["date", "code"]).reset_index(drop=True)):
        return 0
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(EVENTS_CSV, index=False, lineterminator="\n")
    return len(merged) - len(old)


def load_flags() -> pd.DataFrame:
    return _load_csv(FLAGS_CSV, FLAG_COLUMNS)


def merge_flags(rows: list[dict], keep_days: int = 400) -> int:
    if not rows:
        return 0
    old = _load_csv(FLAGS_CSV, FLAG_COLUMNS)
    new = pd.DataFrame(rows).reindex(columns=FLAG_COLUMNS).fillna("").astype(str)
    merged = pd.concat([old, new], ignore_index=True).drop_duplicates(
        ["date", "code", "kind"], keep="last")
    cutoff = (pd.Timestamp.today() - pd.Timedelta(days=keep_days)).strftime("%Y-%m-%d")
    merged = merged[merged["date"] >= cutoff].sort_values(["date", "code"]).reset_index(drop=True)
    before = old.sort_values(["date", "code"]).reset_index(drop=True)
    if len(merged) == len(before) and merged.equals(before):
        return 0
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(FLAGS_CSV, index=False, lineterminator="\n")
    return max(len(merged) - len(before), 1)


PATCH_COLUMNS = ["code", "open", "high", "low", "close", "ref"]


def patch_path(day: date, market: str) -> Path:
    return PATCH_DIR / f"{day.isoformat()}_{market}.parquet"


def save_patch(day: date, market: str, df: pd.DataFrame) -> None:
    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    out = df.reindex(columns=PATCH_COLUMNS).copy()
    out["code"] = out["code"].astype(str)
    for col in PATCH_COLUMNS[1:]:
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("float32")
    out.to_parquet(patch_path(day, market), index=False, compression="zstd")


def load_patches() -> pd.DataFrame:
    """所有修補合成一張表：date, code + PATCH_COLUMNS。"""
    frames = []
    for path in sorted(PATCH_DIR.glob("*.parquet")) if PATCH_DIR.exists() else []:
        df = pd.read_parquet(path)
        df["date"] = pd.Timestamp(path.stem.split("_")[0])
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["date"] + PATCH_COLUMNS)
    return pd.concat(frames, ignore_index=True)
