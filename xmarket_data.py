"""
跨市場指標資料層（Yahoo Finance 日收盤）

資料以 CSV 保存（data/xmarket_prices.csv），欄位：
    item        項目名稱
    price_date  日期 YYYY-MM-DD（交易所當地日期）
    price       收盤

加權指數給總覽的大盤圖用；費半、那斯達克、美元兌台幣進走勢圖分頁；
其餘國際指數、期貨、龍頭股、原物料、匯率給總覽「國際」子分頁（global_market.py）。
櫃買指數 Yahoo 沒有，改由 market_scraper 從櫃買中心取得。
"""
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "xmarket_prices.csv"
COLUMNS = ["item", "price_date", "price"]

# (Yahoo 代碼, 顯示名稱)
SYMBOLS = [
    ("^TWII", "加權指數"),
    ("^SOX", "費城半導體"),
    ("^IXIC", "那斯達克"),
    ("TWD=X", "美元兌台幣"),
    ("TSM", "台積電ADR"),          # 1 單位 ADR＝5 股台積電，算溢價用
    ("^VIX", "VIX"),
    ("DX-Y.NYB", "美元指數"),
    # 國際市場（總覽「國際」子分頁）
    ("^GSPC", "標普500"),
    ("^DJI", "道瓊工業"),
    ("^RUT", "羅素2000"),
    ("ES=F", "標普期貨"),
    ("NQ=F", "那斯達克期貨"),
    ("^N225", "日經225"),
    ("^KS11", "韓國綜合"),
    ("^HSI", "恒生指數"),
    ("000001.SS", "上證指數"),
    ("NVDA", "輝達"),
    ("AMD", "超微"),
    ("AVGO", "博通"),
    ("AAPL", "蘋果"),
    ("MU", "美光"),
    ("ASML", "艾司摩爾"),
    ("005930.KS", "三星電子"),
    ("000660.KS", "SK海力士"),
    ("CL=F", "WTI原油"),
    ("BZ=F", "布蘭特原油"),
    ("HG=F", "銅"),
    ("NG=F", "天然氣"),
    ("JPY=X", "美元兌日圓"),
    ("CNY=X", "美元兌人民幣"),
    ("KRW=X", "美元兌韓元"),
    ("EURUSD=X", "歐元兌美元"),
]
# 台指期夜盤（期交所，不在 Yahoo）
NIGHT = "台指期夜盤"
SYMBOL_ORDER = [name for _, name in SYMBOLS]


def load_xmarket(items: list[str] | None = None) -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(CSV_PATH)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce")
    df = df.dropna(subset=["price_date"])
    if items:
        df = df[df["item"].isin(items)]
    order = {name: i for i, name in enumerate(SYMBOL_ORDER)}
    df = df.assign(_o=df["item"].map(order)).sort_values(["price_date", "_o"])
    return df.drop(columns="_o").reset_index(drop=True)


def latest_date(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    return pd.to_datetime(df["price_date"]).max().strftime("%Y-%m-%d")


def merge_prices(rows: list[dict]) -> int:
    """rows: [{"項目", "收盤", "日期"}]；已存在的 (item, price_date) 不覆寫。"""
    if not rows:
        return 0
    incoming = pd.DataFrame(
        [{"item": r["項目"], "price_date": r["日期"], "price": r["收盤"]} for r in rows
         if r.get("收盤") is not None],
        columns=COLUMNS,
    )
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
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(CSV_PATH, index=False, encoding="utf-8", lineterminator="\n")
    return added
