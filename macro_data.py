"""
總經數據（python update_data.py macro；總覽「總經」子分頁）

台灣（都是政府開放資料，不用金鑰）：
    國發會 景氣指標與燈號（data.gov.tw 6099，zip）：景氣對策信號分數、領先／同時指標（不含趨勢）、
        海關出口值、工業生產指數、名目半導體設備進口、外銷訂單動向指數、失業率
    國發會 採購經理人指數（data.gov.tw 6100）：製造業 PMI、非製造業 NMI
    中央銀行 貨幣總計數（EF15M01，日平均）：M1B、M2 年增率
    經濟部 外銷訂單（data.gov.tw 6845）：金額（百萬美元）
美國：FRED 的 fredgraph.csv（不用金鑰）——CPI、核心 CPI、核心 PCE、非農就業、失業率、
    初領失業金、聯邦基金利率、實質 GDP、零售銷售、工業生產、高收益債利差、密大消費者信心

原始值存 data/macro.csv（series, date, value；月資料的 date 是當月 1 日），
每次整段重抓、成功的序列整段取代（官方會修正前值）；抓失敗的保留舊資料。
build() 算年增率／月變動，加上經濟日曆的公布值，寫 site/data/macro.json。
"""
from __future__ import annotations

import csv
import io
import logging
import math
import unicodedata
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "macro.csv"
COLUMNS = ["series", "date", "value"]
FRED_START = "2014-01-01"
DATASET_API = "https://data.gov.tw/api/v2/rest/dataset/"
CBC_M = "https://www.cbc.gov.tw/public/data/OpenData/經研處/EF15M01.csv"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"

FRED_SERIES = ["CPIAUCSL", "CPILFESL", "PCEPILFE", "PAYEMS", "UNRATE", "ICSA", "DFF",
               "A191RL1Q225SBEA", "RSAFS", "INDPRO", "BAMLH0A0HYM2", "UMCSENT"]

# 國發會 zip 裡要的欄位：(檔名, 欄名開頭, 序列代號)
NDC_COLUMNS = [
    ("景氣指標與燈號", "景氣對策信號綜合分數", "tw_signal"),
    ("景氣指標與燈號", "領先指標不含趨勢指數", "tw_leading"),
    ("景氣指標與燈號", "同時指標不含趨勢指數", "tw_coincident"),
    ("同時指標構成項目", "海關出口值", "tw_export"),
    ("同時指標構成項目", "工業生產指數", "tw_ipi"),
    ("領先指標構成項目", "名目半導體設備進口", "tw_semi_equip"),
    ("領先指標構成項目", "外銷訂單動向指數", "tw_orders_idx"),
    ("落後指標構成項目", "失業率", "tw_unemp"),
]

