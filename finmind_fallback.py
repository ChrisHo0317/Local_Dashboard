"""
FinMind 備援（只用免費額度）

官方來源某一天某一類資料抓不到時，只替「自選股」補那一天，其他股票保留空白。
每日用量有硬上限（DAILY_LIMIT），計數存在 data/finmind_usage.json，
到上限就停，不會把免費額度用光。token 從環境變數 FINMIND_TOKEN 讀，沒有也能跑。

不輪替多組帳號 —— 用多個免費帳號繞過額度可能違反服務條款。
"""
import json
import logging
import os
from datetime import date
from pathlib import Path

import pandas as pd
from curl_cffi import requests as cffi_requests

BASE_DIR = Path(__file__).resolve().parent
USAGE_PATH = BASE_DIR / "data" / "finmind_usage.json"
API = "https://api.finmindtrade.com/api/v4/data"
DAILY_LIMIT = 200

DATASETS = {
    "quotes": "TaiwanStockPrice",
    "insti": "TaiwanStockInstitutionalInvestorsBuySell",
    "margin": "TaiwanStockMarginPurchaseShortSale",
}


def _read_usage() -> dict:
    try:
        return json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def parse_quotes(rows: list[dict]) -> dict:
    if not rows:
        return {}
    r = rows[-1]
    return {"open": r.get("open"), "high": r.get("max"), "low": r.get("min"),
            "close": r.get("close"), "volume": r.get("Trading_Volume"),
            "turnover": r.get("Trading_money")}


def parse_insti(rows: list[dict]) -> dict:
    if not rows:
        return {}
    net = {}
    for r in rows:
        net[r.get("name")] = (r.get("buy") or 0) - (r.get("sell") or 0)
    return {"foreign": net.get("Foreign_Investor"),
            "trust": net.get("Investment_Trust"),
            "dealer": (net.get("Dealer_self") or 0) + (net.get("Dealer_Hedging") or 0)}


def parse_margin(rows: list[dict]) -> dict:
    if not rows:
        return {}
    r = rows[-1]
    return {"margin_bal": r.get("MarginPurchaseTodayBalance"),
            "short_bal": r.get("ShortSaleTodayBalance")}


PARSERS = {"quotes": parse_quotes, "insti": parse_insti, "margin": parse_margin}


class FinMindFallback:
    def __init__(self, logger: logging.Logger | None = None, today: date | None = None):
        self.logger = logger or logging.getLogger("FinMind")
        self.token = os.environ.get("FINMIND_TOKEN", "").strip()
        self.today = (today or pd.Timestamp.now(tz="Asia/Taipei").date()).isoformat()
        usage = _read_usage()
        self.used = usage.get("count", 0) if usage.get("date") == self.today else 0
        self.session = cffi_requests.Session(impersonate="chrome124")

    def remaining(self) -> int:
        return max(0, DAILY_LIMIT - self.used)

    def _save_usage(self) -> None:
        USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        USAGE_PATH.write_text(json.dumps({"date": self.today, "count": self.used}),
                              encoding="utf-8")

    def _get(self, dataset: str, code: str, day: date) -> list[dict] | None:
        if self.remaining() <= 0:
            return None
        params = {"dataset": dataset, "data_id": code,
                  "start_date": day.isoformat(), "end_date": day.isoformat()}
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self.used += 1
        self._save_usage()
        try:
            resp = self.session.get(API, params=params, headers=headers, timeout=40)
            payload = resp.json()
        except Exception as e:
            self.logger.warning(f"FinMind {dataset} {code} 失敗：{e}")
            return None
        if payload.get("status") != 200:
            self.logger.warning(f"FinMind {dataset} {code}：{payload.get('msg')}")
            return None
        return payload.get("data") or []

    def fill(self, day: date, groups: list[str], codes: list[str],
             markets: dict[str, str]) -> pd.DataFrame:
        """替 codes 補 day 那天的 groups，回傳 market_data 格式的列。"""
        rows = []
        for code in codes:
            row = {"code": code, "market": markets.get(code, "")}
            for group in groups:
                data = self._get(DATASETS[group], code, day)
                if data is None:
                    if self.remaining() <= 0:
                        self.logger.warning(f"FinMind 今日用量已達上限 {DAILY_LIMIT} 次，停止補資料")
                        return pd.DataFrame(rows)
                    continue
                row.update(PARSERS[group](data))
            if len(row) > 2:
                rows.append(row)
        self.logger.info(f"FinMind 補 {day}：{len(rows)} 檔，今日已用 {self.used}/{DAILY_LIMIT} 次")
        return pd.DataFrame(rows)
