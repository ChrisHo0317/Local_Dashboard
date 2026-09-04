"""
個股資料爬蟲（證交所開放資料）

三個資料集都是「整批取代」性質：每次拿到的就是最新一期的全部公司，
沒有增量可言。抓不到就回空清單，由呼叫端決定不要覆寫既有資料。
"""
import logging

from curl_cffi import requests as cffi_requests

from stock_sources import BASE_URL, BODY_LIMIT, DATASETS, FIELDS

HEADERS = {"Accept": "application/json", "Accept-Language": "zh-TW,zh;q=0.9"}


class StockScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("StockScraper")
        self.session = cffi_requests.Session(impersonate="chrome124")

    def fetch_all(self) -> dict:
        """回傳 {資料集 id: [列]}。單一資料集失敗不影響其他的。"""
        out = {}
        for key, dataset_id, label in DATASETS:
            try:
                rows = self.fetch(key, dataset_id)
            except Exception as e:
                self.logger.error(f"{label}：抓取失敗 {e}")
                continue
            if rows:
                out[key] = rows
                self.logger.info(f"{label}：{len(rows)} 筆")
            else:
                self.logger.warning(f"{label}：沒有抓到資料，保留既有的")
        return out

    def fetch(self, key: str, dataset_id: str) -> list[dict]:
        resp = self.session.get(BASE_URL + dataset_id, headers=HEADERS, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            self.logger.error(f"{dataset_id}：回應不是清單")
            return []

        mapping = FIELDS[key]
        rows = []
        for item in data:
            row = {}
            for src, dst in mapping:
                value = item.get(src, "")
                row[dst] = "" if value is None else str(value).strip()
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
            rows.append(row)
        return rows