# 頁面上的卡片：(代號, 地區, 名稱, 原始序列, 轉換, 單位, 小數, 好的方向, 說明)
#   轉換：level 原值、yoy 年增率、diff 比上一期的變動、mom 月增率
#   好的方向：1 越高對經濟越好、-1 越低越好、0 不判斷（決定漲跌的顏色）
CARDS = [
    ("tw_signal", "tw", "景氣對策信號", "tw_signal", "level", "分", 0, 1,
     "9–16 藍燈（低迷）、17–22 黃藍、23–31 綠燈（穩定）、32–37 黃紅、38–45 紅燈（熱絡）"),
    ("tw_leading", "tw", "領先指標", "tw_leading", "level", "", 2, 1,
     "不含趨勢指數；連續上升代表未來幾個月景氣可能轉好"),
    ("tw_pmi", "tw", "製造業 PMI", "tw_pmi", "level", "", 1, 1, "高於 50 代表擴張"),
    ("tw_nmi", "tw", "非製造業 NMI", "tw_nmi", "level", "", 1, 1, "高於 50 代表擴張"),
    ("tw_money", "tw", "M1B／M2 年增率", "tw_m1b_yoy", "level", "%", 2, 1,
     "M1B 年增率高於 M2（黃金交叉）代表活期資金增加，常被視為資金行情的條件"),
    ("tw_orders", "tw", "外銷訂單年增率", "tw_orders", "yoy", "%", 1, 1,
     "經濟部，美元計價；通常領先出口 1～3 個月"),
    ("tw_export", "tw", "出口年增率", "tw_export", "yoy", "%", 1, 1, "海關出口值，新臺幣計價"),
    ("tw_ipi", "tw", "工業生產年增率", "tw_ipi", "yoy", "%", 1, 1, ""),
    ("tw_semi_equip", "tw", "半導體設備進口年增率", "tw_semi_equip", "yoy", "%", 1, 1,
     "名目值；反映半導體廠的擴產投資"),
    ("tw_unemp", "tw", "失業率", "tw_unemp", "level", "%", 2, -1, ""),
    ("us_cpi", "us", "CPI 年增率", "CPIAUCSL", "yoy", "%", 1, -1, "物價越高，降息空間越小"),
    ("us_core_cpi", "us", "核心 CPI 年增率", "CPILFESL", "yoy", "%", 1, -1, "不含食品與能源"),
    ("us_core_pce", "us", "核心 PCE 年增率", "PCEPILFE", "yoy", "%", 1, -1, "Fed 最看重的通膨指標，目標 2%"),
    ("us_nfp", "us", "非農就業（月增，千人）", "PAYEMS", "diff", "千人", 0, 1, ""),
    ("us_unemp", "us", "失業率", "UNRATE", "level", "%", 1, -1, ""),
    ("us_claims", "us", "初領失業金（週，千人）", "ICSA", "level", "千人", 0, -1, "每週四公布，最即時的就業指標"),
    ("us_ffr", "us", "聯邦基金利率", "DFF", "level", "%", 2, 0, "實際成交利率（每日）"),
    ("us_gdp", "us", "實質 GDP（季增年率）", "A191RL1Q225SBEA", "level", "%", 1, 1, ""),
    ("us_retail", "us", "零售銷售月增率", "RSAFS", "mom", "%", 1, 1, ""),
    ("us_ip", "us", "工業生產年增率", "INDPRO", "yoy", "%", 1, 1, ""),
    ("us_hy", "us", "高收益債利差", "BAMLH0A0HYM2", "level", "%", 2, -1,
     "垃圾債和公債的利差；急升代表信用風險升高、市場避險"),
    ("us_umich", "us", "密大消費者信心", "UMCSENT", "level", "", 1, 1, ""),
]
# 月資料畫 10 年；日／週資料只畫 3 年，檔案才不會太大
CHART_YEARS = {"DFF": 3, "BAMLH0A0HYM2": 3, "ICSA": 3}
SCALE = {"ICSA": 0.001}            # 初領失業金原始單位是人，換成千人
LIGHTS = [(38, "紅燈"), (32, "黃紅燈"), (23, "綠燈"), (17, "黃藍燈"), (0, "藍燈")]
CAL_COUNTRIES = {"US", "CN", "TW", "JP", "EU", "DE", "KR", "UK", "GB"}

log = logging.getLogger("macro")


def light(score) -> str:
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return ""
    return next(name for lo, name in LIGHTS if score >= lo)


# ── 抓資料 ─────────────────────────────────────────────

def _session():
    from curl_cffi import requests as cr
    return cr.Session(impersonate="chrome124")


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp950", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _num(v):
    try:
        x = float(str(v).replace(",", "").strip())
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def _ym(text: str) -> str | None:
    """202608、2026M08 → 2026-08-01；民國 11507 → 2026-07-01。"""
    t = str(text).strip().upper().replace("M", "")
    if not t.isdigit():
        return None
    if len(t) == 6 and t.startswith(("19", "20")):
        y, m = int(t[:4]), int(t[4:])
    elif len(t) in (5, 4):          # 民國年 3 位或 2 位 + 月
        y, m = int(t[:-2]) + 1911, int(t[-2:])
    else:
        return None
    return f"{y:04d}-{m:02d}-01" if 1 <= m <= 12 else None


def parse_fred(text: str, sid: str) -> list[tuple]:
    rows = list(csv.reader(io.StringIO(text)))
    out = []
    for r in rows[1:]:
        if len(r) >= 2:
            v = _num(r[1])
            if v is not None:
                out.append((sid, r[0], v))
    return out


