"""
情報中心的網頁資料（產生頁面時寫到 site/data/，前端需要時才下載）

    stocks.json          股票清單 [[代號, 名稱, 市場, 產業], …]（查詢建議用）
    stock/{代號}.json    個股深度頁：K 線、法人、融資、營收、EPS、本益比、集保、重訊
    overview.json        總覽：市場數字、自選股異動、事件、條件命中數、重點新聞、
                         大盤走勢、類股、法人排行、期貨未平倉
    screen.json          選股：每個條件的規則、狀態與命中清單
    stocknews.json       強勢股的近五日新聞與上漲原因（點進強勢股才下載）
    record/index.json    強勢紀錄：日期、族群輪動（每天每個族群幾檔）、每檔出現過的日子
    record/{日期}.json   那天每一檔強勢股的原因、族群與同族群個股

數字在這裡就換好單位（張、億元），前端只負責畫。
"""
import json
import math
from datetime import timedelta
from pathlib import Path

import pandas as pd

import intel_data
import signals
from calendar_data import load_events
from chip_data import load_futures, load_tdcc
from fundamentals import load_announce, load_income, load_revenue
from market_data import load_summary
from news_data import load_all as load_news_all
from news_digest import build as build_digest
from stock_news import load_history as load_strong_history
from stock_data import load as load_stock_list
from watchlist import EDIT_URL, load_watchlist
from xmarket_data import load_xmarket

DAYS = 260          # 個股頁的日資料約一年
REV_MONTHS = 36
QUARTERS = 12
PE_MONTHS = 60
ANN_KEEP = 30
TOP_FLOW = 20
STOCK_NEWS = Path(__file__).resolve().parent / "data" / "stock_news.json"
RECORD_DAYS = 120   # 強勢紀錄分頁放幾個交易日
RECORD_THEMES = 20  # 族群輪動圖最多列幾個族群


def _r(x, n=2):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return round(v, n) if n else int(round(v))


def _lots(x):
    """股 → 張。"""
    v = _r(x, 6)
    return None if v is None else int(round(v / 1000))


def _yi(x, n=2):
    """元 → 億元。"""
    v = _r(x, 6)
    return None if v is None else round(v / 1e8, n)


