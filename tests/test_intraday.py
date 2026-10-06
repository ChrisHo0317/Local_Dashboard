"""盤中強勢族群：今日名單、量能曲線校正；Worker 與共用計算的 Node 測試。"""
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import intraday_universe as iu

ROOT = Path(__file__).resolve().parent.parent


def _panel():
    days = pd.bdate_range("2026-09-01", periods=22)
    rows = []
    for d in days:
        for code, tv in (("2330", 5e9), ("2408", 2e9), ("2344", 1e9), ("1234", 1e6), ("0050", 9e9), ("6770", 8e8)):
            rows.append({"date": d, "code": code, "turnover": tv})
    return pd.DataFrame(rows)


def test_universe():
    master = pd.DataFrame({"code": ["2330", "2408", "2344", "1234", "6770"],
                           "name": ["台積電", "南亞科", "華邦電", "小公司", "力積電"],
                           "market": ["twse", "twse", "twse", "tpex", "twse"], "industry": [""] * 5})
    tags = pd.DataFrame({"code": ["2408", "2344", "6770", "2330", "1234"],
                         "tag": ["記憶體", "記憶體", "記憶體", "晶圓代工", "記憶體"],
                         "chain": ["手動補充"] * 3 + ["半導體", "手動補充"], "stage": [""] * 5, "extra": [1, 1, 1, 0, 1]})
    hist = pd.DataFrame({"date": ["2026-09-29", "2026-09-30", "2026-09-30"], "group": ["舊族群", "記憶體", "個股"],
                         "linked": [True, True, False]})
    U = iu.build(_panel(), master, {"1234"}, tags, hist)
    assert U["codes"] == ["1234", "2330", "2344", "2408", "6770"]      # 自選股就算成交小也要列；ETF 不列
    assert U["mk"] == ["o", "t", "t", "t", "t"]
    assert U["groups"] == [["記憶體", "手動補充", [0, 2, 3, 4]]]          # 晶圓代工只有 1 檔，不成族群
    assert U["yday"] == ["記憶體"] and len(U["profile"]) == 271
    assert U["profile"][0] == 0 and U["profile"][-1] == 1.0
    assert all(a <= b for a, b in zip(U["profile"], U["profile"][1:]))


def test_universe_skips_suspended_watchlist_stock():
    # 自選股停牌 20 天（成交值全是 NaN）：不列，名單要是 Worker 讀得了的 JSON
    panel = pd.concat([_panel(), pd.DataFrame({"date": pd.bdate_range("2026-09-01", periods=22), "code": "1589",
                                               "turnover": float("nan")})])
    master = pd.DataFrame({"code": ["2330", "1589"], "name": ["台積電", "停牌股"], "market": ["twse", "twse"],
                           "industry": ["", ""]})
    U = iu.build(panel, master, {"1589"}, pd.DataFrame(columns=["code", "tag", "chain"]))
    assert "1589" not in U["codes"]
    json.dumps(U, allow_nan=False)


def test_profile_calibrates_from_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(iu, "ARCHIVE_DIR", tmp_path)
    assert iu._archive_points() is None
    for k in range(5):
        tl = [{"t": f"{9 + m // 60:02d}:{m % 60:02d}", "tv": 100 * (m / 270) ** 0.5} for m in range(0, 271, 5)]
        (tmp_path / f"2026-09-0{k + 1}.json").write_text(json.dumps({"timeline": tl}), encoding="utf-8")
    p = iu.profile()
    # 開盤半小時的實際比例 √(30/270) ≈ 0.33，和經驗值 0.28 不同，表示有用存檔
    assert abs(p[30] - (30 / 270) ** 0.5) < 0.02 and p[-1] == 1.0


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 Node")
def test_worker_and_core_in_node():
    r = subprocess.run(["node", "intraday/test_core.js"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
