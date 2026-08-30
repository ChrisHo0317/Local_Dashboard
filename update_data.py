"""
更新 DRAM 報價：爬 TrendForce → 併入 data/dram_prices.csv → 重建 docs/index.html

    python update_data.py

供 GitHub Actions 每日排程與手動更新共用。

抓不到資料時「只警告、不失敗」（exit code 0），避免 TrendForce 擋爬蟲時
把 workflow 弄成紅燈，也絕不會覆寫既有的 CSV。
"""
import logging
import sys

import build_static
from dram_data import CSV_PATH, latest_date, load_dram, merge_prices
from scraper import TrendForceScraper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("update_data")


def main() -> int:
    rows = TrendForceScraper(logger=log).fetch_dram_spot()

    if not rows:
        log.warning("未取得任何報價（TrendForce 可能擋下請求），本次不更新 CSV")
        return 0

    added = merge_prices(rows)
    log.info(f"抓取 {len(rows)} 筆，新增 {added} 筆至 {CSV_PATH.name}")

    if added == 0:
        log.info("無新資料，略過重建 HTML")
        return 0

    path = build_static.build()
    log.info(f"已重建 {path.name}，最後報價日：{latest_date(load_dram())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