def parse_ndc_zip(raw: bytes) -> list[tuple]:
    z = zipfile.ZipFile(io.BytesIO(raw))
    files = {n.rsplit("/", 1)[-1].replace(".csv", ""): n for n in z.namelist()}
    out = []
    for fname, prefix, sid in NDC_COLUMNS:
        if fname not in files:
            continue
        rows = list(csv.reader(io.StringIO(_decode(z.read(files[fname])))))
        if not rows:
            continue
        head = rows[0]
        col = next((i for i, h in enumerate(head) if h.strip().startswith(prefix)), None)
        if col is None:
            continue
        for r in rows[1:]:
            d = _ym(r[0]) if r else None
            v = _num(r[col]) if d and col < len(r) else None
            if v is not None:
                out.append((sid, d, v))
    return out


def parse_pmi(text: str) -> list[tuple]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        d = _ym(r.get("Date", ""))
        if not d:
            continue
        for k, sid in (("PMI", "tw_pmi"), ("NMI", "tw_nmi")):
            v = _num(r.get(k, ""))
            if v is not None:
                out.append((sid, d, v))
    return out


def parse_cbc_money(text: str) -> list[tuple]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    head = [unicodedata.normalize("NFKC", h).replace(" ", "") for h in rows[0]]
    want = {"tw_m1b_yoy": "-M1B-年增率", "tw_m2_yoy": "-M2-年增率"}
    cols = {sid: next((i for i, h in enumerate(head) if h.endswith(suffix)), None)
            for sid, suffix in want.items()}
    out = []
    for r in rows[1:]:
        d = _ym(r[0]) if r else None
        if not d:
            continue
        for sid, i in cols.items():
            v = _num(r[i]) if i is not None and i < len(r) else None
            if v is not None:
                out.append((sid, d, v))
    return out


def parse_orders(text: str) -> list[tuple]:
    out = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) >= 3 and r[0].strip() == "外銷訂單金額":
            d, v = _ym(r[1]), _num(r[2])
            if d and v is not None:
                out.append(("tw_orders", d, v))
    return out


def _dataset_url(s, nid: int, fmt: str | None = None) -> str | None:
    r = s.get(DATASET_API + str(nid), timeout=60)
    dist = (r.json().get("result") or {}).get("distribution") or []
    for d in dist:
        if fmt is None or (d.get("resourceFormat") or "").upper() == fmt:
            return d.get("resourceDownloadUrl")
    return None


def fetch_all(logger: logging.Logger | None = None) -> dict[str, list[tuple]]:
    """回傳 {來源: [(series, date, value)]}；失敗的來源不放進來。"""
    lg = logger or log
    s = _session()
    got: dict[str, list[tuple]] = {}

    def run(name, fn):
        try:
            rows = fn()
        except Exception as e:                      # 單一來源失敗不影響其他
            lg.warning(f"總經：{name} 失敗 {e.__class__.__name__}: {e}")
            return
        if rows:
            got[name] = rows
            lg.info(f"總經：{name} {len(rows)} 筆")
        else:
            lg.warning(f"總經：{name} 沒有資料")

    for sid in FRED_SERIES:
        run(f"FRED {sid}", lambda sid=sid: parse_fred(
            _decode(s.get(FRED.format(id=sid, start=FRED_START), timeout=60).content), sid))
    run("國發會景氣指標", lambda: parse_ndc_zip(s.get(_dataset_url(s, 6099), timeout=120).content))
    run("國發會 PMI", lambda: parse_pmi(_decode(s.get(_dataset_url(s, 6100), timeout=60).content)))
    run("央行貨幣總計數", lambda: parse_cbc_money(_decode(s.get(CBC_M, timeout=60).content)))
    run("經濟部外銷訂單", lambda: parse_orders(_decode(s.get(_dataset_url(s, 6845), timeout=60).content)))
    return got


def load() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(CSV_PATH, dtype={"series": str, "date": str})
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])


def merge(got: dict[str, list[tuple]]) -> int:
    """抓到的序列整段取代舊的；回傳有變動的序列數。"""
    old = load()
    rows = [r for v in got.values() for r in v]
    if not rows:
        return 0
    new = pd.DataFrame(rows, columns=COLUMNS).drop_duplicates(["series", "date"], keep="last")
    fresh = set(new["series"])
    keep = old[~old["series"].isin(fresh)]
    out = pd.concat([keep, new], ignore_index=True).sort_values(["series", "date"]).reset_index(drop=True)
    changed = 0
    for sid in fresh:
        a = old[old["series"] == sid][["date", "value"]].reset_index(drop=True)
        b = out[out["series"] == sid][["date", "value"]].reset_index(drop=True)
        if not a.equals(b):
            changed += 1
    if changed or len(out) != len(old):
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(CSV_PATH, index=False, encoding="utf-8", lineterminator="\n")
    return changed


