"""
TrendForce DRAM 現貨報價爬蟲

移植自 AI Cowork 的 News 子系統（apps/News/scrapers/trendforce_scraper.py），
移除對 News 專案的依賴，邏輯不變。

只抓取 DRAM Spot Price 區塊第一個表格的：項目、盤平均、Last Update 日期。
"""
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

TRENDFORCE_HOME = "https://www.trendforce.com.tw/"
TRENDFORCE_DRAM_URL = "https://www.trendforce.com.tw/price/dram/dram_spot"


class TrendForceScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("TrendForceScraper")

    def fetch_dram_spot(self) -> list[dict]:
        """
        回傳: [{"項目": str, "盤平均": float, "日期": "YYYY-MM-DD"}]
        若失敗則回傳空串列（呼叫端據此判斷是否跳過更新）。
        """
        try:
            session = cffi_requests.Session(impersonate="chrome124")
            headers = {
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": TRENDFORCE_HOME,
            }
            session.get(TRENDFORCE_HOME, headers=headers, timeout=15)
            resp = session.get(TRENDFORCE_DRAM_URL, headers=headers, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            self.logger.error(f"TrendForce 頁面讀取失敗: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        date_str = self._extract_date(soup)
        if not date_str:
            self.logger.warning("TrendForce: 無法取得 Last Update 日期")
            return []

        prices = self._extract_spot_prices(soup, date_str)
        self.logger.info(f"TrendForce DRAM 現貨: {date_str}，共 {len(prices)} 項")
        return prices

    def _extract_date(self, soup: BeautifulSoup) -> str | None:
        """
        從頁面找 Last Update 日期，回傳 YYYY-MM-DD。
        嘗試順序：1. 含 "Last Update" 文字的元素  2. 頁面全文的日期 regex
        """
        for tag in soup.find_all(string=re.compile(r"Last Update", re.I)):
            text = tag.strip() if isinstance(tag, str) else tag.get_text(strip=True)
            m = re.search(r"(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", text)
            if m:
                return self._to_iso(m.group(1), m.group(2), m.group(3))

        full_text = soup.get_text(" ")
        m = re.search(
            r"Last Update[^0-9]*(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})",
            full_text, re.I,
        )
        if m:
            return self._to_iso(m.group(1), m.group(2), m.group(3))

        return None

    @staticmethod
    def _to_iso(y: str, mo: str, d: str) -> str | None:
        try:
            return datetime(int(y), int(mo), int(d)).strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _extract_spot_prices(self, soup: BeautifulSoup, date_str: str) -> list[dict]:
        """找第一個含「盤平均」欄的 <table>（即 DRAM Spot Price 表格），提取 項目 + 盤平均。"""
        results = []

        for table in soup.find_all("table"):
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            if "盤平均" not in headers:
                continue

            avg_idx = headers.index("盤平均")
            item_idx = next((i for i, h in enumerate(headers) if "項目" in h), 0)

            for row in table.find_all("tr")[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) <= max(item_idx, avg_idx):
                    continue

                item = cells[item_idx].get_text(strip=True)
                avg_text = cells[avg_idx].get_text(strip=True).replace(",", "").replace(" ", "")

                if not item:
                    continue

                try:
                    avg_val = float(avg_text)
                except ValueError:
                    avg_val = None

                if avg_val is not None:
                    results.append({"項目": item, "盤平均": avg_val, "日期": date_str})

            break  # 只抓第一個匹配表格（DRAM Spot）

        return results
