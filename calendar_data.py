"""
財經行事曆資料層

資料以 CSV 保存（data/calendar_events.csv），欄位：
    event_time  事件時間，ISO 8601 含時區（來源給的是紐約時間，如 2026-09-04T08:30:00-04:00）
    country     貨幣／地區代碼（USD、EUR、All ...）
    title       英文原名（中文由 calendar_i18n 於產生頁面時翻譯，不寫進 CSV，
                改了對照表就會全部跟著更新，不必重抓）
    impact      High / Medium / Low / Holiday
    forecast    市場預估值（可能為空）
    previous    前值（可能為空）

以 (event_time, country, title) 為唯一鍵。

來源只提供「本週」一個 feed，所以每天執行會逐週累積；已存在的事件不覆寫，
但 forecast／previous 會在原本為空、後來有值時補上（公布前後常有變化）。
"""
from datetime import timedelta, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "calendar_events.csv"

COLUMNS = ["event_time", "country", "title", "impact", "forecast", "previous"]
KEY = ["event_time", "country", "title"]


def load_events() -> pd.DataFrame:
    """讀取 CSV，回傳依時間排序的 DataFrame。檔案不存在時回傳空 DataFrame。"""
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    df["_ts"] = pd.to_datetime(df["event_time"], errors="coerce", utc=True)
    df = df.dropna(subset=["_ts"]).sort_values("_ts").reset_index(drop=True)
    return df


def latest_date(df: pd.DataFrame) -> str:
    """回傳資料中最後一個事件日期（台北時間 YYYY-MM-DD）；無資料時回傳空字串。"""
    if df.empty or "_ts" not in df:
        return ""
    # 固定 UTC+8：台灣沒有日光節約時間，不必依賴系統的 tz 資料庫
    return df["_ts"].max().tz_convert(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def merge_events(rows: list[dict]) -> int:
    """
    將爬蟲回傳的事件併入 CSV，回傳新增的筆數。

    rows: [{"event_time","country","title","impact","forecast","previous"}, ...]

    已存在的事件不重複新增；但若原本 forecast／previous 是空的而新資料有值，
    會就地補上（這種情況不計入新增筆數）。
    """
    if not rows:
        return 0

    incoming = pd.DataFrame(rows, columns=COLUMNS).astype(str).fillna("")
    incoming = incoming[incoming["event_time"] != ""]
    if incoming.empty:
        return 0
    incoming = incoming.drop_duplicates(subset=KEY, keep="last")

    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, dtype=str).fillna("")
    else:
        existing = pd.DataFrame(columns=COLUMNS)

    before = len(existing)

    if existing.empty:
        combined = incoming
        filled = 0
    else:
        merged = existing.merge(
            incoming[KEY + ["forecast", "previous"]],
            on=KEY, how="left", suffixes=("", "_new"),
        )
        filled = 0
        for col in ("forecast", "previous"):
            new_col = f"{col}_new"
            need = (merged[col] == "") & (merged[new_col].notna()) & (merged[new_col] != "")
            filled += int(need.sum())
            merged.loc[need, col] = merged.loc[need, new_col]
        existing = merged[COLUMNS]

        combined = pd.concat([existing, incoming], ignore_index=True)
        combined = combined.drop_duplicates(subset=KEY, keep="first")

    combined = combined.sort_values("event_time").reset_index(drop=True)
    added = len(combined) - before

    if added > 0 or filled > 0:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        combined[COLUMNS].to_csv(CSV_PATH, index=False, encoding="utf-8")

    return added
