"""總覽「走勢」卡片：挑項目、漲跌、殖利率用百分點、10−2 利差、其餘型號數。"""
import pandas as pd

import trend_cards as tc


def _df(rows, col):
    return pd.DataFrame(rows, columns=["item", "price_date", col]).assign(
        price_date=lambda d: pd.to_datetime(d["price_date"]))


def test_dram_card_picks_main_models():
    days = pd.bdate_range("2026-09-01", periods=25)
    rows = [(n, d, 10.0 + i) for n in ("DDR5 16Gb (2Gx8) 4800/5600", "DDR3 4Gb 512Mx8 1600/1866")
            for i, d in enumerate(days)]
    c = tc.card({"id": "dram", "tab": "DRAM", "title": "t"}, _df(rows, "avg_price"))
    assert [r["name"] for r in c["rows"]] == ["DDR5 16G"] and c["more"] == 1
    r = c["rows"][0]
    assert r["last"] == 34.0 and r["d1"] == round((34 / 33 - 1) * 100, 2) and len(c["spark"]) == 25
    assert c["date"] == days[-1].strftime("%Y-%m-%d")


def test_bond_card_uses_points_and_spread():
    rows = [("2年期", "2026-10-01", 4.0), ("2年期", "2026-10-02", 4.1),
            ("10年期", "2026-10-01", 4.5), ("10年期", "2026-10-02", 4.5)]
    c = tc.card({"id": "bond", "tab": "美債", "title": "t"}, _df(rows, "yield_pct"))
    names = [r["name"] for r in c["rows"]]
    assert names == ["2 年", "10 年", "10−2 利差"]
    assert c["rows"][0]["unit"] == "pt" and c["rows"][0]["d1"] == 0.1
    assert c["rows"][2]["last"] == 0.4 and c["rows"][2]["d1"] == -0.1


def test_empty_frame():
    c = tc.card({"id": "gold", "tab": "黃金", "title": "t"}, pd.DataFrame())
    assert c["rows"] == [] and c["spark"] == []
