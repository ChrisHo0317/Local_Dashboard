"""盤中即時行情程式（feeder/feeder.py）：快照轉換、只送變動、流量放慢、設定檢查。不需要 shioaji、websockets。"""
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("feeder", ROOT / "feeder" / "feeder.py")
fd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fd)


def _snap(code, close, vol, amt, tt="Buy"):
    return SimpleNamespace(code=code, close=close, total_volume=vol, buy_price=close - 0.5, sell_price=close,
                           total_amount=amt, tick_type=SimpleNamespace(value=tt))


def test_row_and_diff():
    r = fd.row(_snap("2330", 2585.0, 18343, 47_400_000_000))
    assert r == [2585.0, 18343, 2584.5, 2585.0, 474.0, 1]
    assert fd.row(_snap("2330", 2585.0, 1, 0, "Sell"))[5] == 2                     # 1.7 的 tick_type 是字串
    assert fd.row(_snap("2330", 2585.0, 1, 0, "None"))[5] == 0
    assert fd.row(SimpleNamespace(code="X", close=None, tick_type="?"))[0] == 0     # 沒成交、欄位怪也不會壞
    prev = {"2330": r, "2317": [256, 1, 0, 0, 0.0, 2]}
    cur = {"2330": r, "2317": [256.5, 2, 0, 0, 0.0, 1], "1101": [25, 5, 0, 0, 0.0, 0]}
    assert set(fd.diff(prev, cur)) == {"2317", "1101"}


def test_message_format():
    now = datetime(2026, 10, 7, 11, 36, 5, tzinfo=fd.TPE)
    m = json.loads(fd.message("delta", now, {"2330": [1, 2, 3, 4, 5.0, 1]}))
    assert m["type"] == "delta" and m["date"] == "20261007" and m["t"] == "11:36:05"
    assert "q" not in json.loads(fd.message("hb", now))


def test_pace_slows_down_when_quota_is_short():
    # 已用 100 MB 跑了 100 輪（每輪 1 MB），還要 3000 輪，只剩 2000 MB → 放慢一級
    assert fd.pace(100e6, 2000e6, 100, 3000, 5) == 10
    assert fd.pace(100e6, 10_000e6, 100, 3000, 5) == 5
    assert fd.pace(100e6, 10e6, 100, 3000, 20) == 20                 # 已經最慢
    assert fd.pace(None, None, 100, 3000, 5) == 5                    # 不知道流量就不動


def test_config_requires_keys():
    with pytest.raises(SystemExit) as e:
        fd.load_config({"SHIOAJI_API_KEY": "k"})
    assert "SHIOAJI_SECRET_KEY" in str(e.value) and "k" not in str(e.value).replace("KEY", "")
    cfg = fd.load_config({"SHIOAJI_API_KEY": "k", "SHIOAJI_SECRET_KEY": "s", "FEED_URL": "wss://x/feed",
                          "FEED_TOKEN": "t", "INTERVAL": "10"})
    assert cfg["interval"] == 10 and cfg["universe_url"].endswith("intraday_universe.json")


def test_stale_snapshots_and_env_file(tmp_path):
    from datetime import date, timezone as tz
    today = date(2026, 10, 7)
    yday = datetime(2026, 10, 6, 13, 30, tzinfo=tz.utc).timestamp() * 1e9
    now = datetime(2026, 10, 7, 1, 0, 5, tzinfo=tz.utc).timestamp() * 1e9          # 台北 09:00:05
    assert not fd.is_today(SimpleNamespace(ts=yday), today)                          # 開盤前的快照還是昨天的
    assert fd.is_today(SimpleNamespace(ts=now), today)
    assert fd.is_today(SimpleNamespace(), today)                                     # 沒有時間欄位不擋
    assert fd.is_today(SimpleNamespace(ts=now / 1e6), today)                         # 單位是毫秒也認得
    assert not fd.is_today(SimpleNamespace(ts=yday / 1e3), today)                    # 微秒
    f = tmp_path / "feeder.env"
    f.write_text("SHIOAJI_API_KEY=a+b/c=\nFEED_URL=wss://x/feed\n# 註解\n", encoding="utf-8")
    assert fd.read_env_file(f) == {"SHIOAJI_API_KEY": "a+b/c=", "FEED_URL": "wss://x/feed"}
