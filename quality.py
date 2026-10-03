"""
資料品質檢查（python quality.py；排程每次最後跑）

    行情是否停更、最新一天各市場的檔數、零價還沒修好的筆數、
    找不到權值事件的大跳動、歷史回補進度、新聞與強勢股新聞多久沒更新、金鑰有沒有設定

結果寫到 data/quality.json（設定頁與首頁顯示）。有「錯誤」等級的問題就用 Bark 推播，
同一天同一個問題只推一次（記在 data/alerts_sent.csv，和自選股推播共用）。
"""
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import intel_data
import market_data as md

BASE_DIR = Path(__file__).resolve().parent
OUT_PATH = BASE_DIR / "data" / "quality.json"
NEWS_CSV = BASE_DIR / "data" / "news_articles.csv"
STOCK_NEWS = BASE_DIR / "data" / "stock_news.json"
CLOSE_READY = 17      # 台北時間幾點以後，當天的收盤行情應該已經進來

log = logging.getLogger("quality")


def _check(cid: str, level: str, title: str, detail: str = "") -> dict:
    return {"id": cid, "level": level, "title": title, "detail": detail}


def trading_gap(latest, now: datetime, closed: set) -> int:
    """latest 之後到 now 為止，應該有資料卻沒有的交易日數（週末、休市不算；今天要過收盤才算）。"""
    gap, day = 0, latest + timedelta(days=1)
    while day <= now.date():
        if day.weekday() < 5 and day.isoformat() not in closed:
            if day < now.date() or now.hour >= CLOSE_READY:
                gap += 1
        day += timedelta(days=1)
    return gap


