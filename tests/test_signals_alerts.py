"""選股條件與推播。"""
import pandas as pd
import pytest

import alerts
import signals


def _revenue(code, values, start_year=2025, start_month=1):
    rows = []
    y, m = start_year, start_month
    for v in values:
        rows.append({"code": code, "year": y, "month": m, "revenue": float(v)})
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return rows


def test_rev_accel_hit_and_miss():
    base = [200_000] * 12
    good = _revenue("1111", base + [210_000, 210_000, 210_000, 260_000, 260_000, 260_000])
    flat = _revenue("2222", base + [210_000, 210_000, 210_000, 210_000, 210_000, 190_000])
    small = _revenue("3333", [1_000] * 12 + [2_000] * 3 + [5_000] * 3)          # 基期太小
    etf = _revenue("0050", base + [210_000] * 3 + [260_000] * 3)
    df = pd.DataFrame(good + flat + small + etf)
    hits = {h["code"] for h in signals.rev_accel(df)}
    assert hits == {"1111"}
    assert signals.rev_accel(df, exclude={"1111"}) == []


def _panel(code, trust):
    days = pd.bdate_range("2026-06-01", periods=len(trust))
    return pd.DataFrame({"date": days, "code": code, "trust": trust, "close": 10.0})


def test_trust_start():
    fresh = _panel("1111", [0] * 20 + [-5] * 10 + [5, 5, 5])       # 之前沒在買，剛連買 3 天
    steady = _panel("2222", [5] * 33)                               # 一直在買，不算
    two = _panel("3333", [0] * 30 + [-1, 5, 5])                     # 只連 2 天
    hits = {h["code"] for h in signals.trust_start(pd.concat([fresh, steady, two]))}
    assert hits == {"1111"}


def test_value_yield():
    panel = pd.DataFrame([{"date": pd.Timestamp("2026-09-30"), "code": "1111", "per": 8.0,
                           "yield_pct": 6.0},
                          {"date": pd.Timestamp("2026-09-30"), "code": "2222", "per": 20.0,
                           "yield_pct": 6.0}])
    hist = pd.DataFrame([{"code": c, "ym": f"{2022 + i // 12}-{i % 12 + 1:02d}", "pe": 10 + i % 12}
                         for c in ("1111", "2222") for i in range(48)])
    hits = {h["code"] for h in signals.value_yield(panel, hist)}
    assert hits == {"1111"}


def test_chip_conc_needs_four_weeks():
    tdcc = pd.DataFrame({"date": pd.to_datetime(["2026-09-24"]), "code": ["1111"],
                         "big1000": [50.0]})
    hits, note = signals.chip_conc(tdcc, pd.DataFrame(columns=["code", "date", "margin_bal"]))
    assert hits == [] and "需要 4 週" in note


def test_messages_split_urgent():
    events = [{"id": "a", "code": "2330", "urgent": True, "title": "【重訊】2330", "body": "x"},
              {"id": "b", "code": "2330", "urgent": False, "line": "營收"},
              {"id": "c", "code": "6488", "urgent": False, "line": "法人"}]
    msgs = alerts.messages(events)
    assert len(msgs) == 2
    assert msgs[0]["level"] == "timeSensitive" and msgs[0]["ids"] == ["a"]
    assert msgs[1]["ids"] == ["b", "c"] and "2 則" in msgs[1]["title"]


@pytest.fixture
def sent_path(tmp_path, monkeypatch):
    path = tmp_path / "alerts_sent.csv"
    monkeypatch.setattr(alerts, "SENT_PATH", path)
    monkeypatch.setattr(alerts, "collect", lambda: [
        {"id": "x", "code": "2330", "urgent": False, "line": "營收"}])
    sent = []
    monkeypatch.setattr(alerts, "send", lambda msg, key, server: sent.append(msg) or True)
    return path, sent


def test_alerts_disabled(sent_path, monkeypatch):
    path, sent = sent_path
    monkeypatch.setenv("ALERTS_ENABLED", "false")
    monkeypatch.setenv("BARK_KEY", "k")
    assert alerts.main([]) == 0
    assert sent == [] and not path.exists()


def test_alerts_first_run_is_silent_then_sends_new(sent_path, monkeypatch):
    path, sent = sent_path
    monkeypatch.delenv("ALERTS_ENABLED", raising=False)
    monkeypatch.setenv("BARK_KEY", "k")
    alerts.main([])
    assert sent == [] and path.exists()                     # 第一次只記錄
    alerts.main([])
    assert sent == []                                       # 同一件事不再推
    monkeypatch.setattr(alerts, "collect", lambda: [
        {"id": "y", "code": "2330", "urgent": False, "line": "新事件"}])
    alerts.main([])
    assert len(sent) == 1 and sent[0]["ids"] == ["y"]


def test_alerts_without_key_sends_nothing(sent_path, monkeypatch):
    path, sent = sent_path
    monkeypatch.delenv("BARK_KEY", raising=False)
    monkeypatch.delenv("ALERTS_ENABLED", raising=False)
    assert alerts.main([]) == 0
    assert sent == [] and not path.exists()
