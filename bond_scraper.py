"""
美國公債殖利率爬蟲（MoneyDJ）

資料來源頁面：https://www.moneydj.com/bond/defaultBD.xdjhtm

該頁的殖利率是 JS 動態載入的，靜態 HTML 裡沒有表格。實際資料來自頁面自己呼叫的
GetProdHist API，可帶日期區間取得每日歷史值，因此不必逐日累積、一次就能回補。

    GET /XQMBondPo/api/Data/GetProdHist?a=<代碼,...>&b=<起日>&c=<迄日>&d=D

回傳 [{"ID": "GBUS120", "Data": [{"V1": "2026/08/28", "V2": "4.73"}, ...]}, ...]
（Data 由新到舊排列）

代碼為 GBUS + 三位數月份：012=1年、024=2年、060=5年、120=10年、240=20年、360=30年。
其他年期（3/6個月、3年、7年）試過都會回傳 HTML 錯誤頁，該站沒有提供。
"""
import json
import logging
from datetime import date

from curl_cffi import requests as cffi_requests

PAGE_URL = "https://www.moneydj.com/bond/defaultBD.xdjhtm"
API_URL = "https://www.moneydj.com/XQMBondPo/api/Data/GetProdHist"

from bond_data import MATURITIES   # 年期定義的唯一來源

_NAME_BY_CODE = dict(MATURITIES)


class MoneyDJBondScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("MoneyDJBondScraper")

    def fetch_yields(self, start: date, end: date) -> list[dict]:
        """
        取得指定期間的各年期殖利率。

        回傳: [{"項目": "10年期", "殖利率": 4.73, "日期": "2026-08-28"}, ...]
        失敗則回傳空串列，由呼叫端決定是否跳過更新。
        """
        params = {
            "a": ",".join(code for code, _ in MATURITIES),
            "b": start.isoformat(),
            "c": end.isoformat(),
            "d": "D",
        }
        try:
            session = cffi_requests.Session(impersonate="chrome124")
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
                "Referer": PAGE_URL,
            }
            resp = session.get(API_URL, params=params, headers=headers, timeout=60)
            resp.raise_for_status()
        except Exception as e:
            self.logger.error(f"MoneyDJ 殖利率 API 讀取失敗: {e}")
            return []

        # 這個端點偶爾夾帶無法以 UTF-8 解碼的位元組，errors="replace" 才不會整包炸掉；
        # 我們只取數字與日期，替換字元不影響結果。
        try:
            payload = json.loads(resp.content.decode("utf-8", errors="replace"))
        except ValueError:
            # 代碼有誤或被擋時，會回傳一整頁 HTML 而非 JSON
            self.logger.error("MoneyDJ 殖利率 API 未回傳 JSON（可能被擋或代碼有誤）")
            return []

        if not isinstance(payload, list):
            self.logger.error(f"MoneyDJ 殖利率 API 回傳格式非預期: {type(payload).__name__}")
            return []

        rows = []
        for entry in payload:
            name = _NAME_BY_CODE.get(entry.get("ID"))
            if not name:
                continue
            for point in entry.get("Data") or []:
                iso = self._to_iso(point.get("V1"))
                value = self._to_float(point.get("V2"))
                if iso and value is not None:
                    rows.append({"項目": name, "殖利率": value, "日期": iso})

        if rows:
            days = {r["日期"] for r in rows}
            self.logger.info(
                f"MoneyDJ 殖利率：{len(rows)} 筆，{len(days)} 個交易日，"
                f"{min(days)} ～ {max(days)}"
            )
        else:
            self.logger.warning("MoneyDJ 殖利率 API 沒有回傳任何資料點")
        return rows

    @staticmethod
    def _to_iso(value) -> str | None:
        """"2026/08/28" → "2026-08-28"。"""
        if not isinstance(value, str):
            return None
        parts = value.strip().replace("-", "/").split("/")
        if len(parts) != 3:
            return None
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
        except ValueError:
            return None

    @staticmethod
    def _to_float(value) -> float | None:
        try:
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return None
