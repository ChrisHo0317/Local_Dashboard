"""
跨市場指標爬蟲（Yahoo Finance chart API，與 gold_scraper 同一個端點）

    GET https://query1.finance.yahoo.com/v8/finance/chart/{代碼}?range=5y&interval=1d

時間戳依 meta.gmtoffset 換成交易所當地日期。匯率（TWD=X）是 24 小時交易，
最後一筆可能是盤中價，下一次排程會以收盤價補上（已存在的日期不覆寫，
所以盤中價那天會留著 —— 誤差在小數第二位，走勢圖上看不出來）。
"""
import logging
from datetime import datetime, timedelta, timezone

from curl_cffi import requests as cffi_requests

from xmarket_data import SYMBOLS

API_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class XMarketScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("XMarketScraper")
        self.session = cffi_requests.Session(impersonate="chrome124")

    def fetch_prices(self, period: str = "5y") -> list[dict]:
        rows = []
        for symbol, name in SYMBOLS:
            rows.extend(self._fetch_one(symbol, name, period))
        return rows

    def _fetch_one(self, symbol: str, name: str, period: str) -> list[dict]:
        try:
            resp = self.session.get(API_URL.format(symbol=symbol),
                                    params={"range": period, "interval": "1d"},
                                    headers={"Accept": "application/json"}, timeout=40)
            resp.raise_for_status()
            result = resp.json()["chart"]["result"][0]
            offset = int(result["meta"].get("gmtoffset") or 0)
            stamps = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]
        except Exception as e:
            self.logger.error(f"Yahoo Finance {symbol} 讀取失敗：{e}")
            return []
        tz = timezone(timedelta(seconds=offset))
        rows = [{"項目": name, "收盤": round(float(c), 4),
                 "日期": datetime.fromtimestamp(s, tz).strftime("%Y-%m-%d")}
                for s, c in zip(stamps, closes) if c is not None]
        self.logger.info(f"Yahoo Finance {symbol}：{len(rows)} 筆")
        return rows
