"""總經：各來源解析、年增率、景氣燈號、M1B／M2 交叉、經濟日曆公布值。"""
import io
import zipfile

import pandas as pd

import calendar_data
import calendar_render
import macro_data as m


def test_period_parsing():
    assert m._ym("202608") == "2026-08-01"
    assert m._ym("2026M08") == "2026-08-01"
    assert m._ym("11507") == "2026-07-01"          # 民國
    assert m._ym("07301") == "1984-01-01"
    assert m._ym("abc") is None and m._ym("202613") is None


def test_parsers():
    fred = "observation_date,UNRATE\n2026-08-01,4.1\n2026-09-01,.\n"
    assert m.parse_fred(fred, "UNRATE") == [("UNRATE", "2026-08-01", 4.1)]
    pmi = "Date,PMI,NMI\n202608,62.5,55.6\n201207,47.1,-\n"
    assert m.parse_pmi(pmi) == [("tw_pmi", "2026-08-01", 62.5), ("tw_nmi", "2026-08-01", 55.6),
                                ("tw_pmi", "2012-07-01", 47.1)]
    cbc = ('"期間","貨幣總計數 -Ｍ１Ｂ-原始值","貨幣總計數 -Ｍ１Ｂ-年增率","貨幣總計數 -Ｍ２-年增率"\n'
           '"2026M08","30750789","6.65499","6.78887"\n"1987M05","1","-","-"\n')
    assert m.parse_cbc_money(cbc) == [("tw_m1b_yoy", "2026-08-01", 6.65499), ("tw_m2_yoy", "2026-08-01", 6.78887)]
    orders = "統計項目,資料期(民國年),統計值(美元)\n外銷訂單金額,11507,97939\n其他,11507,1\n"
    assert m.parse_orders(orders) == [("tw_orders", "2026-07-01", 97939.0)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("景氣指標與燈號.csv", '"Date","領先指標不含趨勢指數","景氣對策信號綜合分數","景氣對策信號"\n'
                                        '202608,104.4,41,紅\n'.encode("utf-8-sig"))
    rows = m.parse_ndc_zip(buf.getvalue())
    assert ("tw_signal", "2026-08-01", 41.0) in rows and ("tw_leading", "2026-08-01", 104.4) in rows


def test_transform_and_light():
    s = pd.Series([100.0, 102.0, 110.0], index=pd.to_datetime(["2025-07-01", "2025-08-01", "2026-08-01"]))
    yoy = m.transform(s, "yoy")
    assert list(yoy.index) == [pd.Timestamp("2026-08-01")] and round(yoy.iloc[0], 4) == round((110 / 102 - 1) * 100, 4)
    assert m.light(41) == "紅燈" and m.light(32) == "黃紅燈" and m.light(23) == "綠燈"
    assert m.light(17) == "黃藍燈" and m.light(12) == "藍燈"


def _df(rows):
    return pd.DataFrame(rows, columns=m.COLUMNS)


def test_cards_and_highlights():
    months = pd.date_range("2025-01-01", periods=20, freq="MS").strftime("%Y-%m-%d")
    rows = [("tw_signal", d, 30 + i % 3 * 5) for i, d in enumerate(months)]           # 30,35,40 循環
    rows += [("tw_m1b_yoy", d, 3 + i * 0.5) for i, d in enumerate(months)]           # 逐月上升
    rows += [("tw_m2_yoy", d, 8.0) for d in months]
    rows += [("tw_pmi", d, 49 + i) for i, d in enumerate(months)]
    rows += [("ICSA", "2026-09-26", 197000.0), ("ICSA", "2026-09-19", 198000.0)]
    cs = m.cards(_df(rows))
    by = {c["id"]: c for c in cs}
    assert by["tw_signal"]["light"] == m.light(by["tw_signal"]["last"])
    assert by["us_claims"]["last"] == 197 and by["us_claims"]["chg"] == -1   # 換成千人
    money = by["tw_money"]
    assert money["last"] == 12.5 and money["last2"] == 8.0
    assert money["cross"] == 9                                             # i=11 起高於 M2（i=10 相等）
    hl = m.highlights(cs)
    assert any("黃金交叉第 9 個月" in x for x in hl)
    assert any(x.startswith("製造業 PMI 68") and "連續 19 個月擴張" in x for x in hl)


def test_calendar_actual_columns(tmp_path, monkeypatch):
    path = tmp_path / "cal.csv"
    # 舊檔沒有 actual／better 欄位
    path.write_text("event_time,country,title,impact,forecast,previous\n"
                    "2026-10-02T12:30:00Z,US,Nonfarm Payrolls,High,100,162\n", encoding="utf-8")
    monkeypatch.setattr(calendar_data, "CSV_PATH", path)
    df = calendar_data.load_events()
    assert list(df.columns[:8]) == calendar_data.COLUMNS and df.iloc[0]["actual"] == ""
    calendar_data.merge_events([{"event_time": "2026-10-02T12:30:00Z", "country": "US",
                                 "title": "Nonfarm Payrolls", "impact": "High", "forecast": "90",
                                 "previous": "162", "actual": "29", "better": "0"}])
    df = calendar_data.load_events()
    assert df.iloc[0]["actual"] == "29" and df.iloc[0]["better"] == "0" and df.iloc[0]["forecast"] == "100"
    assert calendar_render.surprise("29", "100") == -1 and calendar_render.surprise("3.1%", "3.0%") == 1
    assert calendar_render.surprise("4.2", "4.2") == 0 and calendar_render.surprise("29", "") == 0
    html = calendar_render._actual(df.iloc[0])
    assert "cal-bad" in html and "29▼" in html and "低於預期" in html
