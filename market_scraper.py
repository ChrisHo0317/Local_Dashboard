"""
全市場每日資料爬蟲（證交所＋櫃買中心，依日期查詢）

    上市   www.twse.com.tw/rwd/zh/...    MI_INDEX（收盤行情、指數、成交值）
                                        T86（三大法人）、BFI82U（法人金額）
                                        MI_MARGN（融資融券）、BWIBBU_d（本益比）
    上櫃   www.tpex.org.tw/www/zh-tw/... afterTrading/otc（收盤行情）
                                        insti/dailyTrade、insti/summary（法人）
                                        margin/balance（融資融券）
                                        afterTrading/peQryDate（本益比）
           www.tpex.org.tw/openapi/v1/tpex_index（櫃買指數，當月每日）

    權值事件 證交所 exRight/TWT49U（除權除息計算結果）、reducation/TWTAUU（減資恢復買賣）、
           change/TWTB8U（變更面額恢復買賣）；櫃買 openapi tpex_exright_daily（除權除息）
    注意／處置 證交所 openapi announcement/notice、announcement/punish；
           櫃買 openapi tpex_trading_warning_information、tpex_disposal_information

這些都是官方公開、可帶日期的端點，所以缺了哪天就能回頭補，不必用 FinMind。

參考價（ref）：收盤 − 漲跌。除權息、減資、分割那天的參考價不是前一天收盤，
還原權值就靠它；證交所那幾天的漲跌欄是「X」（不比價），改用上面的權值事件表。
回應的解析寫成獨立函式（parse_*），測試用存下來的樣本直接餵。

休市日：證交所回「很抱歉，沒有符合條件的資料」，櫃買回 stat ok 但沒有資料列，
兩者都當成「那天沒有交易」，回傳 None。
"""
import logging
import re
import time
from datetime import date

import pandas as pd
from curl_cffi import requests as cffi_requests

TWSE = "https://www.twse.com.tw/rwd/zh/"
TWSE_OPENAPI = "https://openapi.twse.com.tw/v1/"
TPEX = "https://www.tpex.org.tw/www/zh-tw/"
TPEX_OPENAPI = "https://www.tpex.org.tw/openapi/v1/"

# 證交所對同一來源連續請求很敏感，間隔拉開一點
TWSE_GAP = 2.5
TPEX_GAP = 1.0


