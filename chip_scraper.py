"""
籌碼爬蟲

    集保戶股權分散表   https://opendata.tdcc.com.tw/getOD.ashx?id=1-5  （CSV，最新一週）
        欄位：資料日期, 證券代號, 持股分級, 人數, 股數, 占集保庫存數比例%
        分級 12–15 是 400 張以上，15 是 1,000 張以上；17 是合計
    期貨三大法人       https://openapi.taifex.com.tw/v1/
                       MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate
        取「臺股期貨」的未平倉淨口數
"""
import io
import logging
from datetime import datetime

import pandas as pd
from curl_cffi import requests as cffi_requests

from market_data import CODE_PATTERN

TDCC_URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
TAIFEX_URL = ("https://openapi.taifex.com.tw/v1/"
              "MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate")

ITEMS = {"外資": "foreign", "外資及陸資": "foreign", "投信": "trust", "自營商": "dealer"}


def parse_tdcc(text: str):
    """回傳 (資料日期, DataFrame[code, big1000, big400, holders])。"""
    df = pd.read_csv(io.StringIO(text), dtype=str)
    df.columns = ["date", "code", "level", "people", "shares", "ratio"]
    df["code"] = df["code"].str.strip()
    df = df[df["code"].str.match(CODE_PATTERN)]
    df["level"] = pd.to_numeric(df["level"], errors="coerce")
    df["ratio"] = pd.to_numeric(df["ratio"], errors="coerce")
    df["people"] = pd.to_numeric(df["people"], errors="coerce")
    day = datetime.strptime(df["date"].iloc[0].strip(), "%Y%m%d").date()
    big1000 = df[df["level"] == 15].set_index("code")["ratio"]
    big400 = df[df["level"].between(12, 15)].groupby("code")["ratio"].sum()
    holders = df[df["level"] == 17].set_index("code")["people"]
    out = pd.DataFrame({"big1000": big1000, "big400": big400, "holders": holders})
    out = out.dropna(subset=["big1000"]).reset_index().rename(columns={"index": "code"})
    return day, out


def parse_futures(data: list) -> dict:
    """臺股期貨各法人的未平倉淨口數。"""
    row = {}
    for r in data or []:
        if str(r.get("ContractCode", "")).strip() != "臺股期貨":
            continue
        key = ITEMS.get(str(r.get("Item", "")).strip())
        if not key:
            continue
        try:
            row[key] = int(str(r.get("OpenInterest(Net)", "")).replace(",", ""))
        except ValueError:
            continue
        row["date"] = datetime.strptime(str(r["Date"]), "%Y%m%d").date().isoformat()
    return row if "date" in row else {}


class ChipScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("ChipScraper")
        self.session = cffi_requests.Session(impersonate="chrome124")

    def fetch_tdcc(self):
        try:
            resp = self.session.get(TDCC_URL, timeout=120)
            resp.raise_for_status()
            return parse_tdcc(resp.content.decode("utf-8-sig", errors="replace"))
        except Exception as e:
            self.logger.error(f"集保股權分散表讀取失敗：{e}")
            return None, None

    def fetch_futures(self) -> dict:
        try:
            resp = self.session.get(TAIFEX_URL, timeout=60)
            resp.raise_for_status()
            return parse_futures(resp.json())
        except Exception as e:
            self.logger.error(f"期交所三大法人讀取失敗：{e}")
            return {}
