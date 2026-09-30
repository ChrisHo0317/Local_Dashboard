"""
個股資料層（最新一期的清單）

每個資料集一份 CSV（data/stock_{資料集}.csv），上市、上櫃放在同一份，
用 market 欄區分：

    revenue    每月營業收入
    announce   重大訊息
    income     綜合損益表（年初至今累計，六種產業格式合併）
    exdiv      除權除息預告

每次都是「以市場為單位整批取代」—— 來源給的就是最新一期的全部公司。
某個市場抓不到時不動它那部分，頁面就還是上一期的資料，不會空一塊。
歷史（月營收、單季損益、重訊）另外累積在 fundamentals.py。
"""
from pathlib import Path

import pandas as pd

from stock_sources import COLUMNS

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CSV_PATHS = {key: DATA_DIR / f"stock_{key}.csv" for key in COLUMNS}


def load(key: str) -> pd.DataFrame:
    """讀一個資料集；檔案不存在時回傳空 DataFrame。舊檔沒有 market 欄的視為上市。"""
    path = CSV_PATHS[key]
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS[key])
    df = pd.read_csv(path, dtype=str).fillna("")
    if "market" not in df.columns:
        df["market"] = "twse"
    return df.reindex(columns=COLUMNS[key]).fillna("")


def merge(key: str, market: str, rows: list[dict]) -> int:
    """把某個市場的那一份整批換掉，回傳「有異動」時的筆數。"""
    if not rows:
        return 0
    incoming = pd.DataFrame(rows).reindex(columns=COLUMNS[key]).fillna("").astype(str)
    incoming["market"] = market
    old = load(key)
    keep = old[old["market"] != market]
    combined = pd.concat([keep, incoming], ignore_index=True)
    combined = combined.sort_values(["market", "code"], kind="stable").reset_index(drop=True)

    before = old.sort_values(["market", "code"], kind="stable").reset_index(drop=True)
    if before.equals(combined):
        return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_csv(CSV_PATHS[key], index=False, encoding="utf-8", lineterminator="\n")
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
    return {key: load(key) for key in COLUMNS}
