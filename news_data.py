"""
新聞資料層

資料以 CSV 保存（data/news_articles.csv），欄位：
    source     來源代碼（ustv / yahoo / ltn / digitimes / technews）
    order      該來源清單上的順序（0 起算）
    title      標題
    url        原文網址
    published  發布時間 ISO 8601（只有 RSS 來源有；HTML 來源留空）
    body       內文（已截斷；抽不到時為空字串）

新聞每天都會換一批，舊的留著沒有意義，一律以最新抓到的為準。
"""
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "news_articles.csv"

COLUMNS = ["source", "order", "title", "url", "published", "body"]


def load_news() -> pd.DataFrame:
    """讀取 CSV，依來源與順序排序。檔案不存在時回傳空 DataFrame。"""
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    df["_order"] = pd.to_numeric(df["order"], errors="coerce").fillna(999)
    return df.sort_values(["source", "_order"]).reset_index(drop=True)


def latest_date(df: pd.DataFrame) -> str:
    """回傳最新一則的發布日期；沒有時間資訊時回傳空字串。"""
    if df.empty:
        return ""
    stamps = pd.to_datetime(df["published"], errors="coerce", utc=True).dropna()
    if stamps.empty:
        return ""
    return stamps.max().strftime("%Y-%m-%d")


def merge_news(rows: list[dict]) -> int:
    """整批取代，回傳「有異動」時的筆數。"""
    if not rows:
        return 0

    incoming = pd.DataFrame(rows, columns=COLUMNS).astype(str).fillna("")
    incoming = incoming[incoming["title"] != ""]
    if incoming.empty:
        return 0

    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        existing = existing.reindex(columns=COLUMNS).reset_index(drop=True)
        if existing.equals(incoming.reset_index(drop=True)):
            return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    incoming.to_csv(CSV_PATH, index=False, encoding="utf-8")
    return len(incoming)


def load_all() -> dict:
    """新聞分頁需要的資料。"""
    return {"news": load_news()}
