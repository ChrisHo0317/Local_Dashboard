"""
F1 賽程資料層

資料以 CSV 保存（data/f1_schedule.csv），欄位：
    event_time   場次時間，ISO 8601（來源為 UTC，如 2026-03-08T04:00:00Z）
    round        第幾站
    race         賽事名稱（繁體中文，如「澳洲大獎賽」）
    location     舉辦地（英文，來源就是英文）
    session      場次名稱（繁體中文，如「排位賽」）
    session_key  場次代碼（fp1 / fp2 / fp3 / qualifying / sprint / sprintQualifying / gp）

以 (event_time, race, session_key) 為唯一鍵。

來源一次就提供整季賽程，所以不必逐週累積；每次更新以最新抓到的為準
（賽程會因為改期而變動，這裡允許覆寫）。
"""
from datetime import timedelta, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CSV_PATH = DATA_DIR / "f1_schedule.csv"

COLUMNS = ["event_time", "round", "race", "location", "session", "session_key"]
KEY = ["event_time", "race", "session_key"]

# 場次重要性，供頁面上的篩選使用（數字越大越重要）
SESSION_RANK = {
    "gp": 3,
    "sprint": 2, "qualifying": 2, "sprintQualifying": 2,
    "fp1": 1, "fp2": 1, "fp3": 1,
}


def load_schedule() -> pd.DataFrame:
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
    """回傳最後一個場次的日期（台北時間 YYYY-MM-DD）；無資料時回傳空字串。"""
    if df.empty or "_ts" not in df:
        return ""
    return df["_ts"].max().tz_convert(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def merge_schedule(rows: list[dict]) -> int:
    """
    將爬蟲回傳的賽程寫入 CSV，回傳「新增或異動」的筆數。

    與其他資料集不同，這裡以最新抓到的為準：F1 賽程會改期，
    舊資料沒有保留的意義。
    """
    if not rows:
        return 0

    incoming = pd.DataFrame(rows, columns=COLUMNS).astype(str).fillna("")
    incoming = incoming[incoming["event_time"] != ""]
    if incoming.empty:
        return 0
    incoming = incoming.drop_duplicates(subset=KEY, keep="last")
    incoming = incoming.sort_values("event_time").reset_index(drop=True)

    if CSV_PATH.exists():
        existing = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        existing = existing.reindex(columns=COLUMNS).sort_values("event_time").reset_index(drop=True)
        if existing.equals(incoming):
            return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    incoming.to_csv(CSV_PATH, index=False, encoding="utf-8")
    return len(incoming)


# ── 積分榜 ───────────────────────────────────────────────────
STANDINGS_CSV = DATA_DIR / "f1_standings.csv"
STANDINGS_COLUMNS = ["kind", "position", "name", "name_en", "team",
                     "points", "wins", "podiums", "gained", "color"]


def load_standings() -> pd.DataFrame:
    """讀取積分榜 CSV。檔案不存在時回傳空 DataFrame。"""
    if not STANDINGS_CSV.exists():
        return pd.DataFrame(columns=STANDINGS_COLUMNS)
    df = pd.read_csv(STANDINGS_CSV, dtype=str).fillna("")
    if df.empty:
        return pd.DataFrame(columns=STANDINGS_COLUMNS)
    df["_pos"] = pd.to_numeric(df["position"], errors="coerce").fillna(999)
    return df.sort_values(["kind", "_pos"]).reset_index(drop=True)


def merge_standings(rows: list[dict]) -> int:
    """
    寫入積分榜，回傳「有異動」時的筆數。

    積分榜每站之後都會變，舊快照沒有保留意義，一律以最新抓到的為準。
    """
    if not rows:
        return 0
    incoming = pd.DataFrame(rows, columns=STANDINGS_COLUMNS).astype(str).fillna("")
    if incoming.empty:
        return 0

    if STANDINGS_CSV.exists():
        existing = pd.read_csv(STANDINGS_CSV, dtype=str).fillna("")
        existing = existing.reindex(columns=STANDINGS_COLUMNS)
        if existing.equals(incoming):
            return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    incoming.to_csv(STANDINGS_CSV, index=False, encoding="utf-8")
    return len(incoming)


def load_all() -> dict:
    """F1 分頁需要的全部資料（賽程 + 積分榜 + 逐站積分）。"""
    return {
        "schedule": load_schedule(),
        "standings": load_standings(),
        "series": load_points_series(),
    }


# ── 逐站累積積分（積分走勢圖用）──────────────────────────────
SERIES_CSV = DATA_DIR / "f1_points_series.csv"
SERIES_COLUMNS = ["kind", "round", "id", "name", "points", "color"]


def load_points_series() -> pd.DataFrame:
    """讀取逐站累積積分。檔案不存在時回傳空 DataFrame。"""
    if not SERIES_CSV.exists():
        return pd.DataFrame(columns=SERIES_COLUMNS)
    df = pd.read_csv(SERIES_CSV, dtype=str).fillna("")
    if df.empty:
        return pd.DataFrame(columns=SERIES_COLUMNS)
    df["round"] = pd.to_numeric(df["round"], errors="coerce")
    df["points"] = pd.to_numeric(df["points"], errors="coerce")
    df = df.dropna(subset=["round", "points"])
    return df.sort_values(["kind", "round"]).reset_index(drop=True)


def merge_points_series(rows: list[dict]) -> int:
    """寫入逐站積分，回傳「有異動」時的筆數。與積分榜同樣以最新為準。"""
    if not rows:
        return 0
    incoming = pd.DataFrame(rows, columns=SERIES_COLUMNS).astype(str).fillna("")
    if incoming.empty:
        return 0

    if SERIES_CSV.exists():
        existing = pd.read_csv(SERIES_CSV, dtype=str).fillna("")
        existing = existing.reindex(columns=SERIES_COLUMNS)
        if existing.equals(incoming):
            return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    incoming.to_csv(SERIES_CSV, index=False, encoding="utf-8")
    return len(incoming)