def num(value):
    """'1,234.5' → 1234.5；'--'、''、'X' 之類 → None。HTML 標記（漲跌符號）先去掉。"""
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", "", str(value)).replace(",", "").strip()
    if text in ("", "-", "--", "---", "----", "X", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _sign(value) -> int:
    """證交所的漲跌欄是 <p style=color:red>+</p> 這種 HTML，取出正負號。"""
    text = re.sub(r"<[^>]+>", "", str(value or "")).strip()
    return -1 if text.startswith("-") else 1


def _ref(close, sign_cell, change) -> float | None:
    """參考價＝收盤 − 漲跌。「X」（不比價：除權息、減資、分割、新上市）回傳 None。"""
    mark = re.sub(r"<[^>]+>", "", str(sign_cell or "")).strip()
    if close is None or mark.upper() == "X":
        return None
    chg = num(change)
    if chg is None:
        return None
    return round(close - (-chg if mark.startswith("-") else chg), 4)


def _code(value) -> str:
    return str(value or "").strip()


def _frame(rows: list[dict]) -> pd.DataFrame | None:
    return pd.DataFrame(rows) if rows else None


# ── 證交所 ──────────────────────────────────────────────────
def parse_twse_quotes(payload: dict) -> tuple[pd.DataFrame | None, dict]:
    """MI_INDEX：個股收盤行情＋加權指數＋成交值。"""
    if not payload or payload.get("stat") != "OK":
        return None, {}
    summary = {}
    rows = []
    for table in payload.get("tables") or []:
        fields = table.get("fields") or []
        data = table.get("data") or []
        if "證券代號" in fields and "收盤價" in fields:
            ix = {f: i for i, f in enumerate(fields)}
            for r in data:
                close = num(r[ix["收盤價"]])
                rows.append({
                    "code": _code(r[ix["證券代號"]]), "market": "twse",
                    "open": num(r[ix["開盤價"]]), "high": num(r[ix["最高價"]]),
                    "low": num(r[ix["最低價"]]), "close": close,
                    "volume": num(r[ix["成交股數"]]), "turnover": num(r[ix["成交金額"]]),
                    "ref": _ref(close, r[ix["漲跌(+/-)"]], r[ix["漲跌價差"]])
                           if "漲跌(+/-)" in ix and "漲跌價差" in ix else None,
                })
        elif fields[:2] == ["指數", "收盤指數"]:
            for r in data:
                if str(r[0]).strip() == "發行量加權股價指數":
                    summary["twse_index"] = num(r[1])
                    pts = num(r[3])
                    if pts is not None:
                        summary["twse_index_chg"] = pts * _sign(r[2])
        elif fields[:2] == ["成交統計", "成交金額(元)"]:
            for r in data:
                if str(r[0]).startswith("總計"):
                    summary["twse_turnover"] = num(r[1])
    return _frame(rows), summary


def parse_twse_insti(payload: dict) -> pd.DataFrame | None:
    """T86：外資取「不含外資自營商」，與上櫃一致；自營商取合計。"""
    if not payload or payload.get("stat") != "OK" or not payload.get("data"):
        return None
    ix = {f: i for i, f in enumerate(payload["fields"])}
    f_col = ix["外陸資買賣超股數(不含外資自營商)"]
    t_col = ix["投信買賣超股數"]
    d_col = ix["自營商買賣超股數"]
    rows = [{
        "code": _code(r[ix["證券代號"]]), "market": "twse",
        "foreign": num(r[f_col]), "trust": num(r[t_col]), "dealer": num(r[d_col]),
    } for r in payload["data"]]
    return _frame(rows)


def parse_twse_insti_value(payload: dict) -> dict:
    """BFI82U：三大法人買賣金額（元）。"""
    if not payload or payload.get("stat") != "OK":
        return {}
    net = {str(r[0]).strip(): num(r[3]) for r in payload.get("data") or []}
    foreign = (net.get("外資及陸資(不含外資自營商)") or 0) + (net.get("外資自營商") or 0)
    dealer = (net.get("自營商(自行買賣)") or 0) + (net.get("自營商(避險)") or 0)
    return {"foreign_value": foreign, "trust_value": net.get("投信"), "dealer_value": dealer}


def parse_twse_margin(payload: dict) -> tuple[pd.DataFrame | None, dict]:
    """MI_MARGN：第二張表是個股，第一張表有融資金額（仟元）總計。"""
    if not payload or payload.get("stat") != "OK":
        return None, {}
    summary = {}
    rows = []
    for table in payload.get("tables") or []:
        fields = table.get("fields") or []
        data = table.get("data") or []
        if fields[:1] == ["項目"]:
            for r in data:
                if str(r[0]).startswith("融資金額"):
                    summary["margin_amount_prev"] = num(r[4])
                    summary["margin_amount"] = num(r[5])
        elif fields[:1] == ["代號"]:
            # 欄位名稱前後兩段重複（融資一段、融券一段），只能依位置取：
            # 6 = 融資今日餘額，12 = 融券今日餘額
            for r in data:
                rows.append({"code": _code(r[0]), "market": "twse",
                             "margin_bal": num(r[6]), "short_bal": num(r[12])})
    return _frame(rows), summary


def parse_twse_valuation(payload: dict) -> pd.DataFrame | None:
    """BWIBBU_d：本益比「-」代表虧損或無法計算，留空。"""
    if not payload or payload.get("stat") != "OK" or not payload.get("data"):
        return None
    ix = {f: i for i, f in enumerate(payload["fields"])}
    rows = [{
        "code": _code(r[ix["證券代號"]]), "market": "twse",
        "per": num(r[ix["本益比"]]), "yield_pct": num(r[ix["殖利率(%)"]]),
        "pbr": num(r[ix["股價淨值比"]]),
    } for r in payload["data"]]
    return _frame(rows)


# ── 櫃買中心 ────────────────────────────────────────────────
def _tpex_table(payload: dict) -> dict | None:
    if not payload or str(payload.get("stat", "")).lower() != "ok":
        return None
    tables = payload.get("tables") or []
    if not tables or not tables[0].get("data"):
        return None
    return tables[0]


def parse_tpex_quotes(payload: dict) -> tuple[pd.DataFrame | None, dict]:
    """afterTrading/otc：代號, 名稱, 收盤, 漲跌, 開盤, 最高, 最低, 成交股數, 成交金額 …"""
    table = _tpex_table(payload)
    if not table:
        return None, {}
    rows = []
    for r in table["data"]:
        close = num(r[2])
        chg = str(r[3]).strip()
        rows.append({
            "code": _code(r[0]), "market": "tpex",
            "close": close, "open": num(r[4]), "high": num(r[5]), "low": num(r[6]),
            "volume": num(r[7]), "turnover": num(r[8]),
            # 櫃買的漲跌是「+0.50」「-1.20」；除權息、新上市等不是數字的就沒有參考價
            "ref": _ref(close, "-" if chg.startswith("-") else "+", chg.lstrip("+-"))
                   if re.fullmatch(r"[+-]?[\d.,]+", chg) else None,
        })
    df = pd.DataFrame(rows)
    return df, {"tpex_turnover": float(df["turnover"].fillna(0).sum())}


def parse_tpex_insti(payload: dict) -> pd.DataFrame | None:
    """
    insti/dailyTrade：欄位名稱整排重複，依位置取。
    4 = 外資及陸資（不含外資自營商）買賣超、13 = 投信、22 = 自營商合計
    """
    table = _tpex_table(payload)
    if not table:
        return None
    rows = [{"code": _code(r[0]), "market": "tpex",
             "foreign": num(r[4]), "trust": num(r[13]), "dealer": num(r[22])}
            for r in table["data"]]
    return _frame(rows)


def parse_tpex_insti_value(payload: dict) -> dict:
    table = _tpex_table(payload)
    if not table:
        return {}
    net = {str(r[0]).replace("　", "").strip(): num(r[3]) for r in table["data"]}
    return {"foreign_value": net.get("外資及陸資合計"), "trust_value": net.get("投信"),
            "dealer_value": net.get("自營商合計")}


def parse_tpex_margin(payload: dict) -> tuple[pd.DataFrame | None, dict]:
    """margin/balance：6 = 資餘額、14 = 券餘額；summary 有融資金（仟元）。"""
    table = _tpex_table(payload)
    if not table:
        return None, {}
    rows = [{"code": _code(r[0]), "market": "tpex",
             "margin_bal": num(r[6]), "short_bal": num(r[14])} for r in table["data"]]
    summary = {}
    for r in table.get("summary") or []:
        if len(r) > 6 and str(r[1]).startswith("融資金"):
            summary = {"margin_amount_prev": num(r[2]), "margin_amount": num(r[6])}
    return _frame(rows), summary


def parse_tpex_valuation(payload: dict) -> pd.DataFrame | None:
    """peQryDate：股票代號, 公司名稱, 本益比, 每股股利, 股利年度, 殖利率(%), 股價淨值比"""
    table = _tpex_table(payload)
    if not table:
        return None
    rows = [{"code": _code(r[0]), "market": "tpex",
             "per": num(r[2]), "yield_pct": num(r[5]), "pbr": num(r[6])}
            for r in table["data"]]
    return _frame(rows)


def parse_tpex_index(payload: list, day: date) -> dict:
    """tpex_index：當月每日的櫃買指數，挑出指定那天。"""
    key = day.strftime("%Y%m%d")
    for r in payload or []:
        if str(r.get("Date")) == key:
            return {"tpex_index": num(r.get("Close")), "tpex_index_chg": num(r.get("Change"))}
    return {}


def names_from_quotes(payload: dict, market: str) -> pd.DataFrame:
    """收盤行情裡順便帶出股票名稱，更新股票清單用。"""
    rows = []
    if market == "twse":
        for table in (payload or {}).get("tables") or []:
            fields = table.get("fields") or []
            if "證券代號" in fields and "證券名稱" in fields:
                i, j = fields.index("證券代號"), fields.index("證券名稱")
                rows += [{"code": _code(r[i]), "name": str(r[j]).strip(), "market": "twse"}
                         for r in table.get("data") or []]
    else:
        table = _tpex_table(payload)
        if table:
            rows = [{"code": _code(r[0]), "name": str(r[1]).strip(), "market": "tpex"}
                    for r in table["data"]]
    return pd.DataFrame(rows, columns=["code", "name", "market"])


# ── 借券賣出、當沖 ──────────────────────────────────────────
def parse_twse_lending(payload: dict) -> pd.DataFrame | None:
    """TWT93U：前 7 欄是融券，後 6 欄是借券賣出（前日餘額、當日賣出、還券、調整、當日餘額、限額）。"""
    if not payload or payload.get("stat") != "OK" or not payload.get("data"):
        return None
    rows = []
    for r in payload["data"]:
        if len(r) < 13:
            continue
        rows.append({"code": _code(r[0]), "market": "twse", "sbl_sell": num(r[9]), "sbl_bal": num(r[12])})
    return _frame(rows)


def parse_twse_daytrade(payload: dict) -> tuple[pd.DataFrame | None, dict]:
    """TWTB4U：第一個表是全市場當沖比重，第二個表是個股當沖成交股數。"""
    if not payload or payload.get("stat") != "OK":
        return None, {}
    summary, rows = {}, []
    for t in payload.get("tables") or []:
        fields = t.get("fields") or []
        data = t.get("data") or []
        if fields and fields[0] == "當日沖銷交易總成交股數" and data:
            summary["twse_daytrade_pct"] = num(data[0][1])
        elif "證券代號" in fields and "當日沖銷交易成交股數" in fields:
            i, k = fields.index("證券代號"), fields.index("當日沖銷交易成交股數")
            rows += [{"code": _code(r[i]), "market": "twse", "dt_vol": num(r[k])} for r in data]
    return _frame(rows), summary


def parse_tpex_lending(payload: list) -> tuple[str | None, pd.DataFrame | None]:
    """tpex_margin_sbl（只有最新一天）：借券賣出當日餘額、當日借券賣出。"""
    rows, day = [], None
    for r in payload or []:
        keys = list(r)
        bal = next((k for k in keys if k.startswith("SecuritiesBorrowing") and "Balance" in k
                    and "Previous" not in k), None)
        sell = next((k for k in keys if k.startswith("SecuritiesBorrowing") and k.endswith("Sale")), None)
        day = day or _roc_date(r.get("Date"))
        rows.append({"code": _code(r.get("SecuritiesCompanyCode")), "market": "tpex",
                     "sbl_bal": num(r.get(bal)) if bal else None,
                     "sbl_sell": num(r.get(sell)) if sell else None})
    return day, _frame(rows)


def parse_tpex_daytrade(payload: list) -> dict:
    """tpex_intraday_trading_statistics：全市場當沖比重 {日期: %}。"""
    out = {}
    for r in payload or []:
        day = _roc_date(r.get("Date"))
        if day:
            out[day] = num(str(r.get("DayTradingVolumeOfTheMarket", "")).rstrip("%"))
    return out


# ── 權值事件 ────────────────────────────────────────────────
EVENT_COLUMNS = ["date", "code", "market", "kind", "before", "ref", "factor"]


def _roc_date(text) -> str | None:
    """「115年09月01日」「114/09/15」「1151002」→ 2026-09-01。"""
    digits = re.findall(r"\d+", str(text or ""))
    if len(digits) == 1 and len(digits[0]) == 7:
        d = digits[0]
        digits = [d[:3], d[3:5], d[5:]]
    if len(digits) != 3:
        return None
    try:
        return date(int(digits[0]) + 1911, int(digits[1]), int(digits[2])).isoformat()
    except ValueError:
        return None


def _event(day, code, market, kind, before, ref) -> dict | None:
    before, ref = num(before), num(ref)
    if not day or not code or not before or not ref:
        return None
    return {"date": day, "code": code, "market": market, "kind": kind,
            "before": before, "ref": ref, "factor": round(ref / before, 8)}


def parse_twse_events(payload: dict, kind: str) -> list[dict]:
    """TWT49U／TWTAUU／TWTB8U：日期、代號、事件前收盤、參考價。"""
    if not payload or payload.get("stat") != "OK":
        return []
    ix = {f: i for i, f in enumerate(payload.get("fields") or [])}
    day_col = "資料日期" if "資料日期" in ix else "恢復買賣日期"
    before_col = "除權息前收盤價" if "除權息前收盤價" in ix else "停止買賣前收盤價格"
    ref_col = "除權息參考價" if "除權息參考價" in ix else "恢復買賣參考價"
    out = []
    for r in payload.get("data") or []:
        e = _event(_roc_date(r[ix[day_col]]), _code(r[ix["股票代號"]]), "twse", kind,
                   r[ix[before_col]], r[ix[ref_col]])
        if e:
            out.append(e)
    return out


def parse_tpex_events(payload: list) -> list[dict]:
    """tpex_exright_daily：除權除息計算結果（openapi 只有最近幾天，每天累積）。"""
    out = []
    for r in payload or []:
        e = _event(_roc_date(r.get("Date")), _code(r.get("SecuritiesCompanyCode")), "tpex",
                   r.get("ExRightsDiviend") or "除權息",
                   r.get("ClosePriceBeforeExRightsDiviend"), r.get("ExRightsDiviendQuote"))
        if e:
            out.append(e)
    return out


# ── 注意股、處置股 ──────────────────────────────────────────
FLAG_COLUMNS = ["date", "code", "name", "market", "kind", "start", "end", "detail"]


def _period(text) -> tuple[str | None, str | None]:
    """「115/10/01～115/10/07」「1151005~1151012」→ 起迄。"""
    parts = re.split(r"[～~]", str(text or ""))
    if len(parts) != 2:
        return None, None
    return _roc_date(parts[0]), _roc_date(parts[1])


def parse_flags(twse_notice: list, twse_punish: list, tpex_warn: list, tpex_disp: list) -> list[dict]:
    out = []
    for r in twse_notice or []:
        code, day = _code(r.get("Code")), _roc_date(r.get("Date"))
        if code and day:
            out.append({"date": day, "code": code, "name": str(r.get("Name") or "").strip(),
                        "market": "twse", "kind": "注意", "start": day, "end": day,
                        "detail": str(r.get("TradingInfoForAttention") or "").strip()[:200]})
    for r in twse_punish or []:
        code, day = _code(r.get("Code")), _roc_date(r.get("Date"))
        start, end = _period(r.get("DispositionPeriod"))
        if code and day:
            out.append({"date": day, "code": code, "name": str(r.get("Name") or "").strip(),
                        "market": "twse", "kind": "處置", "start": start or day, "end": end or day,
                        "detail": (str(r.get("DispositionMeasures") or "") + "：" +
                                   str(r.get("ReasonsOfDisposition") or "")).strip("：")[:200]})
    for r in tpex_warn or []:
        code, day = _code(r.get("SecuritiesCompanyCode")), _roc_date(r.get("Date"))
        if code and day:
            out.append({"date": day, "code": code, "name": str(r.get("CompanyName") or "").strip(),
                        "market": "tpex", "kind": "注意", "start": day, "end": day,
                        "detail": str(r.get("TradingInformation") or "").strip()[:200]})
    for r in tpex_disp or []:
        code, day = _code(r.get("SecuritiesCompanyCode")), _roc_date(r.get("Date"))
        start, end = _period(r.get("DispositionPeriod"))
        if code and day:
            out.append({"date": day, "code": code, "name": str(r.get("CompanyName") or "").strip(),
                        "market": "tpex", "kind": "處置", "start": start or day, "end": end or day,
                        "detail": str(r.get("DispositionReasons") or "").strip()[:200]})
    return out


# ── 抓取 ────────────────────────────────────────────────────
class MarketScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("MarketScraper")
        self.session = cffi_requests.Session(impersonate="chrome124")
        self._last = {}

    def _get(self, url: str, host: str, gap: float):
        wait = self._last.get(host, 0) + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.logger.warning(f"{url.split('?')[0]} 讀取失敗：{e}")
            return None
        finally:
            self._last[host] = time.monotonic()

    def _twse(self, path: str):
        return self._get(TWSE + path, "twse", TWSE_GAP)

    def _tpex(self, path: str):
        return self._get(TPEX + path, "tpex", TPEX_GAP)

    def fetch(self, day: date, groups: dict[str, set[str]]) -> dict:
        """
        抓指定日期缺的部分。groups：{市場: 要抓的欄位組}。
        回傳 {"frames": [DataFrame…], "summary": {...}, "names": [DataFrame…], "closed": bool}
        closed＝兩個市場的收盤行情都說那天沒資料（休市）。
        """
        ymd = day.strftime("%Y%m%d")
        slash = day.strftime("%Y%%2F%m%%2F%d")
        out = {"frames": [], "summary": {}, "names": [], "closed": False}
        no_quotes = 0

        tw = groups.get("twse", set())
        if "quotes" in tw:
            p = self._twse(f"afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json")
            df, summ = parse_twse_quotes(p)
            if df is None:
                no_quotes += 1
            else:
                out["frames"].append(df)
                out["summary"].update(summ)
                out["names"].append(names_from_quotes(p, "twse"))
        if "insti" in tw:
            df = parse_twse_insti(self._twse(f"fund/T86?date={ymd}&selectType=ALLBUT0999&response=json"))
            if df is not None:
                out["frames"].append(df)
                value = parse_twse_insti_value(
                    self._twse(f"fund/BFI82U?type=day&dayDate={ymd}&response=json"))
                out["summary"].update({f"twse_{k}": v for k, v in value.items()})
        if "margin" in tw:
            df, summ = parse_twse_margin(
                self._twse(f"marginTrading/MI_MARGN?date={ymd}&selectType=ALL&response=json"))
            if df is not None:
                out["frames"].append(df)
                out["summary"].update({f"twse_{k}": v for k, v in summ.items()})
        if "valuation" in tw:
            df = parse_twse_valuation(
                self._twse(f"afterTrading/BWIBBU_d?date={ymd}&selectType=ALL&response=json"))
            if df is not None:
                out["frames"].append(df)
        if "lending" in tw:
            df = parse_twse_lending(self._twse(f"marginTrading/TWT93U?date={ymd}&response=json"))
            if df is not None:
                out["frames"].append(df)
        if "daytrade" in tw:
            df, summ = parse_twse_daytrade(self._twse(f"dayTrading/TWTB4U?date={ymd}&response=json"))
            if df is not None:
                out["frames"].append(df)
                out["summary"].update(summ)

        tp = groups.get("tpex", set())
        if "quotes" in tp:
            p = self._tpex(f"afterTrading/otc?date={slash}&type=EW&response=json")
            df, summ = parse_tpex_quotes(p)
            if df is None:
                no_quotes += 1
            else:
                out["frames"].append(df)
                out["summary"].update(summ)
                out["names"].append(names_from_quotes(p, "tpex"))
                idx = self._get(TPEX_OPENAPI + "tpex_index", "tpex", TPEX_GAP)
                out["summary"].update(parse_tpex_index(idx, day))
        if "insti" in tp:
            df = parse_tpex_insti(self._tpex(
                f"insti/dailyTrade?type=Daily&sect=EW&date={slash}&response=json"))
            if df is not None:
                out["frames"].append(df)
                value = parse_tpex_insti_value(
                    self._tpex(f"insti/summary?type=Daily&date={slash}&response=json"))
                out["summary"].update({f"tpex_{k}": v for k, v in value.items()})
        if "margin" in tp:
            df, summ = parse_tpex_margin(self._tpex(f"margin/balance?date={slash}&response=json"))
            if df is not None:
                out["frames"].append(df)
                out["summary"].update({f"tpex_{k}": v for k, v in summ.items()})
        if "valuation" in tp:
            df = parse_tpex_valuation(self._tpex(f"afterTrading/peQryDate?date={slash}&response=json"))
            if df is not None:
                out["frames"].append(df)

        asked_quotes = ("quotes" in tw) + ("quotes" in tp)
        out["closed"] = asked_quotes == 2 and no_quotes == 2
        return out

    def tpex_latest(self) -> dict:
        """上櫃只給最新一天的：借券賣出（存到它回報的日期）、全市場當沖比重。"""
        day, df = parse_tpex_lending(self._get(TPEX_OPENAPI + "tpex_margin_sbl", "tpex", TPEX_GAP))
        dt = parse_tpex_daytrade(self._get(TPEX_OPENAPI + "tpex_intraday_trading_statistics", "tpex", TPEX_GAP))
        return {"lending_day": day, "lending": df, "daytrade": dt}

    def quotes(self, day: date, market: str):
        """只抓一個市場一天的收盤行情（回補參考價、修正零價用）；失敗回傳 None。"""
        if market == "twse":
            df, _ = parse_twse_quotes(self._twse(
                f"afterTrading/MI_INDEX?date={day:%Y%m%d}&type=ALLBUT0999&response=json"))
        else:
            df, _ = parse_tpex_quotes(self._tpex(
                f"afterTrading/otc?date={day:%Y}%2F{day:%m}%2F{day:%d}&type=EW&response=json"))
        return df

    def events(self, start: date, end: date) -> list[dict]:
        """start～end 之間的權值事件。證交所除權息表按月查（一次查太久會被拒）。"""
        out = []
        month = date(start.year, start.month, 1)
        while month <= end:
            nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
            a, b = max(start, month), min(end, date.fromordinal(nxt.toordinal() - 1))
            out += parse_twse_events(self._twse(
                f"exRight/TWT49U?startDate={a:%Y%m%d}&endDate={b:%Y%m%d}&response=json"), "除權息")
            month = nxt
        rng = f"startDate={start:%Y%m%d}&endDate={end:%Y%m%d}&response=json"
        out += parse_twse_events(self._twse(f"reducation/TWTAUU?{rng}"), "減資")
        out += parse_twse_events(self._twse(f"change/TWTB8U?{rng}"), "變更面額")
        out += parse_tpex_events(self._get(TPEX_OPENAPI + "tpex_exright_daily", "tpex", TPEX_GAP))
        return out

    def flags(self) -> list[dict]:
        """今天公布的注意股與目前的處置股（上市＋上櫃）。"""
        return parse_flags(
            self._get(TWSE_OPENAPI + "announcement/notice", "twse-open", TPEX_GAP),
            self._get(TWSE_OPENAPI + "announcement/punish", "twse-open", TPEX_GAP),
            self._get(TPEX_OPENAPI + "tpex_trading_warning_information", "tpex", TPEX_GAP),
            self._get(TPEX_OPENAPI + "tpex_disposal_information", "tpex", TPEX_GAP))
