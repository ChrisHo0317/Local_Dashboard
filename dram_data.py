"""
DRAM 報價資料層

app.py（本地 Dash 版）與 build_static.py（GitHub Pages 靜態版）共用此模組，
確保兩邊看到的資料完全一致。

資料以 CSV 保存（data/dram_prices.csv），欄位：
    item        型號（如 "DDR5 16Gb (2Gx8) 4800/5600"）
    price_date  報價日期 YYYY-MM-DD
    avg_price   盤平均（USD）

以 (item, price_date) 為唯一鍵，對應原 SQLite schema 的 UNIQUE(item, price_date)。
"""
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "dram_prices.csv"

COLUMNS = ["item", "price_date", "avg_price"]


def load_dram() -> pd.DataFrame:
    """讀取 CSV，回傳依日期排序的 DataFrame。檔案不存在時回傳空 DataFrame。"""
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(CSV_PATH)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce")
    df = df.dropna(subset=["price_date"])
    return df.sort_values(["price_date", "item"]).reset_index(drop=True)


def latest_date(df: pd.DataFrame) -> str:
    """回傳資料中最新的報價日期字串（YYYY-MM-DD）；無資料時回傳空字串。"""
    if df.empty:
        return ""
    return pd.to_datetime(df["price_date"]).max().strftime("%Y-%m-%d")


def merge_prices(rows: list[dict]) -> int:
    """
    將爬蟲回傳的報價併入 CSV，回傳實際新增的筆數。

    rows: [{"項目": str, "盤平均": float, "日期": "YYYY-MM-DD"}, ...]
          （沿用 scraper.TrendForceScraper.fetch_dram_spot 的輸出格式）

    已存在的 (item, price_date) 一律略過，不覆寫既有數值。
    """
    if not rows:
        return 0

    incoming = pd.DataFrame(
        [
            {
                "item": str(r["項目"]).strip(),
                "price_date": str(r["日期"]).strip(),
                "avg_price": r["盤平均"],
            }
            for r in rows
            if r.get("項目") and r.get("日期") and r.get("盤平均") is not None
        ],
        columns=COLUMNS,
    )
    if incoming.empty:
        return 0

    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, dtype={"price_date": str})
    else:
        existing = pd.DataFrame(columns=COLUMNS)

    before = len(existing)
    combined = pd.concat([existing, incoming], ignore_index=True)
    combined = combined.drop_duplicates(subset=["item", "price_date"], keep="first")
    combined = combined.sort_values(["price_date", "item"]).reset_index(drop=True)

    added = len(combined) - before
    if added > 0:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        combined.to_csv(CSV_PATH, index=False, encoding="utf-8")

    return added
