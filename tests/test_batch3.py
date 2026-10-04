"""第三批：外資持股、法說會、指數調整日、融資維持率（估）。"""
from datetime import date

import pandas as pd

import earnings_calls
import index_events
import intel_build
import qfii_data


def test_qfii_parsers():
    twse = {"stat": "OK", "fields": ["證券代號", "證券名稱", "全體外資及陸資持股比率"],
            "data": [["2330", "台積電", 69.17], ["0050", "元大台灣50", "1.5"], ["", "x", 1]]}
    assert qfii_data.parse_twse(twse) == [("2330", 69.17), ("0050", 1.5)]
    assert qfii_data.parse_twse({"stat": "很抱歉，沒有符合條件的資料!"}) == []
    tpex = {"tables": [{"fields": ["排行", "代號", "名稱", "僑外資及陸資持股比率(E=C/A)"],
                        "data": [["1", "8455", "大拓-KY", "87.84%"]]}]}
    assert qfii_data.parse_tpex(tpex) == [("8455", 87.84)]
    assert qfii_data.parse_tpex({}) == []


def test_qfii_changes(tmp_path, monkeypatch):
    rows = []
    for i, d in enumerate(pd.bdate_range("2026-09-01", periods=22).strftime("%Y-%m-%d")):
        rows.append((d, "2330", "twse", 70 - i * 0.1))
        rows.append((d, "2317", "twse", 40 + i * 0.2))
        if i >= 15:                                       # 上櫃晚開始累積
            rows.append((d, "8455", "tpex", 80 + (i - 15)))
    df = pd.DataFrame(rows, columns=qfii_data.COLUMNS)
    monkeypatch.setattr(qfii_data, "load", lambda: df)
    ch = qfii_data.changes({"2330": "台積電", "2317": "鴻海", "8455": "大拓"}, {}, None, window=20, top=5)
    assert ch["window"] == 20
    assert [r[0] for r in ch["up"]][:2] == ["8455", "2317"]
    assert ch["up"][0][4] == 6.0 and ch["down"][0][0] == "2330" and ch["down"][0][4] == -2.0


PAGE = """<table id='myTable'><tr class='even' data-type='body' >
<td style='text-align:left !important;'>2330</td><td>台積電</td>
<td align='center'>115/10/16</td><td align='center'>14:00</td>
<td>台北萬豪酒店</td><td>說明本公司 115 年第三季營運成果&#174;</td><td>x</td></tr>
<tr class='odd' data-type='body' ><td>1234</td><td>壞資料</td><td>沒有日期</td><td></td><td></td><td></td></tr>
</table>"""


def test_calls_parse():
    rows = earnings_calls.parse(PAGE, "twse")
    assert rows == [{"code": "2330", "name": "台積電", "market": "twse", "date": "2026-10-16", "time": "14:00",
                     "place": "台北萬豪酒店", "summary": "說明本公司 115 年第三季營運成果®"}]
    assert earnings_calls._months(date(2026, 1, 15)) == [(2025, 12), (2026, 1), (2026, 2)]


def test_index_events():
    ev = index_events.events(date(2026, 10, 1), date(2026, 12, 31))
    got = [(e["date"].isoformat(), e["title"][:4]) for e in ev]
    assert got == [("2026-11-30", "MSCI"), ("2026-12-18", "FTSE")]
    assert "00878" in ev[0]["title"] and "0056" in ev[1]["title"]
    # 最後一個營業日遇到週末往前
    assert index_events._last_weekday(2026, 2).isoformat() == "2026-02-27"
    assert index_events._third_friday(2026, 3).isoformat() == "2026-03-20"


def test_margin_ratio():
    panel = pd.DataFrame({"date": pd.to_datetime(["2026-10-01"] * 2 + ["2026-10-02"] * 2),
                          "code": ["2330", "8455"] * 2, "market": ["twse", "tpex"] * 2,
                          "margin_bal": [100.0, 50.0, 100.0, 50.0],
                          "close": [1000.0, 200.0, 1100.0, 200.0], "raw_close": [1000.0, 200.0, 1100.0, 200.0]})
    summary = pd.DataFrame({"date": ["2026-10-01", "2026-10-02"],
                            "twse_margin_amount": [60000.0, 60000.0],
                            "tpex_margin_amount": [6000.0, None]})
    r = intel_build.margin_ratio(panel, summary)
    # 10/01：(100×1000 + 50×200) ÷ 66000 × 100；10/02 上櫃金額缺 → 不算
    assert list(r.index) == ["2026-10-01"] and round(r.iloc[0], 2) == round(110000 / 66000 * 100, 2)
    k = intel_build.margin_kpi(panel, summary)
    assert k[0]["label"] == "融資維持率（估）" and k[0]["value"] == "166.7%"