def _dump(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")


def _roc_iso(v) -> str:
    v = str(v)
    if len(v) == 7 and v.isdigit():
        return f"{int(v[:3]) + 1911}-{v[3:5]}-{v[5:]}"
    return ""


# ── 個股深度頁 ──────────────────────────────────────────────
def _revenue_block(g: pd.DataFrame) -> dict:
    g = g.sort_values(["year", "month"])
    s = g.set_index(g["year"] * 12 + g["month"] - 1)["revenue"]
    tail = s.tail(REV_MONTHS)
    yoy = [None if (p - 12) not in s.index or not s[p - 12] else _r((s[p] / s[p - 12] - 1) * 100, 1)
           for p in tail.index]
    ym = [f"{p // 12}-{p % 12 + 1:02d}" for p in tail.index]
    return {"ym": ym, "v": [_r(v / 1e5, 2) for v in tail.values], "yoy": yoy}


def _income_block(g: pd.DataFrame) -> dict:
    g = g.sort_values(["year", "quarter"]).tail(QUARTERS)

    def ratio(a, b):
        return _r(a / b * 100, 1) if b and not pd.isna(a) and not pd.isna(b) and b > 0 else None

    return {"q": [f"{y}Q{q}" for y, q in zip(g["year"], g["quarter"])],
            "eps": [_r(v) for v in g["eps"]],
            "gm": [ratio(a, b) for a, b in zip(g["gross"], g["revenue"])],
            "om": [ratio(a, b) for a, b in zip(g["operating"], g["revenue"])]}


def _pe_block(g: pd.DataFrame) -> dict:
    g = g.dropna(subset=["close"]).tail(PE_MONTHS)
    return {"ym": list(g["ym"]), "c": [_r(v) for v in g["close"]],
            "pe": [_r(v) if v and v > 0 else None for v in g["pe"]]}


def write_stock_shards(out_dir: Path, panel: pd.DataFrame, master: pd.DataFrame,
                       pe: pd.DataFrame, tdcc: pd.DataFrame, exdiv: pd.DataFrame) -> int:
    revenue = {c: g for c, g in load_revenue().groupby("code")}
    income = {c: g for c, g in load_income().groupby("code")}
    pe_by = {c: g for c, g in pe.groupby("code")}
    tdcc_by = {c: g.sort_values("date") for c, g in tdcc.groupby("code")} if not tdcc.empty else {}
    ann = load_announce()
    ann_by = {c: g for c, g in ann.groupby("code")} if not ann.empty else {}
    ex_by = {c: g for c, g in exdiv.groupby("code")} if not exdiv.empty else {}
    info = master.set_index("code")

    stock_dir = out_dir / "stock"
    count = 0
    for code, g in panel.groupby("code"):
        g = g.sort_values("date")
        latest_val = g.dropna(subset=["per", "yield_pct", "pbr"], how="all").tail(1)
        meta = info.loc[code] if code in info.index else None
        shard = {
            "code": code,
            "name": meta["name"] if meta is not None else "",
            "market": meta["market"] if meta is not None else g["market"].iloc[-1],
            "industry": meta["industry"] if meta is not None else "",
            "asof": g["date"].iloc[-1].strftime("%Y-%m-%d"),
            "d": {
                "t": [d.strftime("%Y-%m-%d") for d in g["date"]],
                "o": [_r(v) for v in g["open"]], "h": [_r(v) for v in g["high"]],
                "l": [_r(v) for v in g["low"]], "c": [_r(v) for v in g["close"]],
                "v": [_lots(v) for v in g["volume"]],
                "fi": [_lots(v) for v in g["foreign"]], "tr": [_lots(v) for v in g["trust"]],
                "de": [_lots(v) for v in g["dealer"]],
                "mb": [_r(v, 0) for v in g["margin_bal"]], "sb": [_r(v, 0) for v in g["short_bal"]],
            },
            "val": {} if latest_val.empty else {
                "per": _r(latest_val["per"].iloc[0]), "yield": _r(latest_val["yield_pct"].iloc[0]),
                "pbr": _r(latest_val["pbr"].iloc[0]),
                "date": latest_val["date"].iloc[0].strftime("%Y-%m-%d")},
        }
        if code in revenue:
            shard["rev"] = _revenue_block(revenue[code])
        if code in income:
            shard["q"] = _income_block(income[code])
        if code in pe_by:
            shard["pe"] = _pe_block(pe_by[code])
        if code in tdcc_by:
            t = tdcc_by[code]
            shard["tdcc"] = {"t": [d.strftime("%Y-%m-%d") for d in t["date"]],
                             "big": [_r(v) for v in t["big1000"]],
                             "big400": [_r(v) for v in t["big400"]]}
        if code in ann_by:
            a = ann_by[code].head(ANN_KEEP)
            shard["ann"] = [[_roc_iso(r["date"]), str(r["time"]), r["subject"]]
                            for _, r in a.iterrows()]
        if code in ex_by:
            shard["exdiv"] = [[_roc_iso(r["date"]), r["kind"], r["cash"]]
                              for _, r in ex_by[code].iterrows()]
        _dump(shard, stock_dir / f"{code}.json")
        count += 1
    return count


# ── 總覽 ───────────────────────────────────────────────────
def _kpis(summary: pd.DataFrame, xm: pd.DataFrame, latest: str) -> list[dict]:
    row = summary[summary["date"] == latest]
    s = row.iloc[0] if not row.empty else pd.Series(dtype=object)

    def val(key):
        v = s.get(key) if not s.empty else None
        return None if v is None or pd.isna(v) else float(v)

    def both(key):
        parts = [val(f"twse_{key}"), val(f"tpex_{key}")]
        parts = [p for p in parts if p is not None]
        return sum(parts) if parts else None

    out = []

    def add(label, value, delta=None, direction=0, note=""):
        out.append({"label": label, "value": value, "delta": delta, "dir": direction,
                    "note": note})

    for name, key in (("加權指數", "twse_index"), ("櫃買指數", "tpex_index")):
        v, chg = val(key), val(f"{key}_chg")
        if v is None:
            add(name, "—")
            continue
        pct = chg / (v - chg) * 100 if chg is not None and v != chg else None
        add(name, f"{v:,.2f}",
            None if chg is None else f"{chg:+,.2f}（{pct:+.2f}%）" if pct is not None else f"{chg:+,.2f}",
            0 if not chg else (1 if chg > 0 else -1))
    turnover = both("turnover")
    add("成交值", "—" if turnover is None else f"{turnover / 1e8:,.0f} 億", note="上市＋上櫃")
    for label, key in (("外資買賣超", "foreign_value"), ("投信買賣超", "trust_value")):
        v = both(key)
        add(label, "—" if v is None else f"{v / 1e8:+,.1f} 億",
            direction=0 if not v else (1 if v > 0 else -1), note="上市＋上櫃")
    cur, prev = both("margin_amount"), both("margin_amount_prev")
    if cur is not None and prev is not None:
        diff = (cur - prev) / 1e5
        add("融資增減", f"{diff:+,.1f} 億", direction=1 if diff > 0 else -1 if diff < 0 else 0,
            note=f"餘額 {cur / 1e5:,.0f} 億")
    else:
        add("融資增減", "—")
    for name, label in (("美元兌台幣", "美元兌台幣"), ("費城半導體", "費半（前一晚）")):
        series = xm[xm["item"] == name].sort_values("price_date")
        if len(series) >= 2:
            a, b = float(series["price"].iloc[-2]), float(series["price"].iloc[-1])
            fmt = "{:,.3f}" if name == "美元兌台幣" else "{:,.2f}"
            add(label, fmt.format(b), f"{(b / a - 1) * 100:+.2f}%",
                1 if b > a else -1 if b < a else 0,
                series["price_date"].iloc[-1].strftime("%m/%d"))
        else:
            add(label, "—")
    return out


def _watch_rows(panel: pd.DataFrame, names: dict, watch: list[dict], latest) -> list[dict]:
    ann = load_announce()
    roc = f"{latest.year - 1911:03d}{latest.month:02d}{latest.day:02d}"
    ann_codes = set(ann[ann["date"] == roc]["code"]) if not ann.empty else set()
    out = []
    for w in watch:
        g = panel[panel["code"] == w["code"]].sort_values("date")
        row = {"code": w["code"], "name": names.get(w["code"], ""), "note": w["note"],
               "push": w["push"]}
        if len(g) >= 2:
            last, prev = g.iloc[-1], g.iloc[-2]
            vol20 = g["volume"].iloc[-21:-1].mean()
            row.update({
                "date": last["date"].strftime("%m/%d"),
                "close": _r(last["close"]),
                "chg": _r((last["close"] / prev["close"] - 1) * 100) if prev["close"] else None,
                "volr": _r(last["volume"] / vol20, 1) if vol20 else None,
                "fi": _lots(last["foreign"]), "tr": _lots(last["trust"]),
                "ann": w["code"] in ann_codes,
            })
        out.append(row)
    return out


def _events(today, watch_codes: set, names: dict, exdiv: pd.DataFrame) -> list[dict]:
    out = []
    cal = load_events()
    if not cal.empty and "_ts" in cal:
        tp = cal["_ts"].dt.tz_convert("Asia/Taipei")
        lo = pd.Timestamp(today, tz="Asia/Taipei")
        hi = lo + pd.Timedelta(days=7)
        sel = cal[(tp >= lo) & (tp < hi) & (cal["impact"] == "High")]
        from calendar_i18n import translate_country, translate_title
        for _, e in sel.iterrows():
            t = e["_ts"].tz_convert("Asia/Taipei")
            out.append({"date": t.strftime("%Y-%m-%d"), "time": t.strftime("%H:%M"),
                        "kind": "總經",
                        "text": f"{translate_country(e['country'])} {translate_title(e['title'])}"})
    if not exdiv.empty:
        for _, r in exdiv[exdiv["code"].isin(watch_codes)].iterrows():
            d = _roc_iso(r["date"])
            if d and today.isoformat() <= d <= (today + timedelta(days=30)).isoformat():
                cash = f"，現金 {float(r['cash']):g} 元" if _r(r["cash"]) else ""
                out.append({"date": d, "time": "", "kind": "除權息",
                            "text": f"{r['code']} {names.get(r['code'], r['name'])} 除{r['kind'].replace('除', '')}{cash}"})
    for months in (0, 1):
        y, m = today.year, today.month + months
        if m > 12:
            y, m = y + 1, m - 12
        deadline = pd.Timestamp(y, m, 10).date()
        if today <= deadline <= today + timedelta(days=10):
            out.append({"date": deadline.isoformat(), "time": "", "kind": "營收",
                        "text": "上市櫃公司上月營收公布截止日"})
    return sorted(out, key=lambda e: (e["date"], e["time"]))[:20]


def _market_series(panel: pd.DataFrame, xm: pd.DataFrame) -> dict:
    p = panel.assign(fv=panel["foreign"] * panel["close"], tv=panel["trust"] * panel["close"])
    daily = p.groupby("date").agg(fv=("fv", "sum"), tv=("tv", "sum"), turnover=("turnover", "sum"))
    taiex = xm[xm["item"] == "加權指數"].set_index("price_date")["price"]
    taiex = taiex.reindex(daily.index)
    return {"t": [d.strftime("%Y-%m-%d") for d in daily.index],
            "taiex": [_r(v) for v in taiex],
            "fi": [_yi(v, 1) for v in daily["fv"]], "tr": [_yi(v, 1) for v in daily["tv"]],
            "turnover": [_yi(v, 0) for v in daily["turnover"]]}


PERIODS = [1, 5, 10, 20, 60]       # 漲跌幅排行可選的區間（交易日）


def _sectors(panel: pd.DataFrame, master: pd.DataFrame, days: list) -> dict:
    """
    類股：每個產業的加權漲跌、家數、成交值，以及「每一檔」的漲跌與成交值
    （熱力圖點進產業、清單依成交值或漲跌排序都要用到全部股票）。

    漲跌分 1／5／10／20／60 日，都是用收盤價算（沒有還原除權息）；
    中間停牌的日子沿用停牌前的收盤。產業漲跌以最新一天的成交值加權。

    stocks：[[代號, 名稱, 產業序號, 收盤, 成交值億, 1日%, 5日%, 10日%, 20日%, 60日%]]
    industries：每個產業 {industry, turnover, n, chg:[各區間], up:[…], down:[…]}
    """
    empty = {"asof": "", "periods": PERIODS, "industries": [], "stocks": []}
    if len(days) < 2:
        return empty
    closes = (panel[panel["date"].isin(days[-(max(PERIODS) + 1):])]
              .pivot_table(index="date", columns="code", values="close").sort_index().ffill())
    last = panel[panel["date"] == days[-1]].set_index("code")
    last = last[~last.index.str.startswith("00")].dropna(subset=["close", "turnover"])
    last = last[last["turnover"] > 0]
    now = closes.iloc[-1]
    cols = []
    for k in PERIODS:
        col = f"r{k}"
        cols.append(col)
        if len(closes) > k:
            base = closes.iloc[-1 - k]
            last[col] = ((now / base - 1) * 100).reindex(last.index)
        else:
            last[col] = float("nan")
    last = last.dropna(subset=["r1"])
    ind = master.set_index("code")["industry"]
    last = last.assign(industry=ind.reindex(last.index).fillna("其他").replace("", "其他"),
                       name=master.set_index("code")["name"].reindex(last.index).fillna(""))

    industries = []
    for industry, g in last.groupby("industry"):
        info = {"industry": industry, "turnover": _yi(g["turnover"].sum(), 1), "n": int(len(g)),
                "chg": [], "up": [], "down": []}
        for col in cols:
            v = g.dropna(subset=[col])
            w = v["turnover"].sum()
            info["chg"].append(_r((v[col] * v["turnover"]).sum() / w) if w else None)
            info["up"].append(int((v[col] > 0).sum()))
            info["down"].append(int((v[col] < 0).sum()))
        industries.append(info)
    industries.sort(key=lambda s: s["turnover"] or 0, reverse=True)
    index = {s["industry"]: i for i, s in enumerate(industries)}
    stocks = [[code, r["name"], index[r["industry"]], _r(r["close"]), _yi(r["turnover"], 2)]
              + [_r(r[c]) for c in cols]
              for code, r in last.sort_values("turnover", ascending=False).iterrows()]
    return {"asof": pd.Timestamp(days[-1]).strftime("%Y-%m-%d"), "periods": PERIODS,
            "industries": industries, "stocks": stocks}


MOMENTUM_DAYS = 41           # 20 日強度＋往回畫 5 天軌跡＋前 5 日比較，留一點餘裕
MOMENTUM_MIN_TURNOVER = 3e7  # 20 日平均成交值至少 3,000 萬，成交太少的不列（自選股例外）


def _momentum(panel: pd.DataFrame, master: pd.DataFrame, days: list, xm: pd.DataFrame,
              watch_codes: set) -> dict:
    """
    強勢股（漲幅變化）：每一檔近 41 個交易日的收盤，前端據此算
    強度（20 日漲幅）、加速度（近 5 日 − 前 5 日漲幅）與軌跡。
    stocks：[[代號, 名稱, 產業序號, 20 日均成交值億, [收盤 × 41]]]
    bench：加權指數同一段的收盤（基準線）
    """
    window = days[-MOMENTUM_DAYS:]
    if len(window) < 31:
        return {"asof": "", "dates": [], "industries": [], "stocks": [], "bench": []}
    part = panel[panel["date"].isin(window) & ~panel["code"].str.startswith("00")]
    closes = part.pivot_table(index="date", columns="code", values="close").reindex(window).ffill()
    avg_turnover = part[part["date"].isin(window[-20:])].groupby("code")["turnover"].mean()
    info = master.set_index("code")
    industries = sorted({(info["industry"].get(c) or "其他") for c in closes.columns
                         if c in info.index} | {"其他"})
    ind_index = {name: i for i, name in enumerate(industries)}
    stocks = []
    for code in closes.columns:
        series = closes[code]
        # 至少要能算出 5 天前的 20 日強度（index 15 起有值）
        if series.iloc[MOMENTUM_DAYS - 31:].isna().any() or series.iloc[-1] != series.iloc[-1]:
            continue
        liquid = avg_turnover.get(code, 0) >= MOMENTUM_MIN_TURNOVER
        if not liquid and code not in watch_codes:
            continue
        industry = (info["industry"].get(code) if code in info.index else "") or "其他"
        stocks.append([code, info["name"].get(code, "") if code in info.index else "",
                       ind_index[industry], _yi(avg_turnover.get(code, 0), 2),
                       [_r(v) for v in series]])
    bench = xm[xm["item"] == "加權指數"].set_index("price_date")["price"]
    bench = bench.reindex(pd.to_datetime(window)).ffill()
    return {"asof": pd.Timestamp(window[-1]).strftime("%Y-%m-%d"),
            "dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in window],
            "industries": industries, "stocks": stocks,
            "bench": [_r(v) for v in bench]}


def _stock_news() -> dict:
    """強勢股新聞與上漲原因（stock_news.py 產生）；網頁用不到資料指紋。"""
    try:
        d = json.loads(STOCK_NEWS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"stocks": {}}
    for s in (d.get("stocks") or {}).values():
        s.pop("hash", None)
    return d


def _strong_record(data_dir: Path) -> None:
    """
    強勢紀錄分頁（stock_news.py 每天存的歷史）：

    record/index.json   dates、themes [[族群, [每天的族群連動檔數]]]（依總次數取前幾個）、
                        stocks {代號: [名稱, [出現的日期序號]]}、summary [[強勢股數, 連動數, 族群數]]
    record/{日期}.json  rows [[代號, 名稱, 名次, 自選, 強度, 近5日, 加速, 分類, 原因, 可信度,
                        方法, 族群, 是否連動, 同族群 [[代號, 名稱, 近5日, 相關, 強勢股, 新聞提到]],
                        關鍵新聞標題, 連結, 來源]]
    """
    out = data_dir / "record"
    hist = load_strong_history()
    if hist.empty:
        _dump({"dates": [], "themes": [], "stocks": {}, "summary": []}, out / "index.json")
        return
    dates = sorted(hist["date"].unique())[-RECORD_DAYS:]
    hist = hist[hist["date"].isin(dates)].copy()
    hist["linked"] = hist["linked"].astype(bool)
    pos = {d: i for i, d in enumerate(dates)}
    linked = hist[hist["linked"] & (hist["group"].fillna("") != "")]
    counts = linked.groupby(["group", "date"]).size()
    top = linked.groupby("group").size().sort_values(ascending=False).head(RECORD_THEMES)
    stocks = {code: [g["name"].iloc[0], sorted(pos[d] for d in g["date"])]
              for code, g in hist.groupby("code")}
    summary = []
    for d in dates:
        day = hist[hist["date"] == d]
        summary.append([len(day), int(day["linked"].sum()),
                        int(day.loc[day["linked"], "group"].nunique())])
    _dump({"dates": dates,
           "themes": [[g, [int(counts.get((g, d), 0)) for d in dates]] for g in top.index],
           "stocks": stocks, "summary": summary}, out / "index.json")
    for d, day in hist.groupby("date"):
        rows = []
        for r in day.itertuples(index=False):
            try:
                members = json.loads(r.members or "[]")
            except ValueError:
                members = []
            rank = _r(r.rank, 0)
            rows.append([r.code, r.name, None if rank is None or rank < 0 else rank, bool(r.watch),
                         _r(r.s, 1), _r(r.r5, 1), _r(r.a, 1), r.tag, r.why, r.conf, r.method,
                         r.group or "", bool(r.linked), members, r.key_t, r.key_u, r.key_src])
        _dump({"date": d, "rows": rows}, out / f"{d}.json")


def _flows(panel: pd.DataFrame, names: dict, latest) -> dict:
    day = panel[(panel["date"] == latest) & ~panel["code"].str.startswith("00")]
    out = {}
    for col, label in (("foreign", "fi"), ("trust", "tr")):
        d = day.dropna(subset=[col, "close"]).assign(val=lambda x: x[col] * x["close"])
        for side, asc in (("buy", False), ("sell", True)):
            top = d.sort_values("val", ascending=asc).head(TOP_FLOW)
            top = top[top["val"] > 0] if side == "buy" else top[top["val"] < 0]
            out[f"{label}_{side}"] = [[r["code"], names.get(r["code"], ""), _lots(r[col]),
                                       _yi(r["val"], 2)] for _, r in top.iterrows()]
    return out


def _futures() -> dict:
    f = load_futures()
    if f.empty:
        return {}
    f = f.tail(120)
    return {"t": list(f["date"]), "foreign": [_r(v, 0) for v in f["foreign"]],
            "trust": [_r(v, 0) for v in f["trust"]], "dealer": [_r(v, 0) for v in f["dealer"]]}


def _news(watch_terms: list[str]) -> list[dict]:
    df = load_news_all().get("news", pd.DataFrame())
    if df.empty:
        return []
    return [{"title": e["title"], "url": e["url"], "sources": e["sources"],
             "summary": e["summary"], "topics": e["topics"]}
            for e in build_digest(df, watch_terms)[:5]]


# ── 選股 ───────────────────────────────────────────────────
def _screen(results: dict, panel: pd.DataFrame, master: pd.DataFrame, latest) -> dict:
    info = master.set_index("code")
    closes = {c: g.sort_values("date")["close"] for c, g in panel.groupby("code")}
    conds = []
    for c in signals.CONDITIONS:
        res = results.get(c["id"], {"hits": [], "total": 0, "note": ""})
        hits = []
        for h in res["hits"]:
            s = closes.get(h["code"])
            last = s.iloc[-1] if s is not None and len(s) else None
            chg = (s.iloc[-1] / s.iloc[-2] - 1) * 100 if s is not None and len(s) >= 2 else None
            hits.append({"code": h["code"],
                         "name": info["name"].get(h["code"], "") if h["code"] in info.index else "",
                         "industry": info["industry"].get(h["code"], "") if h["code"] in info.index else "",
                         "reason": h["reason"], "close": _r(last), "chg": _r(chg),
                         "spark": [_r(v) for v in (s.tail(20) if s is not None else [])]})
        conds.append({**c, "total": res["total"], "note": res["note"], "hits": hits})
    return {"asof": latest.strftime("%Y-%m-%d"), "conditions": conds}


def build(out_dir: Path) -> dict:
    """寫出所有情報中心資料，回傳給設定頁用的摘要。"""
    data_dir = out_dir / "data"
    panel = intel_data.daily_panel(DAYS)
    if panel.empty:
        _dump({"asof": "", "kpi": [], "watch": [], "events": [], "signals": [], "news": []},
              data_dir / "overview.json")
        _dump({"asof": "", "conditions": []}, data_dir / "screen.json")
        _dump([], data_dir / "stocks.json")
        return {"latest": "無資料", "stocks": 0, "watch": 0}

    master = intel_data.stock_master()
    names = dict(zip(master["code"], master["name"]))
    days = intel_data.trading_days(panel)
    latest = pd.Timestamp(days[-1])
    today = intel_data.today_taipei()
    watch = load_watchlist()
    watch_codes = {w["code"] for w in watch}
    watch_terms = sorted(watch_codes) + [names[c] for c in watch_codes
                                         if len(names.get(c, "")) >= 2]
    exdiv = load_stock_list("exdiv")
    xm = load_xmarket()
    pe = intel_data.pe_series(panel)
    tdcc = load_tdcc()

    in_panel = set(panel["code"].unique())
    listed = master[master["code"].isin(in_panel)]
    _dump([[r["code"], r["name"], r["market"], r["industry"]] for _, r in listed.iterrows()],
          data_dir / "stocks.json")

    shards = write_stock_shards(data_dir, panel, master, pe, tdcc, exdiv)

    results = signals.run(panel, load_revenue(), pe, tdcc, master)
    _dump(_screen(results, panel, master, latest), data_dir / "screen.json")

    summary = load_summary()
    overview = {
        "asof": latest.strftime("%Y-%m-%d"),
        "kpi": _kpis(summary, xm, latest.strftime("%Y-%m-%d")),
        "watch": _watch_rows(panel, names, watch, latest),
        "edit_url": EDIT_URL,
        "events": _events(today, watch_codes, names, exdiv),
        "signals": [{"id": c["id"], "name": c["name"], "total": results[c["id"]]["total"],
                     "note": results[c["id"]]["note"]} for c in signals.CONDITIONS],
        "news": _news(watch_terms),
        "market": _market_series(panel, xm),
        "flows": _flows(panel, names, latest),
        "futures": _futures(),
    }
    _dump(overview, data_dir / "overview.json")
    # 類股、強勢股的資料比較大，點進子分頁才下載
    _dump(_sectors(panel, master, days), data_dir / "sectors.json")
    _dump(_momentum(panel, master, days, xm, watch_codes), data_dir / "momentum.json")
    _dump(_stock_news(), data_dir / "stocknews.json")
    _strong_record(data_dir)
    return {"latest": latest.strftime("%Y-%m-%d"), "stocks": shards, "watch": len(watch)}
