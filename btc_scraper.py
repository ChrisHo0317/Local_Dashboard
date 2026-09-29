"""
比特幣價格爬蟲（Yahoo Finance）

    GET https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?range=5y&interval=1d

做法與 gold_scraper.py 完全相同（同一個 Yahoo Finance chart API），
只是換一個代碼；比特幣是全天候交易，沒有休市日，回傳的每日收盤價
對應 UTC 午夜（gmtoffset 固定為 0）。
"""
import logging
from datetime import datetime, timedelta, timezone

from curl_cffi import requests as cffi_requests

from btc_data import SYMBOLS   # 商品定義的唯一來源

API_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class YahooBTCScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("YahooBTCScraper")

    def fetch_prices(self, period: str = "5y") -> list[dict]:
        """
        取得日線收盤價。period 為 Yahoo 的 range 參數（如 "5y"、"1mo"）。

        回傳: [{"項目": "比特幣", "收盤": 61234.5, "日期": "2026-08-31"}, ...]
        失敗則回傳空串列，由呼叫端決定是否跳過更新。
        """
        rows = []
        for symbol, name in SYMBOLS:
            rows.extend(self._fetch_one(symbol, name, period))
        return rows

    def _fetch_one(self, symbol: str, name: str, period: str) -> list[dict]:
        try:
            session = cffi_requests.Session(impersonate="chrome124")
            resp = session.get(
                API_URL.format(symbol=symbol),
                params={"range": period, "interval": "1d"},
                headers={"Accept": "application/json"},
                timeout=40,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            self.logger.error(f"Yahoo Finance {symbol} 讀取失敗: {e}")
            return []

        try:
            result = payload["chart"]["result"][0]
            offset = int(result["meta"].get("gmtoffset") or 0)
            stamps = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]
        except (KeyError, IndexError, TypeError) as e:
            self.logger.error(f"Yahoo Finance {symbol} 回傳格式非預期: {e}")
            return []

        tz = timezone(timedelta(seconds=offset))
        rows = []
        for stamp, close in zip(stamps, closes):
            if close is None:
                continue          # 該日無資料
            day = datetime.fromtimestamp(stamp, tz).strftime("%Y-%m-%d")
            rows.append({"項目": name, "收盤": round(float(close), 2), "日期": day})

        if rows:
            days = [r["日期"] for r in rows]
            self.logger.info(
                f"Yahoo Finance {symbol}：{len(rows)} 筆，{min(days)} ～ {max(days)}"
            )
        else:
            self.logger.warning(f"Yahoo Finance {symbol} 沒有回傳任何收盤價")
        return rows
