"""市場熱度：全市場、權值股（市值加權、單檔上限）、高價股三個分項與綜合分數。"""
import pandas as pd
import pytest

import breadth


def _panel(n=80):
    days = pd.bdate_range("2026-01-01", periods=n)
    rows = []
    for k, d in enumerate(days):
        for code, px in (("2330", 100 + k),            # 大型權值股，一路漲
                         ("1111", 100 - k * 0.5),      # 一路跌
                         ("2222", 50 - k * 0.2),       # 一路跌
                         ("5274", 900 + k * 5),        # 漲到千元以上
                         ("0050", 100 + k)):           # ETF 不算
            rows.append({"date": d, "code": code, "close": px, "raw_close": px})
    return pd.DataFrame(rows)


SHARES = pd.Series({"2330": 1e10, "1111": 1e8, "2222": 1e8, "5274": 1e7})


def test_capped_weights():
    w = pd.DataFrame([[50.0] + [1.0] * 20])
    share = breadth._capped(w, 0.10)
    assert share.iloc[0, 0] == pytest.approx(0.10, abs=1e-6)
    assert share.iloc[0].sum() == pytest.approx(1.0)
    assert share.iloc[0, 1] == pytest.approx(0.9 / 20)


def test_three_parts_and_composite(monkeypatch):
    monkeypatch.setattr(breadth, "CAP_MAX", 0.9)          # 只有 4 檔，上限放寬才看得出權值股的影響
    b = breadth.breadth(_panel(), shares=SHARES)
    last = b.iloc[-1]
    assert (last["adv"], last["dec"], last["flat"]) == (2, 2, 0)     # ETF 不算
    assert last["temp_all"] == pytest.approx(50)
    assert last["temp_cap"] > 80                                     # 台積電權重大，權值股分項偏多
    assert last["p1000"] == 1 and last["p5000"] == 0 and last["hp_up"] == 1
    assert last["temp_hp"] > 80
    assert last["temp"] == pytest.approx(0.5 * last["temp_all"] + 0.3 * last["temp_cap"] + 0.2 * last["temp_hp"])
    assert breadth.divergence(last["temp_all"], last["temp_cap"], last["temp_hp"]) == "權值撐盤、多數個股弱"


def test_without_shares_skips_cap_part():
    b = breadth.breadth(_panel())
    last = b.iloc[-1]
    assert last["temp_cap"] != last["temp_cap"]                      # NaN
    assert last["temp"] == pytest.approx((0.5 * last["temp_all"] + 0.2 * last["temp_hp"]) / 0.7)


def test_divergence_labels():
    assert breadth.divergence(50, 60, 55) == ""
    assert breadth.divergence(70, 40, None) == "中小型股強、權值股弱"
    assert breadth.divergence(None, 80, 80) == ""


def test_summary_high_price_lists():
    s = breadth.summary(_panel(), shares=SHARES, names={"5274": "信驊"})
    assert s["hp"]["counts"] == {"10000": 0, "5000": 0, "1000": 1}
    assert s["hp"]["tiers"]["1000"] == [["5274", "信驊", 1295]]
    assert len(s["series"]["temp_cap"]) == len(s["series"]["t"])
