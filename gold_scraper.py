"""
黃金價格爬蟲（Yahoo Finance）

    GET https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range=5y&interval=1d

回傳 JSON，取 chart.result[0] 的 timestamp 與 indicators.quote[0].close。

時間戳是 UTC 秒數，對應交易所當地的交易日開盤時刻（GC=F 是 America/New_York
的 00:00，換算後 UTC 日期剛好相同）。仍以 meta.gmtoffset 換算成交易所當地日期，
避免日後換標的或夏令時間造成日期偏移。

備註：GC=F 是連續近月合約，Yahoo 會自動接續換月（目前為 Gold Dec 26），
適合看長期趨勢；若要嚴格的單一合約價格則不適用。

原本指定的來源 truney.com 有 Cloudflare 人機驗證，連真實 Chrome 都停在
「正在執行安全驗證」而逾時，無法用於自動更新。
"""
import logging
from datetime import datetime, timedelta, timezone

from curl_cffi import requests as cffi_requests

from gold_data import SYMBOLS   # 商品定義的唯一來源

API_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


class YahooGoldScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("YahooGoldScraper")

    def fetch_prices(self, period: str = "5y") -> list[dict]:
        """
        取得日線收盤價。period 為 Yahoo 的 range 參數（如 "5y"、"1mo"）。

        回傳: [{"項目": "COMEX 黃金期貨", "收盤": 4493.8, "日期": "2026-08-31"}, ...]
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
                continue          # 尚未收盤或該日無交易
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
