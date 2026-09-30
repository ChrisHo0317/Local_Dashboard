"""
籌碼資料

    data/chips/tdcc/YYYY-MM-DD.parquet   集保戶股權分散（每週一個檔，只增不改）
        code, big1000（千張以上大戶持股比例 %）, big400（400 張以上）, holders（總人數）
    data/chips/futures.csv               三大法人臺股期貨未平倉淨口數（一天一列）
        date, foreign, trust, dealer

集保的開放資料只給最新一週、期交所的只給最新一天，歷史從現在開始累積。
"""
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CHIPS_DIR = BASE_DIR / "data" / "chips"
TDCC_DIR = CHIPS_DIR / "tdcc"
FUTURES_CSV = CHIPS_DIR / "futures.csv"
FUTURES_COLS = ["date", "foreign", "trust", "dealer"]


def tdcc_dates() -> list[date]:
    if not TDCC_DIR.exists():
        return []
    return sorted(date.fromisoformat(p.stem) for p in TDCC_DIR.glob("*.parquet"))


def save_tdcc(day: date, df: pd.DataFrame) -> bool:
    """同一週已經有檔就不動。"""
    path = TDCC_DIR / f"{day.isoformat()}.parquet"
    if path.exists() or df is None or df.empty:
        return False
    TDCC_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression="zstd")
    return True


def load_tdcc(last: int | None = None) -> pd.DataFrame:
    """所有週（或最近幾週）接成長表，多一個 date 欄。"""
    days = tdcc_dates()
    if last:
        days = days[-last:]
    frames = [pd.read_parquet(TDCC_DIR / f"{d.isoformat()}.parquet").assign(date=pd.Timestamp(d))
              for d in days]
    if not frames:
        return pd.DataFrame(columns=["date", "code", "big1000", "big400", "holders"])
    return pd.concat(frames, ignore_index=True)


def load_futures() -> pd.DataFrame:
    if not FUTURES_CSV.exists():
        return pd.DataFrame(columns=FUTURES_COLS)
    return pd.read_csv(FUTURES_CSV, dtype={"date": str})


def merge_futures(row: dict) -> bool:
    if not row or not row.get("date"):
        return False
    df = load_futures()
    if (df["date"] == row["date"]).any():
        return False
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True).sort_values("date")
    CHIPS_DIR.mkdir(parents=True, exist_ok=True)
    df[FUTURES_COLS].to_csv(FUTURES_CSV, index=False, encoding="utf-8", lineterminator="\n")
    return True
