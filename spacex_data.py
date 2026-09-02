"""
SpaceX 發射資料層

資料以 CSV 保存（data/spacex_launches.csv），欄位：
    launch_time   發射時間，ISO 8601 含時區（UTC）；待定時為空字串
    title         任務名稱（英文原名，中文於產生頁面時翻譯）
    vehicle       火箭（Falcon 9 / Falcon Heavy / Starship / Falcon 1）
    launch_site   發射場
    return_site   回收方式
    mission_type  任務類型（starlink / resupply / hsf ...）
    status        upcoming / in-progress / final
    link          官網任務頁的網址片段

以 (launch_time, title, launch_site) 為唯一鍵；時間待定的以 correlation_id 補足。

來源一次提供整份清單（含歷史），所以不必累積；每次以最新抓到的為準
（發射時間常常改期，舊值沒有保留意義）。
"""
from datetime import timedelta, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "spacex_launches.csv"

COLUMNS = ["launch_time", "title", "vehicle", "launch_site", "return_site",
           "mission_type", "status", "link"]


def load_launches() -> pd.DataFrame:
    """讀取 CSV，回傳依時間排序的 DataFrame。檔案不存在時回傳空 DataFrame。"""
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)

    df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)

    df["_ts"] = pd.to_datetime(df["launch_time"], errors="coerce", utc=True)
    df = df.dropna(subset=["_ts"]).sort_values("_ts").reset_index(drop=True)
    return df


def latest_date(df: pd.DataFrame) -> str:
    """回傳最後一筆發射的日期（台北時間 YYYY-MM-DD）；無資料時回傳空字串。"""
    if df.empty or "_ts" not in df:
        return ""
    return df["_ts"].max().tz_convert(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def merge_launches(rows: list[dict]) -> int:
    """
    寫入發射清單，回傳「有異動」時的筆數。

    發射時間常常改期，一律以最新抓到的為準，不做累積。
    """
    if not rows:
        return 0

    incoming = pd.DataFrame(rows, columns=COLUMNS).astype(str).fillna("")
    incoming = incoming[incoming["title"] != ""]
    if incoming.empty:
        return 0
    incoming = incoming.sort_values("launch_time").reset_index(drop=True)

    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        existing = existing.reindex(columns=COLUMNS)
        existing = existing.sort_values("launch_time").reset_index(drop=True)
        if existing.equals(incoming):
            return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    incoming.to_csv(CSV_PATH, index=False, encoding="utf-8")
    return len(incoming)


def load_all() -> dict:
    """SpaceX 分頁需要的資料。"""
    return {"launches": load_launches()}
