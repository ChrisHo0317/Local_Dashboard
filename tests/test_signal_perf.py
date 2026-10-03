"""訊號績效：新進榜、投信開始連買、報酬與成本、統計判讀。"""
import numpy as np
import pandas as pd

import signal_perf as sp


def _m(n=30):
    dates = pd.bdate_range("2026-06-01", periods=n)
    close = pd.DataFrame({"1111": np.linspace(100, 129, n), "2222": [50.0] * n}, index=dates)
    return {"close": close, "open": close.copy(), "tv20": pd.DataFrame(2e8, index=dates, columns=close.columns),
            "trust": pd.DataFrame(0.0, index=dates, columns=close.columns)}


def test_new_entries_only_first_day_in_list():
    idx = pd.bdate_range("2026-06-01", periods=5)
    member = pd.DataFrame({"A": [False, True, True, False, True], "B": [True, True, True, True, True]}, index=idx)
    ev = sp.new_entries(member)
    got = sorted((d.strftime("%m-%d"), c) for d, c in zip(ev["date"], ev["code"]))
    assert got == [("06-01", "B"), ("06-02", "A"), ("06-05", "A")]


def test_trust_start_fires_on_third_day_after_quiet_period():
    m = _m(30)
    t = m["trust"]
    t.iloc[:24, 0] = -1000.0                  # 之前一直賣
    t.iloc[24:28, 0] = 5000.0                 # 第 24 天起連買 4 天
    t.iloc[:, 1] = 1000.0                     # 一直在買的不算「開始」
    ev = sp.trust_events(m)
    assert ev["1111"].sum() == 1 and bool(ev["1111"].iloc[26])
    assert ev["2222"].sum() == 0


def test_event_returns_use_next_open_cost_and_benchmark():
    m = _m(30)
    fwd = sp.forward_returns(m)
    bench = sp.benchmark(fwd, m)
    ev = pd.DataFrame({"date": [m["close"].index[0]], "code": ["1111"]})
    out = sp.event_returns(ev, fwd, bench)
    raw5 = (m["close"]["1111"].iloc[5] / m["open"]["1111"].iloc[1] - 1) * 100
    assert abs(out["r5"].iloc[0] - (raw5 - sp.COST)) < 1e-9
    b5 = (raw5 + 0.0) / 2                    # 兩檔等權，2222 報酬 0
    assert abs(out["x5"].iloc[0] - (raw5 - b5)) < 1e-9
    late = pd.DataFrame({"date": [m["close"].index[-3]], "code": ["1111"]})
    assert pd.isna(sp.event_returns(late, fwd, bench)["r5"].iloc[0])   # 還沒到期


def test_summarize_verdicts():
    rng = np.random.default_rng(0)
    good = pd.DataFrame({f"r{h}": rng.normal(2, 1, 50) for h in sp.HORIZONS}
                        | {f"x{h}": rng.normal(2, 1, 50) for h in sp.HORIZONS})
    assert sp.summarize(good)["20"]["verdict"] == "優於大盤"
    few = good.head(10)
    assert sp.summarize(few)["20"]["verdict"] == "樣本不足"
    flat = good.assign(x20=rng.normal(0, 1, 50))
    assert sp.summarize(flat)["20"]["verdict"] in ("沒有明顯差異", "優於大盤", "輸給大盤")


def test_member_stats_counts_streak_and_last():
    idx = pd.bdate_range("2026-06-01", periods=6)
    member = pd.DataFrame({"A": [True, True, False, True, True, True],
                           "B": [True, False, False, False, False, False],
                           "C": [False] * 6}, index=idx)
    st = sp.member_stats(member, windows=(3, 6))
    assert st.loc["A", "c3"] == 3 and st.loc["A", "c6"] == 5 and st.loc["A", "streak"] == 3
    assert st.loc["A", "last"] == 5
    assert st.loc["B", "c6"] == 1 and st.loc["B", "streak"] == 0 and st.loc["B", "last"] == 0
    assert st.loc["C", "c6"] == 0 and st.loc["C", "last"] == -1
