"""
更新各資料集 → 併入 CSV → 重建 docs/index.html

    python update_data.py

供 GitHub Actions 每日排程與手動更新共用。

任一來源抓不到資料時「只警告、不失敗」（exit code 0），避免對方擋爬蟲時
把 workflow 弄成紅燈，也絕不會覆寫既有的 CSV。
"""
import logging
import sys
from datetime import date, timedelta

import build_static
from bond_data import CSV_PATH as BOND_CSV, merge_yields
from bond_scraper import MoneyDJBondScraper
from dram_data import CSV_PATH as DRAM_CSV, merge_prices
from gold_data import CSV_PATH as GOLD_CSV, merge_prices as merge_gold
from gold_scraper import YahooGoldScraper
from scraper import TrendForceScraper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("update_data")

# 殖利率 API 可帶區間，平常只要回頭抓一小段就能補上假日與漏抓；
# CSV 不存在時（第一次執行）才整段回補。
BOND_HISTORY_START = date(2023, 1, 1)   # 1年期的資料從 2023-01-03 才有
BOND_LOOKBACK_DAYS = 30

# 金價同理：平常只取近一個月，首次執行才整段回補
GOLD_HISTORY_RANGE = "5y"
GOLD_LOOKBACK_RANGE = "1mo"


def update_dram() -> int:
    """DRAM 現貨報價：TrendForce 每次只提供當日快照。"""
    rows = TrendForceScraper(logger=log).fetch_dram_spot()
    if not rows:
        log.warning("DRAM：未取得任何報價（TrendForce 可能擋下請求），本次不更新")
        return 0
    added = merge_prices(rows)
    log.info(f"DRAM：抓取 {len(rows)} 筆，新增 {added} 筆至 {DRAM_CSV.name}")
    return added


def update_bonds() -> int:
    """美國公債殖利率：MoneyDJ 提供歷史區間，回頭抓一段可自我修補缺漏。"""
    if BOND_CSV.exists():
        start = date.today() - timedelta(days=BOND_LOOKBACK_DAYS)
    else:
        start = BOND_HISTORY_START
        log.info(f"美債：首次執行，自 {start} 起整段回補")

    rows = MoneyDJBondScraper(logger=log).fetch_yields(start, date.today())
    if not rows:
        log.warning("美債：未取得任何資料（MoneyDJ 可能擋下請求），本次不更新")
        return 0
    added = merge_yields(rows)
    log.info(f"美債：抓取 {len(rows)} 筆，新增 {added} 筆至 {BOND_CSV.name}")
    return added


def update_gold() -> int:
    """國際金價：Yahoo Finance 提供歷史區間，回頭抓一段可自我修補缺漏。"""
    if GOLD_CSV.exists():
        period = GOLD_LOOKBACK_RANGE
    else:
        period = GOLD_HISTORY_RANGE
        log.info(f"黃金：首次執行，整段回補 {period}")

    rows = YahooGoldScraper(logger=log).fetch_prices(period)
    if not rows:
        log.warning("黃金：未取得任何資料（Yahoo Finance 可能拒絕請求），本次不更新")
        return 0
    added = merge_gold(rows)
    log.info(f"黃金：抓取 {len(rows)} 筆，新增 {added} 筆至 {GOLD_CSV.name}")
    return added


def main() -> int:
    added = update_dram() + update_bonds() + update_gold()

    if added == 0:
        log.info("無新資料，略過重建 HTML")
        return 0

    path = build_static.build()
    log.info(f"已重建 {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
