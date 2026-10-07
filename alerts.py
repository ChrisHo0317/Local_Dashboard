"""
自選股推播（Bark）

    python alerts.py            比對事件，有新的就推播
    python alerts.py --dry-run  只列出會推什麼，不送出、不記錄
    python alerts.py --test     送一則測試通知
    python alerts.py --failure 名稱   排程失敗時通知（workflow 的 if: failure() 步驟呼叫）

環境變數（GitHub Actions 的 Secrets／Variables）：
    BARK_KEY        Bark App 給的金鑰（Secret）。沒有就只記在執行紀錄，不送出
    BARK_SERVER     自架 Bark 伺服器的網址，預設 https://api.day.app
    ALERTS_ENABLED  設成 false 就完全不推播（Variable），預設開啟

事件（只看 watchlist.csv 裡「推播」為是的股票）：
    重大訊息         近 3 天的新重訊，每則一個通知，時效性通知
    月營收公布       最新一個月的營收進來時
    法人連買／連賣   外資或投信連續 3 個交易日同方向（第 3 天那次才推）
    站上／跌破季線   收盤價穿越 60 日均線（還原權值後的價格）
    注意股／處置股   新列入時（處置是時效性通知）
除了重訊，其他事件彙整成一則。選股條件命中不推播（條件尚未回測）。

已推過的事件記在 data/alerts_sent.csv，同一件事只推一次。
第一次執行（還沒有這個檔）只記錄、不推播，免得一開始就把舊事件全部推一遍。
"""
import argparse
import csv
import logging
import os
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
from curl_cffi import requests as cffi_requests

import intel_data
import market_data as md
from fundamentals import load_announce, load_revenue
from watchlist import load_watchlist

BASE_DIR = Path(__file__).resolve().parent
SENT_PATH = BASE_DIR / "data" / "alerts_sent.csv"
SITE_URL = "https://chrisho0317.github.io/Local_Dashboard/"
# 通知圖示：和網站 App 圖示（加到 iPhone 主畫面的那個 apple-touch-icon）同一張；Bark 需要 iOS 15 以上
ICON_URL = SITE_URL + "icon-180.png"
GROUP = "台股情報"
KEEP_DAYS = 120

log = logging.getLogger("alerts")


def enabled() -> bool:
    return os.environ.get("ALERTS_ENABLED", "true").strip().lower() not in (
        "false", "0", "no", "off", "否")


def load_sent() -> dict:
    if not SENT_PATH.exists():
        return {}
    with SENT_PATH.open(encoding="utf-8") as f:
        return {r["id"]: r["sent_at"] for r in csv.DictReader(f)}


def save_sent(sent: dict, today: str) -> None:
    cutoff = (pd.Timestamp(today) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    rows = sorted((k, v) for k, v in sent.items() if v >= cutoff)
    SENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SENT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "sent_at"])
        w.writerows(rows)


def _roc_to_iso(v: str) -> str:
    v = str(v)
    if len(v) == 7 and v.isdigit():
        return f"{int(v[:3]) + 1911}-{v[3:5]}-{v[5:]}"
    return ""


def announce_events(codes: set, names: dict, today: pd.Timestamp) -> list[dict]:
    ann = load_announce()
    if ann.empty:
        return []
    ann = ann[ann["code"].isin(codes)].copy()
    ann["iso"] = ann["date"].map(_roc_to_iso)
    since = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    ann = ann[ann["iso"] >= since]
    out = []
    for _, r in ann.iterrows():
        out.append({
            "id": f"ann|{r['code']}|{r['date']}|{r['time']}|{r['subject'][:40]}",
            "code": r["code"], "urgent": True,
            "title": f"【重訊】{r['code']} {names.get(r['code'], r['name'])}",
            "body": r["subject"],
        })
    return out