def update(logger: logging.Logger | None = None) -> int:
    lg = logger or log
    got = fetch_all(lg)
    if not got:
        lg.warning("總經：全部來源都失敗，本次不更新")
        return 0
    n = merge(got)
    lg.info(f"總經：{n} 個序列有更新")
    return n


# ── 整理成頁面資料 ─────────────────────────────────────

def _r(v, d=2):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), d)


def _series(df: pd.DataFrame, sid: str) -> pd.Series:
    g = df[df["series"] == sid]
    s = pd.Series(g["value"].values * SCALE.get(sid, 1), index=pd.to_datetime(g["date"]), dtype=float)
    return s[~s.index.duplicated(keep="last")].sort_index()


def transform(s: pd.Series, how: str) -> pd.Series:
    if s.empty:
        return s
    if how == "yoy":
        # 月資料：和 12 個月前同一月比（用日期對，不用位置，中間缺月也不會錯）
        prev = s.copy()
        prev.index = prev.index + pd.DateOffset(years=1)
        both = pd.concat([s, prev], axis=1, join="inner")
        return ((both.iloc[:, 0] / both.iloc[:, 1] - 1) * 100).dropna()
    if how == "diff":
        return s.diff().dropna()
    if how == "mom":
        return (s.pct_change() * 100).dropna()
    return s


def _period(ts: pd.Timestamp, sid: str) -> str:
    if sid in ("DFF", "BAMLH0A0HYM2", "ICSA"):
        return ts.strftime("%Y-%m-%d")
    if sid == "A191RL1Q225SBEA":
        return f"{ts.year} Q{(ts.month - 1) // 3 + 1}"
    return ts.strftime("%Y-%m")


def _streak(values: list[float], up: bool) -> int:
    """最後連續上升（或下降）幾期。"""
    n = 0
    for i in range(len(values) - 1, 0, -1):
        if (values[i] > values[i - 1]) if up else (values[i] < values[i - 1]):
            n += 1
        else:
            break
    return n


def cards(df: pd.DataFrame) -> list[dict]:
    out = []
    for cid, region, name, sid, how, unit, dec, good, note in CARDS:
        s = transform(_series(df, sid), how)
        if s.empty:
            continue
        years = CHART_YEARS.get(sid, 10)
        tail = s[s.index >= s.index[-1] - pd.DateOffset(years=years)]
        last = round(float(s.iloc[-1]), dec)
        prev = round(float(s.iloc[-2]), dec) if len(s) >= 2 else None
        card = {"id": cid, "region": region, "name": name, "unit": unit, "dec": dec, "good": good,
                "note": note, "period": _period(s.index[-1], sid), "last": _r(last, dec),
                "prev": _r(prev, dec), "chg": _r(last - prev, dec) if prev is not None else None,
                "t": [d.strftime("%Y-%m-%d") for d in tail.index], "v": [_r(v, max(dec, 2)) for v in tail],
                "spark": [_r(v, max(dec, 2)) for v in s.tail(24)]}
        if cid == "tw_signal":
            card["light"] = light(last)
            card["lights"] = [light(v) for v in tail]
        if cid == "tw_money":
            m2 = _series(df, "tw_m2_yoy")
            m2 = m2.reindex(tail.index)
            card["name2"] = "M2 年增率"
            card["v2"] = [_r(v, 2) for v in m2]
            card["last2"] = _r(m2.iloc[-1], 2) if len(m2) and pd.notna(m2.iloc[-1]) else None
            # M1B − M2：正的是黃金交叉，cross＝目前這個狀態維持了幾個月
            gaps = [a - b for a, b in zip(card["v"], card["v2"]) if a is not None and b is not None]
            n = 0
            for g in reversed(gaps):
                if (g > 0) == (gaps[-1] > 0):
                    n += 1
                else:
                    break
            card["cross"] = n if gaps else None
        out.append(card)
    return out


