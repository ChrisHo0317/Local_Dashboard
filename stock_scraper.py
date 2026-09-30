"""
個股資料爬蟲（證交所＋櫃買中心開放資料）

每個資料集都是「整批取代」性質：拿到的就是最新一期的全部公司。
上市、上櫃分開處理 —— 其中一邊抓不到時只保留那一邊的舊資料，另一邊照常更新。
同一市場的財報分成六種產業格式，任何一種失敗就整個市場這次不更新，
免得金融股從清單上突然消失。
"""
import logging

from curl_cffi import requests as cffi_requests

from stock_sources import BODY_LIMIT, DATASETS, FIELDS

HEADERS = {"Accept": "application/json", "Accept-Language": "zh-TW,zh;q=0.9"}


def pick(item: dict, candidates: list[str]) -> str:
    """依序取第一個有值的來源欄位。"""
    for src in candidates:
        value = item.get(src)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def parse_rows(key: str, market: str, data: list) -> list[dict]:
    rows = []
    for item in data:
        row = {dst: pick(item, srcs) for dst, srcs in FIELDS[key]}
        if not row.get("code"):
            continue
        if "subject" in row:
            # 主旨常夾著 \r\n，是排版用的，不是真的要分行
            row["subject"] = " ".join(row["subject"].split())
        if "body" in row:
            # 原始說明夾著 \r\n 與大量空白，整理成單純的分行
            lines = [" ".join(ln.split()) for ln in row["body"].splitlines()]
            text = "\n".join(ln for ln in lines if ln)
            if len(text) > BODY_LIMIT:
                text = text[:BODY_LIMIT].rstrip() + "…"
            row["body"] = text
        row["market"] = market
        rows.append(row)
    return rows


class StockScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("StockScraper")
        self.session = cffi_requests.Session(impersonate="chrome124")

    def fetch_all(self) -> dict:
        """回傳 {資料集: {市場: [列]}}。抓失敗的 (資料集, 市場) 不會出現。"""
        got: dict = {}
        failed: set = set()
        for key, market, url, label in DATASETS:
            if (key, market) in failed:
                continue
            try:
                resp = self.session.get(url, headers=HEADERS, timeout=90)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, list):
                    raise ValueError("回應不是清單")
            except Exception as e:
                self.logger.error(f"{label}：抓取失敗 {e}")
                failed.add((key, market))
                got.get(key, {}).pop(market, None)
                continue
            rows = parse_rows(key, market, data)
            got.setdefault(key, {}).setdefault(market, []).extend(rows)
            self.logger.info(f"{label}：{len(rows)} 筆")
        return {k: v for k, v in got.items() if v}
