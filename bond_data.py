"""
美國公債殖利率資料層

與 dram_data.py 同樣的作法，但獨立一份：兩組資料的欄位與更新方式不同
（DRAM 每日累積一筆；殖利率可從 API 一次取回整段歷史並自我修補缺漏）。

資料以 CSV 保存（data/bond_yields.csv），欄位：
    item        年期（1年期 / 2年期 / 5年期 / 10年期 / 20年期 / 30年期）
    price_date  日期 YYYY-MM-DD
    yield_pct   殖利率（%）

以 (item, price_date) 為唯一鍵。
"""
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "bond_yields.csv"

COLUMNS = ["item", "price_date", "yield_pct"]

# (MoneyDJ API 代碼, 顯示名稱)，由短天期到長天期。
# 這裡是年期定義的唯一來源，bond_scraper 也從這裡取用。
# 順序很重要：圖表的線條顏色依此指派，直接照字串排序會變成 10年期排在 1年期前面。
MATURITIES = [
    ("GBUS012", "1年期"),
    ("GBUS024", "2年期"),
    ("GBUS060", "5年期"),
    ("GBUS120", "10年期"),
    ("GBUS240", "20年期"),
    ("GBUS360", "30年期"),
]
MATURITY_ORDER = [name for _, name in MATURITIES]


def load_bonds() -> pd.DataFrame:
    """讀取 CSV，回傳依日期排序的 DataFrame。檔案不存在時回傳空 DataFrame。"""
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(CSV_PATH)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce")
    df = df.dropna(subset=["price_date"])
    # 以年期長短排序，而不是字串排序
    df["item"] = pd.Categorical(df["item"], categories=MATURITY_ORDER, ordered=True)
    df = df.dropna(subset=["item"])
    df = df.sort_values(["price_date", "item"]).reset_index(drop=True)
    df["item"] = df["item"].astype(str)
    return df


def latest_date(df: pd.DataFrame) -> str:
    """回傳資料中最新的日期字串（YYYY-MM-DD）；無資料時回傳空字串。"""
    if df.empty:
        return ""
    return pd.to_datetime(df["price_date"]).max().strftime("%Y-%m-%d")


def merge_yields(rows: list[dict]) -> int:
    """
    將爬蟲回傳的殖利率併入 CSV，回傳實際新增的筆數。

    rows: [{"項目": str, "殖利率": float, "日期": "YYYY-MM-DD"}, ...]
          （沿用 bond_scraper.MoneyDJBondScraper.fetch_yields 的輸出格式）

    已存在的 (item, price_date) 一律略過，不覆寫既有數值。
    """
    if not rows:
        return 0

    incoming = pd.DataFrame(
        [
            {
                "item": str(r["項目"]).strip(),
                "price_date": str(r["日期"]).strip(),
                "yield_pct": r["殖利率"],
            }
            for r in rows
            if r.get("項目") and r.get("日期") and r.get("殖利率") is not None
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
