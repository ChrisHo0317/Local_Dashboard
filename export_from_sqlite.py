"""
一次性工具：從 AI Cowork 的本機 SQLite 匯出 DRAM 報價成 CSV。

初始化 repo 時跑一次即可；日後若本機 SQLite 有更完整的資料，
也可以再跑一次重新同步（以 SQLite 為準覆寫 CSV）。

    python export_from_sqlite.py
    python export_from_sqlite.py --db D:/other/path/cowork.db
"""
import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from dram_data import CSV_PATH, DATA_DIR

DEFAULT_DB = Path("E:/AI/Cowork/market_db/data/cowork.db")


def export(db_path: Path) -> int:
    if not db_path.exists():
        print(f"[錯誤] 找不到資料庫：{db_path}")
        return 1

    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query(
            "SELECT item, price_date, avg_price FROM dram_prices "
            "ORDER BY price_date ASC, item ASC",
            conn,
        )
    finally:
        conn.close()

    if df.empty:
        print("[警告] dram_prices 資料表為空，未寫出 CSV")
        return 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False, encoding="utf-8")

    print(f"[完成] 已寫出 {CSV_PATH}")
    print(f"       筆數：{len(df)}　型號：{df['item'].nunique()} 種")
    print(f"       日期範圍：{df['price_date'].min()} ～ {df['price_date'].max()}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="從 cowork.db 匯出 DRAM 報價成 CSV")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite 資料庫路徑")
    args = parser.parse_args()
    sys.exit(export(args.db))
