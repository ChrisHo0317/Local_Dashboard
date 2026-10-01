"""情報中心網頁資料：類股的多區間漲跌。"""
import pandas as pd

import intel_build as ib


def _panel():
    days = pd.bdate_range("2026-06-01", periods=61)
    rows = []
    for i, d in enumerate(days):
        rows.append({"date": d, "code": "1111", "market": "twse", "close": 100.0 + i,
                     "turnover": 1e9})
        if i != 55:                                  # 2222 第 55 天停牌
            rows.append({"date": d, "code": "2222", "market": "tpex", "close": 50.0,
                         "turnover": 3e9})
        if i >= 58:                                  # 3333 最近才上市
            rows.append({"date": d, "code": "3333", "market": "twse", "close": 10.0 + i,
                         "turnover": 1e8})
    return pd.DataFrame(rows), list(days)


def test_sector_periods():
    panel, days = _panel()
    master = pd.DataFrame({"code": ["1111", "2222", "3333"], "name": ["甲", "乙", "丙"],
                           "market": ["twse", "tpex", "twse"],
                           "industry": ["半導體業", "半導體業", "光電業"]})
    d = ib._sectors(panel, master, days)
    assert d["periods"] == [1, 5, 10, 20, 60]
    rows = {s[0]: s for s in d["stocks"]}
    a = rows["1111"]
    assert a[5] == round((160 / 159 - 1) * 100, 2)          # 1 日
    assert a[6] == round((160 / 155 - 1) * 100, 2)          # 5 日
    assert a[9] == round((160 / 100 - 1) * 100, 2)          # 60 日
    assert rows["2222"][5:] == [0.0] * 5                     # 停牌那天沿用前一天收盤
    assert rows["3333"][6] is None                           # 上市不到 5 天算不出 5 日漲跌
    semi = next(s for s in d["industries"] if s["industry"] == "半導體業")
    assert semi["n"] == 2 and len(semi["chg"]) == 5
    # 依成交值加權：1111 佔 1/4、2222（0%）佔 3/4
    assert semi["chg"][4] == round(60.0 * 0.25, 2)
    assert semi["up"][4] == 1 and semi["down"][4] == 0
