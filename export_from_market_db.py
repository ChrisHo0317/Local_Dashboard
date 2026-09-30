"""
一次性工具：從本機 market_db（Cowork 的 DuckDB）匯出歷史資料

要用 Cowork 的虛擬環境執行（那裡才有 duckdb）：

    E:\\AI\\Cowork\\.venv\\Scripts\\python.exe export_from_market_db.py

產出（都在 data/ 底下，之後由排程每天向官方累積，不再需要這個工具）：

    market/history_base.parquet    近一年日資料（價量、三大法人、融資融券），
                                   依代號＋日期排序存成單一檔，壓縮率比逐日檔好很多
    market/stocks.csv              股票清單（代號、名稱、市場、產業）
    fundamental/revenue.parquet    月營收（千元），2021 年起
    fundamental/income.parquet     季損益（單季，千元；EPS 元），2020 年起
    fundamental/pe_monthly.parquet 月底收盤、近四季 EPS、本益比，近五年

只匯出官方本來就公開的欄位（價量、法人、融資券、營收、損益）。
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB = Path("E:/AI/Cowork/market_db/data/market.duckdb")

# 證交所產業別代碼（上市、上櫃共用同一套）
INDUSTRY = {
    "00": "ETF", "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維",
    "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷", "09": "造紙工業", "10": "鋼鐵工業",
    "11": "橡膠工業", "12": "汽車工業", "14": "建材營造業", "15": "航運業", "16": "觀光餐旅",
    "17": "金融保險業", "18": "貿易百貨業", "20": "其他業", "21": "化學工業",
    "22": "生技醫療業", "23": "油電燃氣業", "24": "半導體業", "25": "電腦及週邊設備業",
    "26": "光電業", "27": "通信網路業", "28": "電子零組件業", "29": "電子通路業",
    "30": "資訊服務業", "31": "其他電子業", "32": "文化創意業", "33": "農業科技業",
    "34": "電子商務", "35": "綠能環保", "36": "數位雲端", "37": "運動休閒", "38": "居家生活",
}

DAILY_DAYS = 380
REVENUE_FROM = date(2021, 1, 1)
INCOME_FROM = date(2020, 1, 1)
PE_MONTHS = 60


def export_daily(con, since: date) -> pd.DataFrame:
    df = con.execute("""
        SELECT p.date, p.code, s.market,
               p.open, p.high, p.low, p.close, p.volume, p.turnover,
               i.foreign_buy - i.foreign_sell AS "foreign",
               i.trust_buy - i.trust_sell     AS trust,
               i.dealer_buy - i.dealer_sell   AS dealer,
               m.margin_balance AS margin_bal,
               m.short_balance  AS short_bal
        FROM daily_price p
        JOIN stocks s USING (code)
        LEFT JOIN institutional i ON i.code = p.code AND i.date = p.date
        LEFT JOIN margin_short  m ON m.code = p.code AND m.date = p.date
        WHERE p.date >= ?
        ORDER BY p.code, p.date
    """, [since]).df()
    df["date"] = pd.to_datetime(df["date"])
    return df


def export_revenue(con) -> pd.DataFrame:
    df = con.execute("""
        SELECT code, revenue_year AS year, revenue_month AS month, revenue
        FROM month_revenue
        WHERE make_date(revenue_year, revenue_month, 1) >= ?
        ORDER BY code, year, month
    """, [REVENUE_FROM]).df()
    df["revenue"] = (df["revenue"] / 1000).round()          # 元 → 千元，與官方開放資料一致
    return df.drop_duplicates(["code", "year", "month"], keep="last")


def export_income(con) -> pd.DataFrame:
    wide = con.execute("""
        SELECT code, date,
               max(CASE WHEN type = 'Revenue' THEN value END)          AS revenue,
               max(CASE WHEN type = 'GrossProfit' THEN value END)      AS gross,
               max(CASE WHEN type = 'OperatingIncome' THEN value END)  AS operating,
               coalesce(max(CASE WHEN type = 'EquityAttributableToOwnersOfParent' THEN value END),
                        max(CASE WHEN type = 'IncomeAfterTaxes' THEN value END)) AS net,
               max(CASE WHEN type = 'EPS' THEN value END)              AS eps
        FROM income_statement
        WHERE date >= ?
        GROUP BY code, date
        ORDER BY code, date
    """, [INCOME_FROM]).df()
    d = pd.to_datetime(wide["date"])
    wide["year"] = d.dt.year
    wide["quarter"] = (d.dt.month - 1) // 3 + 1
    for col in ("revenue", "gross", "operating", "net"):
        wide[col] = (wide[col] / 1000).round()
    return wide[["code", "year", "quarter", "revenue", "gross", "operating", "net", "eps"]]


def pe_history(con, income: pd.DataFrame, end: date) -> pd.DataFrame:
    """
    月底收盤 ÷ 近四季 EPS。只用「那個月底之前兩個月就已經結束的季度」，
    避免用到當時還沒公布的財報。EPS 合計不大於 0 的月份不算本益比。
    """
    start = (pd.Timestamp(end) - pd.DateOffset(months=PE_MONTHS + 1)).date()
    closes = con.execute("""
        SELECT code, date, close FROM daily_price WHERE date >= ? ORDER BY code, date
    """, [start]).df()
    closes["date"] = pd.to_datetime(closes["date"])
    closes["ym"] = closes["date"].dt.to_period("M")
    month_end = closes.groupby(["code", "ym"]).tail(1)[["code", "ym", "close"]]

    q = income.dropna(subset=["eps"]).copy()
    q["qend"] = pd.PeriodIndex.from_fields(year=q["year"], quarter=q["quarter"],
                                           freq="Q").to_timestamp(how="end")
    q = q.sort_values(["code", "qend"])
    q["ttm"] = q.groupby("code")["eps"].transform(lambda s: s.rolling(4, min_periods=4).sum())
    q = q.dropna(subset=["ttm"])[["code", "qend", "ttm"]]

    month_end = month_end.assign(
        cutoff=month_end["ym"].dt.to_timestamp(how="end") - pd.DateOffset(months=2))
    month_end = month_end.sort_values("cutoff")
    q = q.sort_values("qend")
    merged = pd.merge_asof(month_end, q, left_on="cutoff", right_on="qend", by="code",
                           direction="backward").dropna(subset=["ttm"])
    merged["pe"] = (merged["close"] / merged["ttm"]).where(merged["ttm"] > 0).round(2)
    out = merged.assign(ym=merged["ym"].astype(str), eps_ttm=merged["ttm"].round(2))
    return out[["code", "ym", "close", "eps_ttm", "pe"]].sort_values(["code", "ym"])


def main(db_path: Path) -> int:
    try:
        import duckdb
    except ImportError:
        print("[錯誤] 這個環境沒有 duckdb，請用 Cowork 的虛擬環境執行。")
        return 1
    if not db_path.exists():
        print(f"[錯誤] 找不到資料庫：{db_path}")
        return 1

    con = duckdb.connect(str(db_path), read_only=True)
    last = con.execute("SELECT max(date) FROM daily_price").fetchone()[0]
    since = last - timedelta(days=DAILY_DAYS)

    (DATA_DIR / "market").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "fundamental").mkdir(parents=True, exist_ok=True)

    stocks = con.execute("SELECT code, name, market, industry FROM stocks ORDER BY code").df()
    stocks["industry"] = stocks["industry"].map(INDUSTRY).fillna("其他")
    stocks.to_csv(DATA_DIR / "market" / "stocks.csv", index=False, encoding="utf-8",
                  lineterminator="\n")
    print(f"股票清單：{len(stocks)} 檔")

    daily = export_daily(con, since)
    for col in ("open", "high", "low", "close"):
        daily[col] = daily[col].astype("float32")
    for col in ("volume", "turnover", "foreign", "trust", "dealer", "margin_bal", "short_bal"):
        daily[col] = daily[col].round().astype("Int64")
    daily.to_parquet(DATA_DIR / "market" / "history_base.parquet", index=False,
                     compression="zstd", compression_level=19)
    print(f"日資料：{len(daily)} 筆，{daily['date'].min().date()} ～ {daily['date'].max().date()}")

    revenue = export_revenue(con)
    revenue.to_parquet(DATA_DIR / "fundamental" / "revenue.parquet", index=False,
                       compression="zstd")
    print(f"月營收：{len(revenue)} 筆")

    income = export_income(con)
    income.to_parquet(DATA_DIR / "fundamental" / "income.parquet", index=False,
                      compression="zstd")
    print(f"季損益：{len(income)} 筆")

    pe = pe_history(con, income, last)
    pe.to_parquet(DATA_DIR / "fundamental" / "pe_monthly.parquet", index=False,
                  compression="zstd")
    print(f"月本益比：{len(pe)} 筆")
    con.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="從 market_db 匯出歷史資料")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sys.exit(main(parser.parse_args().db))
