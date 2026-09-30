"""資料層：日期檔的合併、基本面換算與累積、自選清單。"""
from datetime import date

import pandas as pd
import pytest

import fundamentals as fund
import market_data as md
from watchlist import parse


@pytest.fixture
def tmp_market(tmp_path, monkeypatch):
    monkeypatch.setattr(md, "MARKET_DIR", tmp_path)
    monkeypatch.setattr(md, "DAILY_DIR", tmp_path / "daily")
    monkeypatch.setattr(md, "SUMMARY_CSV", tmp_path / "summary.csv")
    monkeypatch.setattr(md, "STOCKS_CSV", tmp_path / "stocks.csv")
    return tmp_path


def test_save_day_merges_groups_without_overwriting(tmp_market):
    d = date(2026, 9, 24)
    assert md.save_day(d, pd.DataFrame([{"code": "2330", "market": "twse", "close": 2475.0}]))
    assert md.save_day(d, pd.DataFrame([{"code": "2330", "market": "twse", "foreign": -1.0}]))
    row = md.load_day(d).iloc[0]
    assert row["close"] == 2475.0 and row["foreign"] == -1.0        # 前一次的收盤沒被空值蓋掉
    assert not md.save_day(d, pd.DataFrame([{"code": "2330", "market": "twse", "close": 2475.0}]))
    assert md.present_groups(d)["twse"] == {"quotes", "insti"}


def test_save_day_drops_warrants(tmp_market):
    d = date(2026, 9, 24)
    md.save_day(d, pd.DataFrame([{"code": "030001", "market": "twse", "close": 1.0},
                                 {"code": "00878", "market": "twse", "close": 20.0}]))
    assert list(md.load_day(d)["code"]) == ["00878"]


def test_merge_summary_updates_only_given_fields(tmp_market):
    d = date(2026, 9, 24)
    assert md.merge_summary(d, {"twse_index": 1.0})
    assert md.merge_summary(d, {"tpex_index": 2.0})
    assert not md.merge_summary(d, {"tpex_index": 2.0})
    row = md.load_summary().iloc[0]
    assert (row["twse_index"], row["tpex_index"]) == (1.0, 2.0)


def test_single_quarter_from_ytd():
    history = pd.DataFrame([{"code": "1", "year": 2026, "quarter": 1, "revenue": 100.0,
                             "gross": 30.0, "operating": 20.0, "net": 10.0, "eps": 1.0}])
    ytd = pd.DataFrame([
        {"code": "1", "year": 2026, "quarter": 2, "revenue": 250.0, "gross": 70.0,
         "operating": 45.0, "net": 22.0, "eps": 2.2},
        {"code": "2", "year": 2026, "quarter": 2, "revenue": 50.0, "gross": 1.0,
         "operating": 1.0, "net": 1.0, "eps": 0.1},                       # 缺第一季 → 跳過
    ])
    out = fund.to_single_quarter(ytd, history)
    assert list(out["code"]) == ["1"]
    row = out.iloc[0]
    assert (row["revenue"], row["net"], row["eps"]) == (150.0, 12.0, 1.2)


def test_revenue_from_list_includes_previous_month():
    df = pd.DataFrame([{"code": "2330", "month": "11501", "revenue": "100", "prev_month": "90"}])
    cur, prev = fund.revenue_from_list(df)
    assert (cur.iloc[0]["year"], cur.iloc[0]["month"], cur.iloc[0]["revenue"]) == (2026, 1, 100.0)
    assert (prev.iloc[0]["year"], prev.iloc[0]["month"], prev.iloc[0]["revenue"]) == (2025, 12, 90.0)


def test_upsert_revenue_fill_only(tmp_path, monkeypatch):
    monkeypatch.setattr(fund, "FUND_DIR", tmp_path)
    monkeypatch.setattr(fund, "REVENUE_PATH", tmp_path / "revenue.parquet")
    base = pd.DataFrame([{"code": "1", "year": 2026, "month": 1, "revenue": 10.0}])
    assert fund.upsert_revenue(base) == 1
    patch = pd.DataFrame([{"code": "1", "year": 2026, "month": 1, "revenue": 99.0},
                          {"code": "1", "year": 2026, "month": 2, "revenue": 20.0}])
    assert fund.upsert_revenue(patch, overwrite=False) == 1          # 只補 2 月，不改 1 月
    rev = fund.load_revenue().set_index("month")["revenue"]
    assert (rev[1], rev[2]) == (10.0, 20.0)


def test_parse_mops_revenue():
    html = ("<table><tr align=right><td align=center>2330</td><td align=left>台積電</td>"
            "<td nowrap> 442,679,969</td><td> 1</td><td> 2</td></tr>"
            "<tr><td>合計</td><td></td><td>1</td><td>1</td><td>1</td></tr></table>")
    df = fund.parse_mops_revenue(html)
    assert df.to_dict("records") == [{"code": "2330", "revenue": 442679969.0}]


def test_watchlist_parse():
    text = "代號,備註,推播\n2330,範例,否\n6488,,是\n  \n2330,重複,是\nabc,壞的,是\n00878\n"
    rows = parse(text)
    assert [r["code"] for r in rows] == ["2330", "6488", "00878"]
    assert [r["push"] for r in rows] == [False, True, True]            # 沒寫推播欄視為要推
    assert parse("") == []
