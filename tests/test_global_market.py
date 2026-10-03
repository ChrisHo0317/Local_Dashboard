"""國際市場：漲跌、殖利率變動、和台股的連動（隔日／同日）、摘要文字。"""
import numpy as np
import pandas as pd

import global_market as gm


def _days(n, start="2026-01-05"):
    return pd.bdate_range(start, periods=n)


def test_change_and_ytd():
    s = pd.Series([100.0, 110.0, 121.0], index=pd.to_datetime(["2025-12-31", "2026-01-02", "2026-01-05"]))
    assert round(gm._change(s, 1, False), 2) == 10.0
    assert round(gm._ytd(s, False), 2) == 21.0
    y = pd.Series([4.0, 4.25], index=pd.to_datetime(["2025-12-31", "2026-01-02"]))
    assert gm._change(y, 1, True) == 0.25                       # 殖利率看百分點
    assert gm._change(s, 5, False) is None


def test_corr_lead_uses_previous_night():
    rng = np.random.default_rng(0)
    d = _days(150)
    us = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.01, 150)), index=d)
    # 台股每天的漲跌＝美股前一天的漲跌
    tw_ret = us.pct_change().shift(1).fillna(0)
    tw = pd.Series(100 * np.cumprod(1 + tw_ret.values), index=d)
    assert gm._corr(us, tw, "lead", False) > 0.95
    assert abs(gm._corr(us, tw, "sync", False)) < 0.3


def test_build_and_digest(monkeypatch):
    d = _days(80)
    series = {"加權指數": pd.Series(np.linspace(100, 120, 80), index=d),
              "標普500": pd.Series(np.linspace(50, 60, 80), index=d),
              "美債10年": pd.Series(np.linspace(4, 4.5, 80), index=d)}
    monkeypatch.setattr(gm, "load_series", lambda: series)
    g = gm.build()
    names = [r["name"] for grp in g["groups"] for r in grp["items"]]
    assert names == ["標普500", "加權指數", "美債10年"]
    rate = next(r for grp in g["groups"] for r in grp["items"] if r["name"] == "美債10年")
    assert rate["unit"] == "pt" and rate["last"] == 4.5 and len(rate["spark"]) == gm.SPARK_DAYS
    assert [k["name"] for k in g["key"]] == ["標普500", "美債10年"]
    assert len(g["series"]["標普500"][0]) == 80
    lines = gm.digest_lines(g)
    assert lines[0].startswith("美股大盤：標普500 60.00（+")
    assert "個百分點" in lines[-1]