def revenue_events(codes: set, names: dict) -> list[dict]:
    rev = load_revenue()
    if rev.empty:
        return []
    latest = rev[["year", "month"]].drop_duplicates().sort_values(["year", "month"]).iloc[-1]
    y, m = int(latest["year"]), int(latest["month"])
    cur = rev[(rev["year"] == y) & (rev["month"] == m) & rev["code"].isin(codes)]
    prev = rev[(rev["year"] == y - 1) & (rev["month"] == m)].set_index("code")["revenue"]
    out = []
    for _, r in cur.iterrows():
        ly = prev.get(r["code"])
        yoy = f"，年增 {(r['revenue'] / ly - 1) * 100:+.1f}%" if ly and ly > 0 else ""
        out.append({"id": f"rev|{r['code']}|{y}-{m:02d}", "code": r["code"], "urgent": False,
                    "line": f"{r['code']} {names.get(r['code'], '')} {m} 月營收 "
                            f"{r['revenue'] / 1e5:,.2f} 億{yoy}"})
    return out


def flow_events(panel: pd.DataFrame, codes: set, names: dict) -> list[dict]:
    if panel.empty:
        return []
    days = intel_data.trading_days(panel)
    if len(days) < 4:
        return []
    latest = days[-1]
    out = []
    recent = panel[panel["code"].isin(codes) & panel["date"].isin(days[-4:])]
    for code, g in recent.groupby("code"):
        g = g.set_index("date").reindex(days[-4:])
        for col, label in (("foreign", "外資"), ("trust", "投信")):
            v = g[col].values
            if pd.isna(v).any():
                continue
            last3, before = v[-3:], v[0]
            for sign, word in ((1, "連買"), (-1, "連賣")):
                if all(x * sign > 0 for x in last3) and not before * sign > 0:
                    total = abs(sum(last3)) / 1000
                    out.append({"id": f"flow|{code}|{col}{word}|{latest.date()}", "code": code,
                                "urgent": False,
                                "line": f"{code} {names.get(code, '')} {label}{word} 3 日，"
                                        f"共 {total:,.0f} 張"})
    return out


def ma_events(panel: pd.DataFrame, codes: set, names: dict) -> list[dict]:
    if panel.empty:
        return []
    out = []
    latest = panel["date"].max()
    for code, g in panel[panel["code"].isin(codes)].groupby("code"):
        close = g.set_index("date")["close"].dropna()
        if len(close) < 62 or close.index[-1] != latest:
            continue
        ma = close.rolling(60).mean()
        prev_above = close.iloc[-2] > ma.iloc[-2]
        now_above = close.iloc[-1] > ma.iloc[-1]
        if prev_above == now_above:
            continue
        word = "站上" if now_above else "跌破"
        out.append({"id": f"ma60|{code}|{word}|{latest.date()}", "code": code, "urgent": False,
                    "line": f"{code} {names.get(code, '')} 收盤 {close.iloc[-1]:,.2f} {word}季線"
                            f"（{ma.iloc[-1]:,.2f}）"})
    return out


def flag_events(codes: set, names: dict, today: pd.Timestamp) -> list[dict]:
    """近 3 天新列入的注意股、處置股。處置會限制交易（分盤撮合、預收款券），單獨推。"""
    flags = md.load_flags()
    if flags.empty:
        return []
    since = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    out = []
    for r in flags[(flags["code"].isin(codes)) & (flags["date"] >= since)].itertuples():
        name = names.get(r.code, r.name)
        if r.kind == "處置":
            out.append({"id": f"flag|{r.code}|處置|{r.start}", "code": r.code, "urgent": True,
                        "title": f"處置股：{r.code} {name}",
                        "body": f"{r.start} ～ {r.end}　{r.detail}"[:180]})
        else:
            out.append({"id": f"flag|{r.code}|注意|{r.date}", "code": r.code, "urgent": False,
                        "line": f"{r.code} {name} 列入注意股：{r.detail[:40]}"})
    return out


def collect() -> list[dict]:
    watch = [w for w in load_watchlist() if w["push"]]
    return watch_events({w["code"] for w in watch})


def watch_events(codes: set) -> list[dict]:
    """指定股票的所有事件（推播只用「推播＝是」的；首頁的自選股警示用全部）。"""
    if not codes:
        return []
    master = intel_data.stock_master()
    names = dict(zip(master["code"], master["name"]))
    panel = intel_data.daily_panel(days=80)
    today = pd.Timestamp(intel_data.today_taipei())
    return (announce_events(codes, names, today) + revenue_events(codes, names)
            + flow_events(panel, codes, names) + ma_events(panel, codes, names)
            + flag_events(codes, names, today))


