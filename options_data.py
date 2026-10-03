"""
期交所選擇權籌碼與台指期夜盤（openapi.taifex.com.tw，官方只給最近 20～30 個交易日）

    PutCallRatio                       臺指選擇權 Put/Call 比（成交量、未平倉）
    …DetailsOfCallsAndPutsBytheDate    三大法人臺指選擇權買權、賣權的淨未平倉（口）
    OpenInterestOfLargeTradersOptions  臺指選擇權大額交易人（全部月份）前五大、前十大的淨部位
    DailyMarketReportFut               臺指期近月的盤後交易（夜盤）收盤，放進跨市場資料

選擇權存 data/chips/options.csv（一天一列），每次把官方給的那幾天都併進去，
所以第一次執行就會有近一個月的資料。
"""
import logging
import re
import time
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "chips" / "options.csv"
API = "https://openapi.taifex.com.tw/v1/"
COLUMNS = ["date", "pc_vol", "pc_oi", "fi_call_oi", "fi_put_oi", "it_call_oi", "it_put_oi",
           "dl_call_oi", "dl_put_oi", "top5_call", "top5_put", "top10_call", "top10_put"]
ITEMS = {"外資": "fi", "投信": "it", "自營商": "dl"}

log = logging.getLogger("options")


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _day(v) -> str | None:
    d = re.sub(r"\D", "", str(v or ""))
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else None


def parse_pc(rows: list) -> dict:
    out = {}
    for r in rows or []:
        d = _day(r.get("Date"))
        if d:
            out.setdefault(d, {})["pc_vol"] = _num(r.get("PutCallVolumeRatio%"))
            out[d]["pc_oi"] = _num(r.get("PutCallOIRatio%"))
    return out


def parse_insti(rows: list) -> dict:
    out = {}
    for r in rows or []:
        d = _day(r.get("Date"))
        if not d or "臺指" not in str(r.get("ContractCode", "")):
            continue
        item = str(r.get("Item", "")).strip()          # 「外資及陸資」用開頭比對
        who = next((v for k, v in ITEMS.items() if item.startswith(k)), None)
        side = "call" if str(r.get("CallPut", "")).upper().startswith("C") else "put"
        if who:
            out.setdefault(d, {})[f"{who}_{side}_oi"] = _num(r.get("OpenInterest(Net)"))
    return out


def parse_large(rows: list) -> dict:
    """全部月份（666666）、全部交易人（0）：前五大、前十大的買方減賣方未平倉。"""
    out = {}
    for r in rows or []:
        d = _day(r.get("Date"))
        if not d or r.get("Contract") != "TXO" or r.get("SettlementMonth") != "666666" \
                or str(r.get("TypeOfTraders")) != "0":
            continue
        side = "call" if "買" in str(r.get("CallPut", "")) else "put"
        for n in (5, 10):
            buy, sell = _num(r.get(f"Top{n}Buy")), _num(r.get(f"Top{n}Sell"))
            if buy is not None and sell is not None:
                out.setdefault(d, {})[f"top{n}_{side}"] = buy - sell
    return out


def parse_night(rows: list) -> list[dict]:
    """臺指期（TX）盤後交易時段、最近月份的收盤 → 跨市場資料的列。"""
    best = {}
    for r in rows or []:
        if r.get("Contract") != "TX" or str(r.get("TradingSession", "")).strip() != "盤後":
            continue
        month = str(r.get("ContractMonth(Week)", "")).strip()
        d, last = _day(r.get("Date")), _num(r.get("Last"))
        if not d or last is None or not re.fullmatch(r"\d{6}", month):
            continue
        if d not in best or month < best[d][0]:
            best[d] = (month, last)
    return [{"項目": "台指期夜盤", "收盤": last, "日期": d} for d, (_, last) in sorted(best.items())]


def _get(session, path: str):
    for i in range(3):
        try:
            resp = session.get(API + path, timeout=40, headers={"Accept": "application/json"})
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        time.sleep(2)
    log.warning(f"期交所 {path} 讀取失敗")
    return None


def _session():
    from curl_cffi import requests as cffi_requests
    return cffi_requests.Session(impersonate="chrome124")


def night_rows(logger: logging.Logger | None = None) -> list[dict]:
    return parse_night(_get(_session(), "DailyMarketReportFut"))


def load() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(CSV_PATH).reindex(columns=COLUMNS)


def update(logger: logging.Logger | None = None) -> int:
    lg = logger or log
    s = _session()
    merged = {}
    for part in (parse_pc(_get(s, "PutCallRatio")),
                 parse_insti(_get(s, "MarketDataOfMajorInstitutionalTradersDetailsOfCallsAndPutsBytheDate")),
                 parse_large(_get(s, "OpenInterestOfLargeTradersOptions"))):
        for d, vals in part.items():
            merged.setdefault(d, {}).update(vals)
    if not merged:
        lg.warning("選擇權：期交所沒有回應，本次不更新")
        return 0
    new = pd.DataFrame([{"date": d, **v} for d, v in merged.items()]).reindex(columns=COLUMNS)
    old = load()
    # 同一天以這次抓到的為準，這次沒有的欄位沿用舊值
    both = pd.concat([old, new], ignore_index=True)
    out = both.groupby("date", as_index=False).last().reindex(columns=COLUMNS).sort_values("date")
    before = old.sort_values("date").reset_index(drop=True)
    out = out.reset_index(drop=True)
    if len(out) == len(before) and out.fillna(-1e18).equals(before.fillna(-1e18)):
        lg.info("選擇權：與上次相同")
        return 0
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CSV_PATH, index=False, lineterminator="\n")
    lg.info(f"選擇權：{len(out)} 天（新增或更新 {len(new)} 天）")
    return len(new)
