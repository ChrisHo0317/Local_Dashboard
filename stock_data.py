"""
個股資料層

三個資料集各一份 CSV（data/stock_{資料集}.csv）：

    revenue    上市公司每月營業收入
    announce   重大訊息
    income     綜合損益表（單季）

都是整批取代 —— 來源給的就是最新一期的全部公司，沒有「新增幾筆」可言。
抓不到某個資料集時不動它的 CSV，頁面就還是上一期的資料，不會空一塊。
"""
from pathlib import Path

import pandas as pd

from stock_sources import FIELDS

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CSV_PATHS = {key: DATA_DIR / f"stock_{key}.csv" for key in FIELDS}
COLUMNS = {key: [dst for _, dst in cols] for key, cols in FIELDS.items()}


def load(key: str) -> pd.DataFrame:
    """讀一個資料集；檔案不存在時回傳空 DataFrame。"""
    path = CSV_PATHS[key]
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS[key])
    df = pd.read_csv(path, dtype=str).fillna("")
    return df.reindex(columns=COLUMNS[key]).fillna("")


def merge(key: str, rows: list[dict]) -> int:
    """整批取代，回傳「有異動」時的筆數。"""
    if not rows:
        return 0
    incoming = pd.DataFrame(rows).reindex(columns=COLUMNS[key]).fillna("").astype(str)
    if incoming.empty:
        return 0

    path = CSV_PATHS[key]
    if path.exists():
        old = pd.read_csv(path, dtype=str).fillna("").reindex(columns=COLUMNS[key])
        if old.reset_index(drop=True).equals(incoming.reset_index(drop=True)):
            return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    incoming.to_csv(path, index=False, encoding="utf-8")
    return len(incoming)


def latest_date(df: pd.DataFrame) -> str:
    """資料裡最新的日期字串，找不到就回空字串。民國年月照原樣回。"""
    for col in ("date", "month"):
        if col in df.columns and not df.empty:
            values = sorted(v for v in df[col] if v)
            if values:
                return values[-1]
    return ""


def load_all() -> dict:
    return {key: load(key) for key in FIELDS}
