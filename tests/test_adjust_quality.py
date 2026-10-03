"""還原權值、權值事件與注意處置的解析、資料品質檢查。"""
from datetime import date, datetime

import pandas as pd

import intel_data
import market_scraper as ms
import quality


def _panel(rows):
    df = pd.DataFrame(rows, columns=["date", "code", "market", "open", "high", "low", "close", "ref"])
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["code", "date"]).reset_index(drop=True)


def test_adjust_uses_events_ref_and_neutralizes_unexplained_jumps():
    rows = []
    days = pd.bdate_range("2026-08-03", periods=8)
    # A：第 4 天除息（事件表：100 → 95），之後照常
    for i, (d, c) in enumerate(zip(days, [100, 101, 100, 96, 97, 98, 99, 100])):
        rows.append([d, "1111", "twse", c, c, c, c, None])
    # B：第 5 天參考價 50（前一天 100，1 拆 2），事件表沒有
    for i, (d, c) in enumerate(zip(days, [100, 100, 100, 100, 51, 52, 53, 54])):
        rows.append([d, "2222", "tpex", c, c, c, c, 50.0 if i == 4 else None])
    # C：第 3 天 0 元（缺值），第 6 天無故 −40%（找不到事件）
    for i, (d, c) in enumerate(zip(days, [10, 10, 0, 10, 10, 6, 6.1, 6.2])):
        rows.append([d, "3333", "tpex", c, c, c, c, None])
    events = pd.DataFrame({"date": [days[3].strftime("%Y-%m-%d")], "code": ["1111"],
                           "factor": [0.95]})
    out = intel_data.adjust(_panel(rows), events)
    a = out[out["code"] == "1111"]["close"].tolist()
    assert abs(a[2] - 95.0) < 1e-9 and a[-1] == 100           # 事件前乘 0.95，最新一天不變
    b = out[out["code"] == "2222"]["close"].tolist()
    assert abs(b[3] - 50.0) < 1e-9 and b[4] == 51              # 拆分前價格減半，報酬連續
    c = out[out["code"] == "3333"]
    assert pd.isna(c["close"].iloc[2]) and pd.isna(c["raw_close"].iloc[2])   # 0 元變缺值
    assert c["jump"].sum() == 1 and bool(c["jump"].iloc[5])
    r = c["close"].pct_change()
    assert abs(r.iloc[5]) < 1e-9                                # 找不到事件的跳動記為 0
    assert out["raw_close"].iloc[0] == 100


def test_ref_and_event_parsers():
    assert ms._ref(100.0, "<p style= color:red>+</p>", "2.00") == 98.0
    assert ms._ref(100.0, "<p style= color:green>-</p>", "2.00") == 102.0
    assert ms._ref(100.0, "<p>X</p>", "0.00") is None
    payload = {"stat": "OK", "fields": ["恢復買賣日期", "股票代號", "名稱", "停止買賣前收盤價格", "恢復買賣參考價"],
               "data": [["114/08/25", "2327", "國巨", "546.00", "136.50"]]}
    ev = ms.parse_twse_events(payload, "變更面額")
    assert ev == [{"date": "2025-08-25", "code": "2327", "market": "twse", "kind": "變更面額",
                   "before": 546.0, "ref": 136.5, "factor": 0.25}]
    tp = ms.parse_tpex_events([{"Date": "1151002", "SecuritiesCompanyCode": "6171",
                                "ClosePriceBeforeExRightsDiviend": "27.35",
                                "ExRightsDiviendQuote": "25.35", "ExRightsDiviend": "除息"}])
    assert tp[0]["date"] == "2026-10-02" and tp[0]["kind"] == "除息" and round(tp[0]["factor"], 4) == 0.9269


def test_flag_parser():
    flags = ms.parse_flags(
        [{"Code": "1234", "Name": "甲", "Date": "1151002", "TradingInfoForAttention": "漲幅過大"}],
        [{"Code": "5678", "Name": "乙", "Date": "1150930", "DispositionPeriod": "115/10/01～115/10/07",
          "DispositionMeasures": "第一次處置", "ReasonsOfDisposition": "連續三次"}],
        [], [{"SecuritiesCompanyCode": "9999", "CompanyName": "丙", "Date": "1151002",
              "DispositionPeriod": "1151005~1151012", "DispositionReasons": "連續3個營業日"}])
    by = {f["code"]: f for f in flags}
    assert by["1234"]["kind"] == "注意" and by["1234"]["date"] == "2026-10-02"
    assert by["5678"]["start"] == "2026-10-01" and by["5678"]["end"] == "2026-10-07"
    assert by["9999"]["market"] == "tpex" and by["9999"]["end"] == "2026-10-12"


def test_trading_gap_skips_weekends_holidays_and_before_close():
    fri = date(2026, 10, 2)
    assert quality.trading_gap(fri, datetime(2026, 10, 5, 10, 0), set()) == 0     # 週一收盤前
    assert quality.trading_gap(fri, datetime(2026, 10, 5, 18, 0), set()) == 1
    assert quality.trading_gap(fri, datetime(2026, 10, 6, 18, 0), {"2026-10-05"}) == 1
    assert quality.trading_gap(fri, datetime(2026, 10, 7, 18, 0), set()) == 3


def test_old_daily_files_without_new_columns(tmp_path, monkeypatch):
    """加欄位以前存的日期檔：讀取時補空欄，判斷缺哪些資料組不能出錯。"""
    import market_data as md
    monkeypatch.setattr(md, "DAILY_DIR", tmp_path)
    day = date(2026, 9, 1)
    old = pd.DataFrame({"code": ["2330"], "market": ["twse"], "open": [1.0], "high": [1.0], "low": [1.0],
                        "close": [1.0], "volume": [1.0], "turnover": [1.0]})
    old.to_parquet(md._path(day), index=False)
    df = md.load_day(day)
    assert list(df.columns) == md.COLUMNS and df["ref"].isna().all()
    got = md.present_groups(day)
    assert "quotes" in got["twse"] and "lending" not in got["twse"]
