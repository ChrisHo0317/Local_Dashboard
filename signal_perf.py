"""
訊號績效：歷史回測＋往後追蹤

每個訊號用同一套算法：訊號「新出現」（前一天不在名單、這天進榜）的隔天開盤買進，
持有 5／10／20 個交易日、以那天收盤計算報酬。價格已還原權值，扣掉來回成本
0.585%（手續費 0.1425% × 2＋證交稅 0.3%）。
對照組「市場平均」：同一天、同樣隔天開盤進場，均量 1 億以上股票的等權平均報酬。
超額報酬＝訊號報酬 − 市場平均。

    歷史回測（用過去的資料重算，只用當時就知道的資訊）
        strong10      強勢股前 10：近 20 日上漲、近 5 日漲得比前 5 日多、均量 1 億以上，依加速度
        strong30      強勢股前 30
        extreme       最極端 10% 而且越來越強（強勢股頁的「最極端 10%」）
        trust_start   投信開始連買（連買到第 3 天、之前 20 日沒買）
        rev_accel     營收成長加速（假設每月 10 日公布上個月營收，11 日起算）
    往後追蹤（需要當天的新聞或資料，從開始記錄那天起累積）
        linked        族群連動的強勢股（強勢紀錄）
        solo          不是族群連動的強勢股
        value_yield   低估值高殖利率（每天記錄命中名單）
        chip_conc     籌碼集中

注意：同一檔可能短期內反覆進出名單，事件之間會重疊，t 值會偏樂觀；回測沒有考慮滑價、
漲跌停買不到、下市股票，結果只能當參考。
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "data" / "signal_log.csv"

HORIZONS = [5, 10, 20]
COST = 0.585                # 來回成本（%）
LIQUID = 1e8                # 均量門檻（元），與強勢股頁預設「1 億↑」一致
EXTREME = 0.10
MIN_N = 30                  # 次數少於這個不下結論

SIGNALS = [
    ("strong10", "強勢股前 10", "回測", "近 20 日上漲、近 5 日漲得比前 5 日多、均量 1 億以上，依加速度排前 10"),
    ("strong30", "強勢股前 30", "回測", "同上，前 30"),
    ("extreme", "最極端 10% 且越來越強", "回測", "強度與加速度離中心最遠的 10%，再挑越來越強的"),
    ("trust_start", "投信開始連買", "回測", "投信連買第 3 天，而且之前 20 日累計沒有買"),
    ("rev_accel", "營收成長加速", "回測", "近 6 個月營收都年增，而且近 3 月年增率高於前 3 月（每月 11 日起算）"),
    ("linked", "族群連動的強勢股", "追蹤", "強勢紀錄裡判定為族群連動的（自開始記錄起）"),
    ("solo", "個股行情的強勢股", "追蹤", "強勢紀錄裡不是族群連動的"),
    ("value_yield", "低估值高殖利率", "追蹤", "選股條件，每天記錄命中名單"),
    ("chip_conc", "籌碼集中", "追蹤", "選股條件，每天記錄命中名單"),
]


# ── 矩陣 ────────────────────────────────────────────────────
def matrices(panel: pd.DataFrame) -> dict:
    """日期 × 代號：還原後收盤、開盤、20 日均成交值、投信買賣超（ETF 不列入）。"""
    p = panel[~panel["code"].str.startswith("00")]
    piv = lambda col: p.pivot_table(index="date", columns="code", values=col).sort_index()
    close = piv("close")
    dates = close.index
    out = {"close": close.ffill(), "open": piv("open").reindex(index=dates, columns=close.columns),
           "trust": piv("trust").reindex(index=dates, columns=close.columns)}
    tv = piv("turnover").reindex(index=dates, columns=close.columns)
    out["tv20"] = tv.rolling(20, min_periods=15).mean()
    return out


def forward_returns(m: dict) -> dict:
    """{h: 報酬矩陣（%，未扣成本）}：隔天開盤進場、第 h 天收盤出場。"""
    entry = m["open"].shift(-1)
    entry = entry.where(entry > 0, m["close"].shift(-1))     # 沒有開盤價就用隔天收盤
    return {h: (m["close"].shift(-h) / entry - 1) * 100 for h in HORIZONS}


def benchmark(fwd: dict, m: dict) -> dict:
    """{h: 每天的市場平均報酬}（均量 1 億以上等權）。"""
    liquid = m["tv20"] >= LIQUID
    return {h: r.where(liquid).mean(axis=1) for h, r in fwd.items()}


# ── 訊號（回測）─────────────────────────────────────────────
def momentum_members(m: dict) -> dict:
    """每天的名單（布林矩陣）：strong10、strong30、extreme。"""
    c = m["close"]
    s = (c / c.shift(20) - 1) * 100
    r5 = (c / c.shift(5) - 1) * 100
    p5 = (c.shift(5) / c.shift(10) - 1) * 100
    a = r5 - p5
    liquid = m["tv20"] >= LIQUID
    strong = liquid & (s > 0) & (a > 0)
    rank = a.where(strong).rank(axis=1, ascending=False, method="first")
    out = {"strong10": rank <= 10, "strong30": rank <= 30}

    # 最極端：每天在均量門檻以上的股票裡，強度與加速度各自扣中位數、除以 MAD×1.4826 後的距離
    sv, av, lv = s.to_numpy(), a.to_numpy(), liquid.to_numpy()
    ext = np.zeros_like(lv)
    for i in range(len(c)):
        ok = lv[i] & np.isfinite(sv[i]) & np.isfinite(av[i])
        if ok.sum() < 20:
            continue
        x, y = sv[i][ok], av[i][ok]
        sx = np.median(np.abs(x - np.median(x))) * 1.4826 or 1
        sy = np.median(np.abs(y - np.median(y))) * 1.4826 or 1
        d = np.hypot((x - np.median(x)) / sx, (y - np.median(y)) / sy)
        k = max(1, math.ceil(len(d) * EXTREME))
        thr = np.sort(d)[::-1][k - 1]
        row = np.zeros(lv.shape[1], dtype=bool)
        row[np.flatnonzero(ok)] = d >= thr
        ext[i] = row
    out["extreme"] = pd.DataFrame(ext, index=c.index, columns=c.columns) & strong
    return out


def trust_events(m: dict) -> pd.DataFrame:
    """投信連買剛好第 3 天、之前 20 日累計 ≤ 0（缺值不超過 5 天）。"""
    t = m["trust"]
    pos = (t > 0).astype(int)
    run3 = pos.rolling(3).sum() == 3
    first3 = run3 & ~(pos.shift(3).fillna(0).astype(bool))       # 第 4 天前不是買超 → 剛好第 3 天
    prior = t.shift(3).rolling(20, min_periods=1).sum()
    missing = t.shift(3).isna().rolling(20, min_periods=1).sum()
    enough = t.shift(3).notna().rolling(20, min_periods=1).sum() >= 15
    return first3 & (prior <= 0) & (missing <= 5) & enough


def revenue_events(revenue: pd.DataFrame, dates: pd.DatetimeIndex, exclude: set) -> pd.DataFrame:
    """營收成長加速：每月 11 日（公布期限隔天）後第一個交易日，列出新命中的股票。"""
    import signals
    rev = revenue.copy()
    rev["p"] = rev["year"] * 12 + rev["month"] - 1
    rows, prev = [], set()
    start, end = dates[0], dates[-1]
    p = (start.year * 12 + start.month - 1) - 2
    while True:
        y, mth = divmod(p, 12)
        avail = pd.Timestamp(y + (mth + 1) // 12, (mth + 1) % 12 + 1, 11)   # 下個月 11 日
        if avail > end:
            break
        day = dates[dates >= avail]
        hits = {h["code"] for h in signals.rev_accel(rev[rev["p"] <= p].drop(columns="p"), exclude)}
        if len(day) and avail >= dates[0]:              # 歷史起點以前的月份只拿來比對「新命中」
            rows += [(day[0], code) for code in sorted(hits - prev)]
        prev = hits
        p += 1
    return pd.DataFrame(rows, columns=["date", "code"])


def new_entries(member: pd.DataFrame) -> pd.DataFrame:
    """前一天不在、這天進榜。"""
    before = member.shift(1).fillna(False).astype(bool)
    hit = member & ~before
    st = hit.stack()
    st = st[st]
    return pd.DataFrame({"date": st.index.get_level_values(0), "code": st.index.get_level_values(1)})


# ── 訊號（往後追蹤）─────────────────────────────────────────
def history_entries(hist: pd.DataFrame, linked: bool) -> pd.DataFrame:
    """強勢紀錄：每個記錄日的族群連動（或非連動）名單，取新進榜的。"""
    if hist.empty:
        return pd.DataFrame(columns=["date", "code"])
    h = hist[hist["linked"].astype(bool) == linked]
    rows, prev = [], set()
    for d in sorted(hist["date"].unique()):
        today = set(h.loc[h["date"] == d, "code"])
        rows += [(pd.Timestamp(d), c) for c in sorted(today - prev)]
        prev = today
    return pd.DataFrame(rows, columns=["date", "code"])


def log_entries(log: pd.DataFrame, signal: str) -> pd.DataFrame:
    if log.empty:
        return pd.DataFrame(columns=["date", "code"])
    g = log[log["signal"] == signal]
    rows, prev = [], set()
    for d in sorted(g["date"].unique()):
        today = set(g.loc[g["date"] == d, "code"])
        rows += [(pd.Timestamp(d), c) for c in sorted(today - prev)]
        prev = today
    return pd.DataFrame(rows, columns=["date", "code"])


def load_log() -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame(columns=["date", "signal", "code"])
    return pd.read_csv(LOG_PATH, dtype=str)


def append_log(day: str, results: dict, signals_to_log=("value_yield", "chip_conc", "rev_accel",
                                                      "trust_start")) -> int:
    """選股條件每天的命中名單（往後追蹤用）。同一天重跑會整批取代。"""
    old = load_log()
    rows = [{"date": day, "signal": sid, "code": h["code"]}
            for sid in signals_to_log for h in results.get(sid, {}).get("hits", [])]
    new = pd.DataFrame(rows, columns=["date", "signal", "code"])
    merged = pd.concat([old[old["date"] != day], new], ignore_index=True)
    merged = merged.sort_values(["date", "signal", "code"]).reset_index(drop=True)
    before = old.sort_values(["date", "signal", "code"]).reset_index(drop=True)
    if merged.equals(before):
        return 0
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(LOG_PATH, index=False, lineterminator="\n")
    return len(new)


# ── 統計 ────────────────────────────────────────────────────
def event_returns(events: pd.DataFrame, fwd: dict, bench: dict) -> pd.DataFrame:
    """每個事件的報酬（已扣成本）與超額報酬。"""
    if events.empty:
        return pd.DataFrame(columns=["date", "code"] + [f"r{h}" for h in HORIZONS]
                            + [f"x{h}" for h in HORIZONS])
    ev = events.copy()
    ev["date"] = pd.to_datetime(ev["date"])
    idx = fwd[HORIZONS[0]].index
    ev = ev[ev["date"].isin(idx)]
    cols = fwd[HORIZONS[0]].columns
    ev = ev[ev["code"].isin(cols)]
    di = idx.get_indexer(ev["date"])
    ci = cols.get_indexer(ev["code"])
    for h in HORIZONS:
        r = fwd[h].to_numpy()[di, ci]
        b = bench[h].to_numpy()[di]
        ev[f"r{h}"] = r - COST
        ev[f"x{h}"] = r - b                                     # 超額不扣成本（兩邊同樣進出）
    return ev.reset_index(drop=True)


def summarize(ev: pd.DataFrame) -> dict:
    out = {}
    for h in HORIZONS:
        r, x = ev[f"r{h}"].dropna(), ev[f"x{h}"].dropna()
        n = len(r)
        if not n:
            out[str(h)] = {"n": 0}
            continue
        sd = float(x.std(ddof=1)) if n > 1 else float("nan")
        t = float(x.mean() / (sd / math.sqrt(n))) if n > 1 and sd > 0 else float("nan")
        verdict = ("樣本不足" if n < MIN_N else
                   "優於大盤" if t >= 2 and x.mean() > 0 else
                   "輸給大盤" if t <= -2 else "沒有明顯差異")
        out[str(h)] = {"n": n, "ret": round(float(r.mean()), 2), "med": round(float(r.median()), 2),
                       "win": round(float((r > 0).mean() * 100), 1),
                       "exc": round(float(x.mean()), 2), "beat": round(float((x > 0).mean() * 100), 1),
                       "t": None if t != t else round(t, 2), "verdict": verdict}
    return out


def monthly(ev: pd.DataFrame) -> list:
    if ev.empty:
        return []
    g = ev.assign(ym=ev["date"].dt.strftime("%Y-%m")).groupby("ym")
    return [[ym] + [None if pd.isna(v) else round(float(v), 2) for v in (gg[f"x{h}"].mean() for h in HORIZONS)]
            + [int(len(gg))] for ym, gg in g]


def build(panel: pd.DataFrame, revenue: pd.DataFrame, master: pd.DataFrame,
          strong_hist: pd.DataFrame, names: dict) -> dict:
    if panel.empty:
        return {"asof": "", "signals": []}
    m = matrices(panel)
    dates = m["close"].index
    fwd = forward_returns(m)
    bench = benchmark(fwd, m)
    members = momentum_members(m)
    import signals
    lumpy = set(master[master["industry"].isin(signals.LUMPY_INDUSTRIES)]["code"]) if not master.empty else set()
    log = load_log()
    events = {
        "strong10": new_entries(members["strong10"]),
        "strong30": new_entries(members["strong30"]),
        "extreme": new_entries(members["extreme"]),
        "trust_start": new_entries(trust_events(m)),
        "rev_accel": revenue_events(revenue, dates, lumpy) if not revenue.empty else pd.DataFrame(columns=["date", "code"]),
        "linked": history_entries(strong_hist, True),
        "solo": history_entries(strong_hist, False),
        "value_yield": log_entries(log, "value_yield"),
        "chip_conc": log_entries(log, "chip_conc"),
    }
    # 回測從有完整 20 日強度的那天起算
    first = dates[min(25, len(dates) - 1)]
    out = []
    for sid, name, mode, desc in SIGNALS:
        ev = event_returns(events[sid], fwd, bench)
        if mode == "回測":
            ev = ev[ev["date"] >= first]
        ev = ev.sort_values(["date", "code"])
        recent = ev.tail(30).iloc[::-1]
        out.append({
            "id": sid, "name": name, "mode": mode, "desc": desc,
            "since": ev["date"].min().strftime("%Y-%m-%d") if len(ev) else "",
            "stats": summarize(ev), "monthly": monthly(ev),
            "recent": [[r.date.strftime("%Y-%m-%d"), r.code, names.get(r.code, "")]
                       + [None if pd.isna(getattr(r, f"r{h}")) else round(float(getattr(r, f"r{h}")), 2)
                          for h in HORIZONS] for r in recent.itertuples()],
        })
    return {"asof": dates[-1].strftime("%Y-%m-%d"), "start": first.strftime("%Y-%m-%d"),
            "cost": COST, "horizons": HORIZONS, "signals": out}
