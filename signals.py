"""
選股條件（全部「未驗證」：還沒有回測，只能當觀察名單）

每個條件是一個純函式：吃準備好的資料表，吐出命中的股票與命中原因。
網頁顯示的規則文字（RULES）和程式判斷寫在同一個檔案，改規則時兩邊一起改。
日後若要回測，可以直接拿同一份函式去跑歷史資料。

ETF（00 開頭）不列入。
"""
import pandas as pd

MAX_HITS = 60

CONDITIONS = [
    {"id": "rev_accel", "name": "營收成長加速", "data": "月營收",
     "rule": "最近 6 個月每個月營收都比去年同月高；近 3 個月合計營收的年增率高於前 3 個月合計的年增率；"
             "近 3 個月平均月營收至少 1 億元（排除基期太小、數字忽大忽小的公司）。"
             "建設公司完工才一次認列營收，年增率沒有參考價值，不列入。依近 3 個月年增率排序。"},
    {"id": "trust_start", "name": "投信開始連買", "data": "三大法人",
     "rule": "投信連續買超 3 個交易日以上，而且在這段連買之前的 20 個交易日，"
             "投信累計是賣超或持平（代表是新進場，不是一直在買）。"},
    {"id": "value_yield", "name": "低估值高殖利率", "data": "本益比、殖利率",
     "rule": "目前本益比位於自己近 5 年（至少 3 年）月本益比的最低 20%，而且殖利率高於 5%。"},
    {"id": "chip_conc", "name": "籌碼集中", "data": "集保、融資融券",
     "rule": "千張以上大戶持股比例連續 3 週上升，同一段期間融資餘額下降。"},
]


def _stocks_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df["code"].astype(str).str.startswith("00")]


MIN_MONTHLY_REVENUE = 100_000      # 千元＝1 億元


LUMPY_INDUSTRIES = {"建材營造業", "建材營造"}


def rev_accel(revenue: pd.DataFrame, exclude: set | None = None) -> list[dict]:
    """exclude：不列入的代號（營收一次認列的建設公司）。"""
    if revenue.empty:
        return []
    rev = _stocks_only(revenue).copy()
    if exclude:
        rev = rev[~rev["code"].isin(exclude)]
    rev["p"] = rev["year"] * 12 + rev["month"] - 1
    latest = rev["p"].max()
    need = [latest - i for i in range(5, -1, -1)]
    this = rev[rev["p"].isin(need)].pivot_table(index="code", columns="p", values="revenue")
    last = rev[rev["p"].isin([p - 12 for p in need])].pivot_table(
        index="code", columns="p", values="revenue")
    if not all(c in this.columns for c in need) or not all(c - 12 in last.columns for c in need):
        return []
    cur = this[need].dropna()
    ly = last[[p - 12 for p in need]].dropna()
    ly.columns = need
    codes = cur.index.intersection(ly.index)
    if codes.empty:
        return []
    cur, ly = cur.loc[codes], ly.loc[codes]
    monthly_up = (cur > ly).all(axis=1) & (ly > 0).all(axis=1)
    recent = (cur[need[3:]].sum(axis=1) / ly[need[3:]].sum(axis=1) - 1) * 100
    prior = (cur[need[:3]].sum(axis=1) / ly[need[:3]].sum(axis=1) - 1) * 100
    big_enough = cur[need[3:]].mean(axis=1) >= MIN_MONTHLY_REVENUE
    hit = codes[monthly_up & (recent > prior) & big_enough]
    return [{"code": code, "score": float(recent[code]),
             "reason": f"近 3 月年增 {recent[code]:.1f}%，前 3 月 {prior[code]:.1f}%"}
            for code in hit]


