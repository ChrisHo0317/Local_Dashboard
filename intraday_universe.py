"""
盤中強勢族群的「今日名單」（site/data/intraday_universe.json，每次產生頁面時重算）

盤中服務（intraday/worker.js，跑在 Cloudflare Workers）每天第一次執行時讀這份，
決定要向證交所查哪些股票；網站的盤中頁也用它把即時價量對回股票與族群。

    date      依據的交易日（最近一個有收盤的日子）
    codes     要追蹤的股票：近 20 日平均成交值 0.3 億以上＋自選股（不含 ETF）
    names、mk 名稱、市場（t 上市／o 上櫃，查證交所即時行情要用）
    avg       近 20 日平均成交值（億），算量比用
    groups    族群：[[名稱, 產業鏈, [成員在 codes 裡的序號]]]，細產業中至少 MIN_MEMBERS 檔在名單裡的
    yday      上一個交易日強勢紀錄裡「族群連動」的族群（盤中標「延續」）
    profile   盤中累積成交量占全天的比例，09:00 起每分鐘一個（0～270），算「到現在應該有多少量」
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

MIN_TURNOVER = 3e7
MIN_MEMBERS = 3
DAYS = 20
SESSION_MIN = 270        # 09:00～13:30

# 台股盤中累積成交量的大致比例（開盤與收盤最集中；13:25～13:30 收盤集合競價約占一成）。
# 先用經驗值；data/intraday/ 累積 5 天以上的盤中存檔後，改用實際的分時量（名單內累積成交值）。
PROFILE_POINTS = [(0, 0.0), (5, 0.10), (15, 0.19), (30, 0.28), (60, 0.40), (90, 0.49), (120, 0.57),
                  (150, 0.64), (180, 0.70), (210, 0.76), (240, 0.82), (265, 0.89), (266, 0.89),
                  (270, 1.0)]


ARCHIVE_DIR = Path(__file__).resolve().parent / "data" / "intraday"
CALIBRATE_MIN_DAYS = 5


def _archive_points() -> list[tuple[int, float]] | None:
    """盤中存檔（每 5 分鐘的名單內累積成交值）算出的實際量能曲線；不到 5 天就用經驗值。"""
    files = sorted(ARCHIVE_DIR.glob("*.json"))[-20:] if ARCHIVE_DIR.exists() else []
    by_min: dict[int, list[float]] = {}
    days = 0
    for f in files:
        try:
            tl = json.loads(f.read_text(encoding="utf-8")).get("timeline") or []
        except (OSError, ValueError):
            continue
        total = tl[-1]["tv"] if tl else 0
        if not total or len(tl) < 40:
            continue
        days += 1
        for row in tl:
            hh, mm = (row.get("t") or "0:0").split(":")[:2]
            m = (int(hh) - 9) * 60 + int(mm)
            if 0 < m < SESSION_MIN:
                by_min.setdefault(m, []).append(row["tv"] / total)
    if days < CALIBRATE_MIN_DAYS:
        return None
    pts = [(0, 0.0)] + [(m, sum(v) / len(v)) for m, v in sorted(by_min.items())] + [(SESSION_MIN, 1.0)]
    out, top = [], 0.0
    for m, v in pts:
        top = max(top, min(v, 1.0))          # 累積比例只會往上
        out.append((m, top))
    return out


def profile() -> list[float]:
    points = _archive_points() or PROFILE_POINTS
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    out = []
    for m in range(SESSION_MIN + 1):
        for k in range(1, len(xs)):
            if m <= xs[k]:
                a, b = xs[k - 1], xs[k]
                f = 0 if b == a else (m - a) / (b - a)
                out.append(round(ys[k - 1] + f * (ys[k] - ys[k - 1]), 4))
                break
    return out


def build(panel: pd.DataFrame, master: pd.DataFrame, watch_codes: set,
          tag_df: pd.DataFrame, strong_hist: pd.DataFrame | None = None) -> dict:
    days = sorted(panel["date"].unique())
    if not days:
        return {"date": "", "codes": [], "groups": []}
    recent = panel[panel["date"].isin(days[-DAYS:]) & ~panel["code"].str.startswith("00")]
    avg = recent.groupby("code")["turnover"].mean()
    codes = sorted(set(avg[avg >= MIN_TURNOVER].index) | (set(watch_codes) & set(avg.index)))
    info = master.set_index("code")
    index = {c: i for i, c in enumerate(codes)}

    groups = []
    if tag_df is not None and not tag_df.empty:
        part = tag_df[tag_df["code"].isin(index)]
        for tag, g in part.groupby("tag"):
            members = sorted({index[c] for c in g["code"]})
            if len(members) >= MIN_MEMBERS:
                groups.append([tag, g["chain"].iloc[0], members])
    groups.sort(key=lambda x: x[0])

    yday = []
    if strong_hist is not None and not strong_hist.empty:
        last = strong_hist[strong_hist["date"] == strong_hist["date"].max()]
        yday = sorted({g for g, linked in zip(last["group"], last["linked"]) if g and bool(linked)})

    tpe = timezone(timedelta(hours=8))
    return {
        "date": pd.Timestamp(days[-1]).strftime("%Y-%m-%d"),
        "built": datetime.now(tpe).strftime("%Y-%m-%d %H:%M"),
        "codes": codes,
        "names": [str(info["name"].get(c, "")) if c in info.index else "" for c in codes],
        "mk": ["o" if (info["market"].get(c) if c in info.index else "") == "tpex" else "t" for c in codes],
        "avg": [round(float(avg[c]) / 1e8, 3) for c in codes],
        "groups": groups,
        "yday": yday,
        "profile": profile(),
    }