def highlights(cs: list[dict]) -> list[str]:
    """總經重點（規則產生，給頁面與盤前／盤後摘要）。"""
    by = {c["id"]: c for c in cs}
    out = []
    c = by.get("tw_signal")
    if c:
        ls = c["lights"]
        n = 1
        while n < len(ls) and ls[-1 - n] == ls[-1]:
            n += 1
        chg = ("" if c.get("chg") is None else "，與上月持平" if c["chg"] == 0
               else f"，比上月 {c['chg']:+.0f} 分")
        out.append(f"{c['period']} 景氣燈號 {c['light']}（{c['last']:.0f} 分{chg}）"
                   + (f"，連續 {n} 個月{c['light']}" if n >= 2 else ""))
    c = by.get("tw_leading")
    if c and len(c["v"]) >= 3:
        up, down = _streak(c["v"], True), _streak(c["v"], False)
        if up >= 2:
            out.append(f"領先指標連續 {up} 個月上升（{c['period']} {c['last']}）")
        elif down >= 2:
            out.append(f"領先指標連續 {down} 個月下降（{c['period']} {c['last']}）")
    c = by.get("tw_pmi")
    if c:
        state = "擴張" if c["last"] >= 50 else "緊縮"
        n = 0
        for v in reversed(c["v"]):
            if (v >= 50) == (c["last"] >= 50):
                n += 1
            else:
                break
        out.append(f"製造業 PMI {c['last']}（{c['period']}），連續 {n} 個月{state}")
    c = by.get("tw_money")
    if c and c.get("last2") is not None:
        above, n = c["last"] > c["last2"], c.get("cross") or 0
        if above:
            tag = "本月黃金交叉" if n == 1 else f"黃金交叉第 {n} 個月"
        else:
            tag = "本月死亡交叉" if n == 1 else f"連續 {n} 個月"
        out.append(f"M1B 年增率 {c['last']:.2f}% {'高於' if above else '低於'} M2 {c['last2']:.2f}%"
                   f"（{c['period']}，{tag}）")
    c = by.get("tw_orders")
    if c:
        out.append(f"外銷訂單年增 {c['last']:+.1f}%（{c['period']}）")
    for cid, fmt in (("us_core_pce", "美國核心 PCE 年增 {last}%（{period}）"),
                     ("us_cpi", "美國 CPI 年增 {last}%（{period}）"),
                     ("us_nfp", "美國非農就業增加 {last:,.0f} 千人（{period}）"),
                     ("us_unemp", "美國失業率 {last}%（{period}）"),
                     ("us_ffr", "聯邦基金利率 {last}%"),
                     ("us_hy", "高收益債利差 {last}%（{period}）")):
        c = by.get(cid)
        if c:
            out.append(fmt.format(**c))
    return out


def calendar_rows(now: datetime | None = None, past: int = 10, future: int = 14) -> dict:
    """經濟日曆：最近公布（有實際值）與接下來的重要數據。"""
    from calendar_data import load_events
    from calendar_i18n import translate_country, translate_title
    from calendar_render import surprise
    cal = load_events()
    if cal.empty or "_ts" not in cal:
        return {"recent": [], "next": []}
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    cal = cal[cal["country"].isin(CAL_COUNTRIES) & cal["impact"].isin(["High", "Medium"])]

    def row(e):
        tp = e["_ts"].tz_convert("Asia/Taipei")
        return {"when": tp.strftime("%m/%d %H:%M"), "country": translate_country(e["country"]),
                "title": translate_title(e["title"]), "impact": e["impact"],
                "actual": e.get("actual", ""), "forecast": e["forecast"], "previous": e["previous"],
                "surprise": surprise(e.get("actual", ""), e["forecast"]), "better": e.get("better", "")}

    recent = cal[(cal["_ts"] <= now) & (cal["_ts"] >= now - pd.Timedelta(days=past))
                 & (cal["actual"] != "")].sort_values("_ts", ascending=False)
    nxt = cal[(cal["_ts"] > now) & (cal["_ts"] <= now + pd.Timedelta(days=future))
              & (cal["impact"] == "High")].sort_values("_ts")
    return {"recent": [row(e) for _, e in recent.head(60).iterrows()],
            "next": [row(e) for _, e in nxt.head(40).iterrows()]}


def build() -> dict:
    df = load()
    cs = cards(df)
    return {"generated": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
            "cards": cs, "highlights": highlights(cs), "calendar": calendar_rows()}