def trust_start(panel: pd.DataFrame) -> list[dict]:
    if panel.empty:
        return []
    df = _stocks_only(panel)[["code", "date", "trust"]].dropna(subset=["trust"])
    days = sorted(df["date"].unique())
    if len(days) < 24:
        return []
    latest = days[-1]
    wide = df[df["date"].isin(days[-60:])].pivot_table(index="code", columns="date",
                                                        values="trust")
    wide = wide.reindex(columns=days[-60:])
    out = []
    for code, row in wide.iterrows():
        values = row.values
        if pd.isna(values[-1]) or values[-1] <= 0:
            continue
        streak = 0
        for v in values[::-1]:
            if pd.notna(v) and v > 0:
                streak += 1
            else:
                break
        if streak < 3:
            continue
        before = values[-streak - 20:-streak]
        if len(before) < 20 or pd.isna(before).sum() > 5:
            continue
        prior = float(pd.Series(before).fillna(0).sum())
        if prior > 0:
            continue
        bought = float(pd.Series(values[-streak:]).sum())
        out.append({"code": code, "score": bought,
                    "reason": f"投信連買 {streak} 日共 {bought / 1000:,.0f} 張；"
                              f"之前 20 日累計 {prior / 1000:,.0f} 張"})
    return out


def value_yield(panel: pd.DataFrame, pe_hist: pd.DataFrame) -> list[dict]:
    if panel.empty or pe_hist.empty:
        return []
    latest_day = panel["date"].max()
    now = _stocks_only(panel[panel["date"] == latest_day])
    now = now[(now["per"] > 0) & (now["yield_pct"] > 5)]
    hist = pe_hist.dropna(subset=["pe"])
    hist = hist[hist["pe"] > 0].sort_values(["code", "ym"])
    by_code = {code: g["pe"].tail(60) for code, g in hist.groupby("code")}
    out = []
    for _, r in now.iterrows():
        h = by_code.get(r["code"])
        if h is None or len(h) < 36:
            continue
        pct = float((h <= r["per"]).mean() * 100)
        if pct > 20:
            continue
        out.append({"code": r["code"], "score": -pct,
                    "reason": f"本益比 {r['per']:.1f}（近 {len(h) // 12} 年第 {pct:.0f} 百分位），"
                              f"殖利率 {r['yield_pct']:.1f}%"})
    return out


def chip_conc(tdcc: pd.DataFrame, panel: pd.DataFrame) -> tuple[list[dict], str]:
    """回傳 (命中, 狀態說明)。集保資料不足 4 週時回傳空清單與說明。"""
    weeks = sorted(tdcc["date"].unique()) if not tdcc.empty else []
    if len(weeks) < 4:
        return [], f"集保資料累積中：已有 {len(weeks)} 週，需要 4 週才能判斷。"
    w = weeks[-4:]
    wide = _stocks_only(tdcc[tdcc["date"].isin(w)]).pivot_table(index="code", columns="date",
                                                                  values="big1000")
    wide = wide.reindex(columns=w).dropna()
    rising = wide[(wide[w[1]] > wide[w[0]]) & (wide[w[2]] > wide[w[1]]) & (wide[w[3]] > wide[w[2]])]
    if rising.empty:
        return [], ""
    margin = panel.dropna(subset=["margin_bal"])[["code", "date", "margin_bal"]]

    def bal_at(code, day):
        m = margin[(margin["code"] == code) & (margin["date"] <= day)]
        return float(m["margin_bal"].iloc[-1]) if not m.empty else None

    out = []
    for code, row in rising.iterrows():
        start, end = bal_at(code, w[0]), bal_at(code, w[3])
        if start is None or end is None or end >= start:
            continue
        out.append({"code": code, "score": float(row[w[3]] - row[w[0]]),
                    "reason": f"千張大戶 {row[w[0]]:.2f}% → {row[w[3]]:.2f}%；"
                              f"融資 {start:,.0f} → {end:,.0f} 張"})
    return out, ""


def run(panel: pd.DataFrame, revenue: pd.DataFrame, pe_hist: pd.DataFrame,
        tdcc: pd.DataFrame, master: pd.DataFrame | None = None) -> dict:
    """{條件 id: {"hits": [...], "note": 狀態說明}}，命中依 score 由大到小。"""
    lumpy = set()
    if master is not None and not master.empty:
        lumpy = set(master[master["industry"].isin(LUMPY_INDUSTRIES)]["code"])
    results = {
        "rev_accel": (rev_accel(revenue, lumpy), ""),
        "trust_start": (trust_start(panel), ""),
        "value_yield": (value_yield(panel, pe_hist), ""),
        "chip_conc": chip_conc(tdcc, panel),
    }
    out = {}
    for cid, (hits, note) in results.items():
        hits = sorted(hits, key=lambda h: h["score"], reverse=True)
        out[cid] = {"hits": hits[:MAX_HITS], "total": len(hits), "note": note}
    return out
