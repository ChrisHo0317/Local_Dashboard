"""
盤中即時行情程式：永豐金 Shioaji → Cloudflare 即時轉播站（intraday/livehub.js）

跑在雲端小主機上，安裝與金鑰由 .github/workflows/feeder.yml 部署（金鑰存在 GitHub Secrets，部署時寫進 feeder.env）。
平日 08:45 由 systemd timer 啟動：
  1. 讀今日名單（網站的 data/intraday_universe.json，和盤中服務、網站用同一份）
  2. 用只開「行情」權限的 API Key 登入（不需要憑證、不能下單）
  3. 09:00～13:35 每 INTERVAL 秒查一次名單內全部股票的快照（一次最多 500 檔），
     只把有變動的送到轉播站；大約每分鐘送一次全部，沒變動時送心跳
  4. Shioaji 每日流量快用完時自動放慢（5 → 10 → 20 秒）
  5. 13:36 送完最後一份就結束；開盤後 5 分鐘快照都還是之前的（休市）也結束；週末或收盤後啟動會直接結束

    python feeder.py                        正式執行（設定由 systemd 的 EnvironmentFile 給）
    python feeder.py --check --env feeder.env  登入測試：連一次轉播站、登入、查一檔快照，印結果就結束（不印金鑰）

開盤前還沒成交的股票，Shioaji 快照仍是前一天的價量：快照時間不是今天的就不送，網站沿用每分鐘資料。
轉播站拒絕 FEED_TOKEN 時直接結束、不重試（免得 systemd 一直重啟、一直登入永豐金）。

送出的訊息：{type:'full'|'delta'|'hb', date:'20261007', t:'11:36:05', ts:毫秒,
            q:{代號:[成交價, 累計量(張), 買價, 賣價, 成交金額(億), 內外盤 1=外盤 2=內盤 0=無]}}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    TPE = ZoneInfo("Asia/Taipei")
except Exception:                     # 沒有時區資料庫（例如 Windows 沒裝 tzdata）：台灣沒有日光節約時間，固定 +8
    TPE = timezone(timedelta(hours=8))
OPEN, CLOSE = (9, 0), (13, 36)        # 13:30 收盤集合競價的結果要幾十秒才出來
BATCH = 500                           # Shioaji 快照一次最多 500 檔
FULL_EVERY_SEC = 60                   # 大約每分鐘送一次全部
CLOSED_AFTER_MIN = 5                  # 開盤後 5 分鐘都沒有任何變化，當作休市
MAX_FAILS = 12                        # 連續查不到快照這麼多次就結束（systemd 30 秒後重新登入）
INTERVALS = (5, 10, 20)               # 流量不夠時一級一級放慢

log = logging.getLogger("feeder")


# ── 純計算（tests/test_feeder.py 測這些，不需要 shioaji、websockets）──

def _num(v, nd=2):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0
    return round(v, nd) if v == v else 0


def row(s) -> list:
    """一筆 Shioaji 快照 → [成交價, 累計量(張), 買價, 賣價, 成交金額(億), 內外盤]"""
    tt = getattr(s, "tick_type", None)
    tt = {"Buy": 1, "Sell": 2}.get(str(getattr(tt, "value", tt)), 0)
    return [_num(s.close), int(_num(getattr(s, "total_volume", 0), 0)), _num(getattr(s, "buy_price", 0)),
            _num(getattr(s, "sell_price", 0)), _num(_num(getattr(s, "total_amount", 0), 0) / 1e8, 3), tt]


def is_today(s, today) -> bool:
    """快照時間（奈秒）是不是今天：Shioaji 的 ts 不論當成 UTC 或台北時間，前一天的日期都會比今天早"""
    ts = getattr(s, "ts", None)
    if not ts:
        return True                                     # 沒有時間欄位就不擋
    ts = float(ts)
    sec = ts / 1e9 if ts > 1e17 else ts / 1e6 if ts > 1e14 else ts / 1e3 if ts > 1e11 else ts
    return datetime.fromtimestamp(sec, tz=timezone.utc).date() >= today


def diff(prev: dict, cur: dict) -> dict:
    """和上一份比，有變的代號"""
    return {c: v for c, v in cur.items() if prev.get(c) != v}


def message(kind: str, now: datetime, q: dict | None = None) -> str:
    m = {"type": kind, "date": now.strftime("%Y%m%d"), "t": now.strftime("%H:%M:%S"), "ts": int(now.timestamp() * 1000)}
    if q is not None:
        m["q"] = q
    return json.dumps(m, ensure_ascii=False, separators=(",", ":"))


def at(now: datetime, hm: tuple) -> datetime:
    return now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)


def pace(used: float, remaining: float, rounds_done: int, rounds_left: int, interval: int) -> int:
    """依 Shioaji 剩下的流量決定間隔：照現在的速度跑到收盤會超過剩下流量的八成，就放慢一級。
    used／rounds_done 是「這段期間」用掉的流量與輪數（兩次檢查的差），不要用帳號整天的總量"""
    if rounds_done <= 0 or remaining is None or used is None:
        return interval
    per_round = used / rounds_done
    if per_round * rounds_left > remaining * 0.8:
        slower = [i for i in INTERVALS if i > interval]
        return slower[0] if slower else interval
    return interval


def read_env_file(path: str) -> dict:
    """KEY=value 一行一個（部署流程寫的 feeder.env）；不經過 shell，值裡有特殊字元也沒關係"""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def load_config(env=os.environ) -> dict:
    need = ["SHIOAJI_API_KEY", "SHIOAJI_SECRET_KEY", "FEED_URL", "FEED_TOKEN"]
    missing = [k for k in need if not env.get(k)]
    if missing:
        raise SystemExit("feeder.env 缺少：" + "、".join(missing))
    return {"api_key": env["SHIOAJI_API_KEY"], "secret_key": env["SHIOAJI_SECRET_KEY"],
            "feed_url": env["FEED_URL"], "feed_token": env["FEED_TOKEN"],
            "universe_url": env.get("UNIVERSE_URL",
                                    "https://chrisho0317.github.io/Local_Dashboard/data/intraday_universe.json"),
            "interval": int(env.get("INTERVAL", INTERVALS[0]))}


# ── 連外（需要 shioaji、websockets）──

def load_codes(url: str) -> list[str]:
    with urllib.request.urlopen(url + "?t=" + str(int(time.time())), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))["codes"]


def login(cfg: dict):
    """Shioaji 1.7：login(api_key, secret_key, subscribe_trade, …)，合約另外用 fetch_contracts 下載"""
    import shioaji as sj
    api = sj.Shioaji()
    api.login(api_key=cfg["api_key"], secret_key=cfg["secret_key"], subscribe_trade=False)
    api.fetch_contracts(contract_download=True)
    return api


def contracts_for(api, codes: list[str]) -> list:
    stocks = api.Contracts.Stocks
    out = []
    for c in codes:
        try:
            k = stocks.get(c)
        except Exception:
            k = None
        if k is not None:
            out.append(k)
    return out


def snapshots(api, contracts: list, today=None):
    """(今天的快照 {代號: row}, 收到幾筆)；收到但全部不是今天＝休市或還沒開盤"""
    today = today or datetime.now(TPE).date()
    cur, raw = {}, 0
    for i in range(0, len(contracts), BATCH):
        for s in api.snapshots(contracts[i:i + BATCH]):
            raw += 1
            if is_today(s, today):
                cur[s.code] = row(s)
    return cur, raw


def usage(api):
    """(帳號今天已用 bytes, 剩下 bytes)；查不到就回 (None, None)"""
    try:
        u = api.usage()
        return float(u.bytes), float(u.remaining_bytes)
    except Exception:
        return None, None


def _connect(url: str, token: str):
    from websockets.asyncio.client import connect      # websockets 14 以後的寫法
    return connect(url, additional_headers={"Authorization": "Bearer " + token}, ping_interval=20, max_size=2 ** 22)


async def run(cfg: dict, clock=lambda: datetime.now(TPE)) -> int:
    from websockets.exceptions import InvalidStatus
    try:
        return await _run(cfg, clock)
    except InvalidStatus as e:
        code = e.response.status_code
        if code in (401, 403):
            log.error(f"轉播站拒絕連線（{code}）：FEED_TOKEN 和 Cloudflare 那邊不一樣，"
                      "請確認 GitHub Secret FEED_TOKEN 並重跑 Deploy intraday worker 與 Deploy feeder；今天不再重試")
            return 0
        raise


async def _run(cfg: dict, clock) -> int:
    now = clock()
    if now.weekday() >= 5 or now >= at(now, CLOSE):
        log.info("不是盤中（週末或已經收盤），不跑")
        return 0
    codes = load_codes(cfg["universe_url"])
    loop = asyncio.get_running_loop()
    api = contracts = None
    interval, prev, last_full, rounds, fails = cfg["interval"], {}, 0.0, 0, 0
    stale_since = None                                  # 收到快照但全部不是今天的開始時間（判斷休市）
    mark = None                                         # 上一次看流量時的 (已用 bytes, 輪數)
    from websockets.exceptions import ConnectionClosed
    try:
        async for ws in _connect(cfg["feed_url"], cfg["feed_token"]):
            last_full = 0.0                             # 連上（或重連）先送一次全部
            try:
                if api is None:                         # 轉播站連得上才登入永豐金
                    api = await loop.run_in_executor(None, login, cfg)
                    contracts = contracts_for(api, codes)
                    log.info(f"登入成功；名單 {len(codes)} 檔，找得到合約 {len(contracts)} 檔")
                    wait = (at(clock(), OPEN) - clock()).total_seconds()
                    if wait > 0:
                        log.info(f"等到 09:00（{int(wait)} 秒）")
                        await asyncio.sleep(wait)
                while True:
                    t0 = time.monotonic()
                    now = clock()
                    if now >= at(now, CLOSE):
                        await ws.send(message("full", now, prev))
                        log.info(f"收盤，共 {rounds} 輪；結束")
                        return 0
                    try:
                        cur, raw = await loop.run_in_executor(None, snapshots, api, contracts, now.date())
                    except Exception as e:              # 查詢太頻繁、連線中斷：等下一輪再試
                        cur, raw = {}, 0
                        log.warning(f"快照查詢失敗：{e.__class__.__name__}：{str(e)[:120]}")
                    if raw and not cur:                 # 收到了但全部是之前的：還沒有人成交，或今天休市
                        stale_since = stale_since or now
                        if now - stale_since >= timedelta(minutes=CLOSED_AFTER_MIN) and now >= at(now, OPEN):
                            log.info(f"開盤後 {CLOSED_AFTER_MIN} 分鐘快照都不是今天的，今天休市；結束")
                            return 0
                    else:
                        stale_since = None
                    if not cur:                         # 查不到、或被限流回空：算失敗
                        fails += 1
                        if fails >= MAX_FAILS:
                            log.error("連續查不到快照，結束（systemd 會重新啟動並重新登入）")
                            return 1
                        await asyncio.sleep(interval)
                        continue
                    fails = 0
                    if t0 - last_full >= FULL_EVERY_SEC:
                        await ws.send(message("full", now, cur))
                        last_full = t0
                    else:
                        changed = diff(prev, cur)
                        await ws.send(message("delta", now, changed) if changed else message("hb", now))
                    prev = cur
                    rounds += 1
                    if rounds % 60 == 0:                # 大約每 5 分鐘看一次流量（用這 60 輪的差值估）
                        used, left = await loop.run_in_executor(None, usage, api)
                        if used is not None and mark is not None:
                            rest = max(0, (at(now, CLOSE) - now).total_seconds() / interval)
                            new = pace(used - mark[0], left, rounds - mark[1], int(rest), interval)
                            if new != interval:
                                log.warning(f"Shioaji 流量剩 {left / 1e6:.0f} MB，間隔 {interval} → {new} 秒")
                                interval = new
                        mark = (used, rounds) if used is not None else mark
                    await asyncio.sleep(max(0.0, interval - (time.monotonic() - t0)))
            except ConnectionClosed as e:
                code = getattr(e.rcvd, "code", None)
                # 4000＝另一個行情程式連上了（例如部署時的登入測試）：等 30 秒再連，免得兩邊一直互踢
                wait = 30 if code == 4000 else 2
                log.warning(f"轉播站斷線（{code or '—'}），{wait} 秒後重連")
                await asyncio.sleep(wait)
                continue
    finally:
        if api is not None:
            try:
                api.logout()
            except Exception:
                pass
    return 0


async def check(cfg: dict) -> int:
    """登入測試：不印金鑰，只印結果"""
    ok = True
    try:
        async with _connect(cfg["feed_url"], cfg["feed_token"]) as ws:
            await ws.send(message("hb", datetime.now(TPE)))
        print("轉播站連線成功")
    except Exception as e:
        ok = False
        print(f"轉播站連線失敗（FEED_TOKEN 或網址不對，或 Cloudflare 還沒部署轉播站）：{e.__class__.__name__}：{str(e)[:160]}")
    try:
        api = login(cfg)
        k = contracts_for(api, ["2330", "2317"])
        snap, raw = snapshots(api, k)
        used, left = usage(api)
        print(f"永豐金登入成功；找得到合約 {len(k)}/2 檔，快照 {raw} 筆（今天的 {len(snap)} 筆）；今日流量已用 "
              f"{'—' if used is None else f'{used / 1e6:.1f} MB'}、剩 {'—' if left is None else f'{left / 1e6:.0f} MB'}")
        api.logout()
    except Exception as e:
        ok = False
        print(f"永豐金登入失敗：{e.__class__.__name__}：{str(e)[:200]}")
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true", help="只做登入與連線測試")
    p.add_argument("--env", help="從這個檔案讀設定（KEY=value），不用先 export")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config({**os.environ, **read_env_file(a.env)} if a.env else os.environ)
    return asyncio.run(check(cfg) if a.check else run(cfg))


if __name__ == "__main__":
    sys.exit(main())