def run(now: datetime | None = None) -> dict:
    now = now or pd.Timestamp.now(tz="Asia/Taipei").to_pydatetime().replace(tzinfo=None)
    checks = []
    days = md.dates()
    closed = set()
    closed_path = md.MARKET_DIR / "closed.txt"
    if closed_path.exists():
        closed = {x.strip() for x in closed_path.read_text(encoding="utf-8").split() if x.strip()}

    # 行情停更
    if not days:
        checks.append(_check("stale", "error", "沒有任何全市場日資料"))
    else:
        latest = days[-1]
        gap = trading_gap(latest, now, closed)
        if gap >= 2:
            checks.append(_check("stale", "error", f"行情停在 {latest}，已經缺 {gap} 個交易日",
                                 "請到 GitHub Actions 看 Update market data 的執行紀錄"))
        elif gap == 1:
            checks.append(_check("stale", "warn", f"今天的收盤行情還沒進來（最新 {latest}）",
                                 "官方通常 17:30 前公布；排程晚一點會再補"))
        else:
            checks.append(_check("stale", "ok", f"行情最新到 {latest}"))

        # 最新一天各市場的檔數（和近 20 天的中位數比）
        recent = md.load_days(days[-21:])
        if not recent.empty:
            counts = recent.dropna(subset=["close"]).groupby(["date", "market"]).size().unstack(fill_value=0)
            last = counts.iloc[-1]
            typical = counts.iloc[:-1].median() if len(counts) > 1 else last
            short = [f"{'上市' if m == 'twse' else '上櫃'} {int(last.get(m, 0))} 檔（平常 {int(typical.get(m, 0))}）"
                     for m in ("twse", "tpex") if last.get(m, 0) < typical.get(m, 0) * 0.9]
            checks.append(_check("coverage", "warn" if short else "ok",
                                 "最新一天有市場資料不完整" if short else "最新一天兩個市場的檔數正常",
                                 "、".join(short)))

    # 零價、未解釋跳動（近 60 個交易日）
    panel = intel_data.daily_panel(60)
    if not panel.empty:
        raw = intel_data.daily_panel(60, adjusted=False)
        # 只有零股或鉅額交易的日子官方本來就沒有收盤價，成交至少 1 張才算缺
        zero = int((raw["raw_close"].isna() & (raw["volume"] >= 1000)).sum())
        checks.append(_check("zero", "warn" if zero else "ok",
                             f"近 60 日有 {zero} 筆成交 1 張以上卻沒有收盤價" if zero else "近 60 日沒有缺收盤價",
                             "歷史回補會逐步修正" if zero else ""))
        jumps = panel[panel["jump"]]
        if len(jumps):
            sample = "、".join(f"{r.code}（{r.date:%m/%d}）" for r in jumps.tail(8).itertuples())
            checks.append(_check("jump", "warn",
                                 f"近 60 日有 {len(jumps)} 次大跳動找不到除權息或減資紀錄",
                                 f"這些天的報酬先記為 0：{sample}"))
        else:
            checks.append(_check("jump", "ok", "近 60 日的大跳動都對得到權值事件"))

    # 歷史回補進度
    base_path = md.MARKET_DIR / "history_base.parquet"
    if base_path.exists():
        base_days = pd.read_parquet(base_path, columns=["date"])["date"].unique()
        left = sum(1 for d in base_days if not md.patch_path(pd.Timestamp(d).date(), "tpex").exists())
        checks.append(_check("backfill", "info" if left else "ok",
                             f"上櫃歷史回補還剩 {left} 天" if left else "歷史回補完成",
                             "每次排程補一批，補完後上櫃的除權息也會還原" if left else ""))

    # 新聞與強勢股新聞
    if NEWS_CSV.exists():
        news = pd.read_csv(NEWS_CSV, usecols=["published"])
        last = pd.to_datetime(news["published"], errors="coerce", utc=True).max()
        if pd.notna(last):
            hours = (pd.Timestamp.now(tz="UTC") - last).total_seconds() / 3600
            checks.append(_check("news", "warn" if hours > 6 else "ok",
                                 f"新聞 {hours:.0f} 小時沒有更新" if hours > 6 else "新聞正常更新"))
    try:
        sn = json.loads(STOCK_NEWS.read_text(encoding="utf-8"))
        gen = pd.Timestamp(sn.get("generated"))
        age = (pd.Timestamp(now) - gen).total_seconds() / 86400
        claude = bool(sn.get("model"))
        checks.append(_check("stocknews", "warn" if age > 3 else ("info" if not claude else "ok"),
                             f"強勢股新聞 {age:.0f} 天沒有更新" if age > 3 else
                             ("強勢股新聞以關鍵字挑選（沒有設定 ANTHROPIC_API_KEY）" if not claude
                              else "強勢股新聞由 Claude 整理")))
    except (OSError, ValueError):
        pass

    # 金鑰（只有在 GitHub Actions 裡看得到）
    if os.environ.get("GITHUB_ACTIONS"):
        missing = [k for k in ("BARK_KEY", "ANTHROPIC_API_KEY") if not os.environ.get(k)]
        if missing:
            checks.append(_check("secrets", "info", "還沒設定：" + "、".join(missing),
                                 "GitHub → Settings → Secrets and variables → Actions"))

    order = {"error": 3, "warn": 2, "info": 1, "ok": 0}
    worst = max((order[c["level"]] for c in checks), default=0)
    return {"generated": now.strftime("%Y-%m-%d %H:%M"),
            "status": {3: "error", 2: "warn", 1: "ok", 0: "ok"}[worst],
            "checks": sorted(checks, key=lambda c: -order[c["level"]])}


def notify(report: dict) -> int:
    """錯誤等級的問題推播（同一天同一個問題只推一次）。"""
    import alerts
    errors = [c for c in report["checks"] if c["level"] == "error"]
    key = os.environ.get("BARK_KEY", "").strip()
    if not errors or not key or not alerts.enabled():
        return 0
    today = report["generated"][:10]
    sent = alerts.load_sent()
    fresh = [c for c in errors if f"quality|{c['id']}|{today}" not in sent]
    if not fresh:
        return 0
    server = os.environ.get("BARK_SERVER", "").strip() or "https://api.day.app"
    ok = alerts.send({"title": "台股情報：資料異常",
                      "body": "\n".join(c["title"] for c in fresh), "level": "timeSensitive",
                      "url": alerts.SITE_URL}, key, server)
    if ok:
        for c in fresh:
            sent[f"quality|{c['id']}|{today}"] = today
        alerts.save_sent(sent, today)
    return int(ok)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = run()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
    text = json.dumps(report, ensure_ascii=False, indent=1)
    # 只有內容變了才寫（generated 每次都不同，比對時拿掉）
    strip = lambda t: json.dumps({k: v for k, v in json.loads(t).items() if k != "generated"},
                                 ensure_ascii=False) if t else ""
    if strip(old) != strip(text):
        OUT_PATH.write_text(text, encoding="utf-8", newline="\n")
    for c in report["checks"]:
        log.info(f"[{c['level']}] {c['title']} {c['detail']}")
    notify(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