def messages(events: list[dict]) -> list[dict]:
    """重訊各自一則；其他彙整成一則。"""
    msgs = []
    for e in events:
        if e["urgent"]:
            msgs.append({"title": e["title"], "body": e["body"], "level": "timeSensitive",
                         "url": f"{SITE_URL}?stock={e['code']}", "ids": [e["id"]]})
    rest = [e for e in events if not e["urgent"]]
    if rest:
        msgs.append({"title": f"台股情報：自選股 {len(rest)} 則事件",
                     "body": "\n".join(e["line"] for e in rest), "level": "active",
                     "url": SITE_URL, "ids": [e["id"] for e in rest]})
    return msgs


def send(msg: dict, key: str, server: str) -> bool:
    try:
        resp = cffi_requests.post(
            server.rstrip("/") + "/push",
            json={"device_key": key, "title": msg["title"], "body": msg["body"],
                  "group": GROUP, "level": msg.get("level", "active"),
                  "url": msg.get("url", SITE_URL), "icon": msg.get("icon", ICON_URL)},
            timeout=30)
        ok = resp.status_code == 200 and resp.json().get("code") == 200
        if not ok:
            log.error(f"Bark 回應非預期：{resp.status_code} {resp.text[:200]}")
        return ok
    except Exception as e:
        log.error(f"Bark 送出失敗：{e}")
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--failure", metavar="NAME")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    key = os.environ.get("BARK_KEY", "").strip()
    server = os.environ.get("BARK_SERVER", "").strip() or "https://api.day.app"

    if args.failure:
        # 排程失敗：不看 ALERTS_ENABLED，沒有金鑰就只記在執行紀錄
        run_url = "{}/{}/actions/runs/{}".format(os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
                                                 os.environ.get("GITHUB_REPOSITORY", ""),
                                                 os.environ.get("GITHUB_RUN_ID", ""))
        log.error(f"排程失敗：{args.failure}")
        if not key:
            return 0
        send({"title": "台股情報：排程失敗", "body": f"{args.failure} 執行失敗，點開看執行紀錄",
              "level": "timeSensitive", "url": run_url}, key, server)
        return 0

    if args.test:
        if not key:
            log.error("沒有設定 BARK_KEY，無法送出測試通知")
            return 1
        ok = send({"title": "台股情報：測試通知", "body": "收到這則代表 Bark 推播設定成功。",
                   "level": "active", "url": SITE_URL}, key, server)
        log.info("測試通知已送出" if ok else "測試通知送出失敗")
        return 0 if ok else 1

    if not enabled() and not args.dry_run:
        log.info("ALERTS_ENABLED 已關閉，不推播")
        return 0

    events = collect()
    today = intel_data.today_taipei().isoformat()
    sent = load_sent()
    pending = [e for e in events if e["id"] not in sent]
    log.info(f"自選股事件 {len(events)} 則，未推過 {len(pending)} 則")

    if args.dry_run:
        for m in messages(pending):
            log.info(f"[預覽] {m['title']}｜{m['body']}")
        return 0
    if not key:
        for m in messages(pending):
            log.info(f"[未設定 BARK_KEY，略過] {m['title']}")
        return 0

    # 剛開始推播的自選股（第一次設定 BARK_KEY、或新加進清單）：現有事件只記錄、不推，
    # 免得一開始就收到一堆舊消息。每檔記一個 watch|代號，每次都更新日期，還在清單上就不會被清掉。
    # （不能只看 alerts_sent.csv 存不存在：盤前盤後摘要、資料品質的推播也會建立這個檔）
    codes = {w["code"] for w in load_watchlist() if w["push"]}
    new = {c for c in codes if f"watch|{c}" not in sent}
    quiet = [e for e in pending if e["code"] in new]
    fresh = [e for e in pending if e["code"] not in new]
    for e in quiet:
        sent[e["id"]] = today
    for c in codes:
        sent[f"watch|{c}"] = today
    if new:
        log.info(f"新開始推播的自選股 {len(new)} 檔：記錄 {len(quiet)} 則現有事件，不推播")

    for m in messages(fresh):
        if send(m, key, server):
            for i in m["ids"]:
                sent[i] = today
    save_sent(sent, today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
