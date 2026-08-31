"""
黃金價格資料層

資料以 CSV 保存（data/gold_prices.csv），欄位：
    item        商品名稱（目前只有「COMEX 黃金期貨」一項）
    price_date  日期 YYYY-MM-DD
    price_usd   收盤價（USD / 盎司）

以 (item, price_date) 為唯一鍵。

原本指定的來源 truney.com 有 Cloudflare 人機驗證，連真實瀏覽器都會被擋在
「正在執行安全驗證」頁，無法用於自動更新，因此改用 Yahoo Finance。
"""
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "gold_prices.csv"

COLUMNS = ["item", "price_date", "price_usd"]

# (Yahoo Finance 代碼, 顯示名稱)。這裡是商品定義的唯一來源，gold_scraper 也從這裡取用。
SYMBOLS = [
    ("GC=F", "COMEX 黃金期貨"),
]
SYMBOL_ORDER = [name for _, name in SYMBOLS]


def load_gold() -> pd.DataFrame:
    """讀取 CSV，回傳依日期排序的 DataFrame。檔案不存在時回傳空 DataFrame。"""
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(CSV_PATH)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce")
    df = df.dropna(subset=["price_date"])
    df["item"] = pd.Categorical(df["item"], categories=SYMBOL_ORDER, ordered=True)
    df = df.dropna(subset=["item"])
    df = df.sort_values(["price_date", "item"]).reset_index(drop=True)
    df["item"] = df["item"].astype(str)
    return df


def latest_date(df: pd.DataFrame) -> str:
    """回傳資料中最新的日期字串（YYYY-MM-DD）；無資料時回傳空字串。"""
    if df.empty:
        return ""
    return pd.to_datetime(df["price_date"]).max().strftime("%Y-%m-%d")


def merge_prices(rows: list[dict]) -> int:
    """
    將爬蟲回傳的金價併入 CSV，回傳實際新增的筆數。

    rows: [{"項目": str, "收盤": float, "日期": "YYYY-MM-DD"}, ...]

    已存在的 (item, price_date) 一律略過，不覆寫既有數值。
    """
    if not rows:
        return 0

    incoming = pd.DataFrame(
        [
            {
                "item": str(r["項目"]).strip(),
                "price_date": str(r["日期"]).strip(),
                "price_usd": r["收盤"],
            }
            for r in rows
            if r.get("項目") and r.get("日期") and r.get("收盤") is not None
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
