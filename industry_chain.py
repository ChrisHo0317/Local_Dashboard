"""
細產業分類（python update_data.py chain）

來源：櫃買中心「產業價值鏈資訊平台」（ic.tpex.org.tw），47 條產業鏈、上中下游與子分類，
只取本國上市、上櫃公司。一家公司常同時屬於好幾類（例如聯發科同時在 5 種 IC 設計裡），全部保留。
每週重抓一次（官方很少改），存 data/industry_chain.csv：code, chain, stage, node, sub。

補充表 industry_extra.csv（repo 根目錄，和 watchlist.csv 一樣可以自己改）：
官方分得不夠細的熱門族群（光通訊、CoWoS、散熱…），欄位 細產業,代號,名稱,備註；標示為「手動」。

頁面上的細產業名稱＝子分類（沒有子分類就用節點名稱），常見的改成習慣的叫法（晶圓製造 → 晶圓代工）；
太籠統的名稱（其他、零組件、材料…）前面加上產業鏈名稱，才不會把不相干的公司併在一起。

主要細產業（類股熱力圖一檔只能放一個位置）＝候選類別中，股價走勢和這檔最接近的那一類；
（近 60 日每日漲跌和該類其他成員平均漲跌的相關係數最高）；有手動補充的類別時優先從那些挑。
"""
from __future__ import annotations

import csv
import html
import io
import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "industry_chain.csv"
META_PATH = BASE_DIR / "data" / "industry_chain_meta.json"
EXTRA_PATH = BASE_DIR / "industry_extra.csv"
SITE = "https://ic.tpex.org.tw/"
COLUMNS = ["code", "chain", "stage", "node", "sub"]
REFRESH_DAYS = 7
CORR_DAYS = 60
MIN_GROUP = 3            # 主要細產業的候選：類別裡至少要有幾檔（自己以外）

# (產業鏈, 名稱) → 習慣的叫法
RENAME = {
    ("半導體", "晶圓製造"): "晶圓代工",
    ("半導體", "DRAM製造"): "DRAM",
    ("半導體", "生產製程及檢測設備"): "半導體設備",
    ("半導體", "IC封裝測試"): "封裝測試",
    ("半導體", "IP設計/IC設計代工服務"): "IC設計服務",
    ("半導體", "IC/晶圓製造"): "IC製造",
    ("半導體", "其他IC/二極體製造"): "二極體／其他IC製造",
    ("半導體", "IC模組"): "IC模組",
    ("半導體", "IC通路"): "IC通路",
    ("半導體", "化學品"): "半導體化學品",
    ("半導體", "基板"): "IC基板",
    ("電腦及週邊設備", "記憶體"): "記憶體模組",
    ("通信網路", "記憶體"): "記憶體模組",
    ("電腦及週邊設備", "散熱片、風扇馬達、散熱模組"): "散熱模組",
    ("電腦及週邊設備", "印表機、傳真機、掃瞄器、多功能事務機、投影機"): "事務機器",
    ("電腦及週邊設備", "隨身碟、記憶卡讀卡機"): "隨身碟／讀卡機",
    ("電腦及週邊設備", "光學鏡片、鏡頭"): "光學鏡頭",
    ("通信網路", "光通訊設備"): "光通訊",
    ("通信網路", "主/被動元件"): "通訊元件",
    ("印刷電路板", "硬板、軟板、IC載板製造"): "PCB製造",
    ("印刷電路板", "銅箔基板"): "銅箔基板（CCL）",
    ("印刷電路板", "玻璃纖維/玻纖布"): "玻纖布",
}
# 太籠統的名稱：前面加上產業鏈
GENERIC = {"其他", "零組件", "材料", "原料", "原材料", "原物料", "製造", "製造商", "銷售", "通訊", "網路",
           "IC", "中", "個人", "民間企業", "政府機構", "儲存", "系統整合", "系統整合服務", "整體解決方案",
           "領域方案", "領域解決方案", "設計開發", "軟體開發", "應用軟體", "通路經銷", "零售通路", "組裝廠",
           "控制器", "感測器", "顯示器", "監控系統", "生產製程及檢測設備", "生產製程及檢測", "零組件/材料",
           "其他零組件", "其他配件", "封裝/模組", "模組", "服務", "設備", "系統", "應用", "平台",
           "電子零組件", "金屬零件", "整車組裝", "營運管理軟體", "資料處理", "數據分析"}

log = logging.getLogger("chain")


def label(chain: str, node: str, sub: str) -> str:
    """頁面上用的細產業名稱。"""
    raw = (sub or node).strip()
    if (chain, raw) in RENAME:
        return RENAME[(chain, raw)]
    if raw in GENERIC or raw.startswith("其他"):
        return f"{chain}・{raw}"
    return raw


# ── 抓取與解析 ─────────────────────────────────────────

def _clean(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "", text)
    text = re.sub(r"<span.*", "", text, flags=re.S)        # 括號裡的舉例說明
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", "", html.unescape(text))


def _companies(block: str) -> list[tuple[str, str]]:
    """一個公司清單區塊裡的本國上市、上櫃公司。"""
    out = []
    for sec in re.split(r"<b>", block)[1:]:
        kind = sec[:sec.find("</b>")]
        if not (kind.startswith("本國上市") or kind.startswith("本國上櫃")):
            continue
        out += re.findall(r'stk_code=(\w+)"[^>]*title="([^"]*)"', sec)
    return out


def parse_chain(page: str, chain: str) -> list[tuple]:
    nodes = {nid: _clean(name) for nid, name in
             re.findall(r'id="ic_link_(\w+)" class="company-chain-panel"[^>]*>(.*?)</div>', page, re.S)}
    stage, cur = {}, ""
    for m in re.finditer(r'chain-title-panel">([^<]+)<|id="ic_link_(\w+)"', page):
        if m.group(1):
            cur = m.group(1).strip()
        elif m.group(2) and m.group(2) not in stage:
            stage[m.group(2)] = cur
    rows = []
    for part in page.split('<div id="companyList_')[1:]:
        nid = part[:part.find('"')]
        if nid not in nodes:
            continue
        subs = re.findall(r'sc_link_(\w+)" class="subchain[^"]*"><span>&#9658;</span>&nbsp;(.*?)&nbsp;\(', part)
        if subs:
            for sid, sname in subs:
                k = part.find(f'id="sc_company_{sid}"')
                if k < 0:
                    continue
                for code, _ in _companies(part[k:part.find("</table>", k)]):
                    rows.append((code, chain, stage.get(nid, ""), nodes[nid], _clean(sname)))
        else:
            for code, _ in _companies(part):
                rows.append((code, chain, stage.get(nid, ""), nodes[nid], ""))
    return rows


def fetch(logger: logging.Logger | None = None, pause: float = 0.6) -> pd.DataFrame:
    from curl_cffi import requests as cr
    lg = logger or log
    s = cr.Session(impersonate="chrome124")
    first = s.get(SITE + "introduce.php?ic=D000", timeout=60).content.decode("utf-8", "replace")
    chains = re.findall(r"<option value='(\w+)'\s*(?:selected)?\s*>([^<]+)</option>", first)
    if not chains:
        raise RuntimeError("找不到產業鏈清單（網站可能改版）")
    rows = []
    for ic, name in chains:
        page = first if ic == "D000" else s.get(SITE + f"introduce.php?ic={ic}", timeout=60).content.decode("utf-8", "replace")
        rows += parse_chain(page, name.strip())
        time.sleep(pause)
    df = pd.DataFrame(rows, columns=COLUMNS).drop_duplicates()
    # 同一個節點有子分類時，只留子分類那幾列
    has_sub = df[df["sub"] != ""].groupby(["code", "chain", "node"]).size()
    keep = [not (r.sub == "" and (r.code, r.chain, r.node) in has_sub.index) for r in df.itertuples()]
    df = df[keep].sort_values(COLUMNS).reset_index(drop=True)
    lg.info(f"細產業：{len(chains)} 條產業鏈、{df['code'].nunique()} 家公司、{len(df)} 筆歸屬")
    return df


def load() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(CSV_PATH, dtype=str).fillna("")


def update(logger: logging.Logger | None = None, force: bool = False) -> int:
    lg = logger or log
    try:
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    last = meta.get("fetched", "")
    if not force and last and date.fromisoformat(last) > date.today() - timedelta(days=REFRESH_DAYS):
        lg.info(f"細產業：{last} 抓過，{REFRESH_DAYS} 天內不重抓")
        return 0
    try:
        df = fetch(lg)
    except Exception as e:
        lg.warning(f"細產業：抓取失敗 {e.__class__.__name__}: {e}")
        return 0
    if df["code"].nunique() < 1000:          # 只抓到一部分就不覆蓋
        lg.warning(f"細產業：只抓到 {df['code'].nunique()} 家，本次不更新")
        return 0
    old = load()
    changed = not old.equals(df)
    if changed:
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(CSV_PATH, index=False, encoding="utf-8", lineterminator="\n")
    META_PATH.write_text(json.dumps({"fetched": date.today().isoformat(),
                                     "companies": int(df["code"].nunique())}, ensure_ascii=False),
                         encoding="utf-8")
    return int(changed)


# ── 手動補充表 ─────────────────────────────────────────

def load_extra() -> pd.DataFrame:
    """industry_extra.csv：細產業,代號,名稱,備註（# 開頭的列是註解）。"""
    if not EXTRA_PATH.exists():
        return pd.DataFrame(columns=["tag", "code", "name", "note"])
    lines = [l for l in EXTRA_PATH.read_text(encoding="utf-8-sig").splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    rows = []
    for r in csv.reader(io.StringIO("\n".join(lines))):
        if len(r) >= 2 and r[0].strip() and r[0].strip() != "細產業":
            code = r[1].strip()
            if code.isalnum():
                rows.append((r[0].strip(), code, r[2].strip() if len(r) > 2 else "",
                             r[3].strip() if len(r) > 3 else ""))
    return pd.DataFrame(rows, columns=["tag", "code", "name", "note"]).drop_duplicates(["tag", "code"])


# ── 整理：每檔的細產業標籤、主要細產業 ────────────────────

def tags(chain_df: pd.DataFrame | None = None, extra: pd.DataFrame | None = None) -> pd.DataFrame:
    """code, tag, chain, stage, extra（一檔一個標籤一列，同名合併）。"""
    df = load() if chain_df is None else chain_df
    ex = load_extra() if extra is None else extra
    rows = [(r.code, label(r.chain, r.node, r.sub), r.chain, r.stage, 0) for r in df.itertuples()]
    rows += [(r.code, r.tag, "手動補充", "", 1) for r in ex.itertuples()]
    out = pd.DataFrame(rows, columns=["code", "tag", "chain", "stage", "extra"])
    return out.drop_duplicates(["code", "tag"]).reset_index(drop=True)


def primary(tag_df: pd.DataFrame, returns: pd.DataFrame | None = None) -> dict:
    """
    每檔的主要細產業。returns：日期 × 代號 的日報酬（近 CORR_DAYS 日）。
    沒有報酬資料、或候選都不夠大時，用最小（最具體）的類別。
    """
    size = tag_df.groupby("tag")["code"].nunique()
    by_code = tag_df.groupby("code")["tag"].apply(list)
    members = tag_df.groupby("tag")["code"].apply(list)
    out = {}
    have = set(returns.columns) if returns is not None else set()
    # 每一類的漲跌加總與檔數先算好；某檔「其他成員平均」＝（加總 − 自己）÷（檔數 − 1）
    sums, cnts = {}, {}
    if have:
        for t, cs in members.items():
            cs = [c for c in cs if c in have]
            if len(cs) - 1 >= MIN_GROUP:
                sub = returns[cs]
                sums[t], cnts[t] = sub.sum(axis=1), sub.notna().sum(axis=1)
    extra = set(zip(tag_df.loc[tag_df["extra"] == 1, "code"], tag_df.loc[tag_df["extra"] == 1, "tag"]))
    for code, ts in by_code.items():
        cands = [t for t in ts if t in sums]
        # 手動補充的類別是特地加的：有的話優先從裡面挑
        mine_extra = [t for t in cands if (code, t) in extra]
        if mine_extra:
            cands = mine_extra
        if code in have and cands:
            mine = returns[code]
            best, best_c = None, -2.0
            for t in cands:
                n = cnts[t] - mine.notna()
                peer = (sums[t] - mine.fillna(0)) / n.where(n > 0)
                both = pd.concat([mine, peer], axis=1).dropna()
                if len(both) < 20:
                    continue
                c = both.iloc[:, 0].corr(both.iloc[:, 1])
                if pd.notna(c) and c > best_c:
                    best, best_c = t, c
            if best:
                out[code] = best
                continue
        out[code] = min(ts, key=lambda t: (size[t], t))
    return out


def daily_returns(panel: pd.DataFrame, days: int = CORR_DAYS) -> pd.DataFrame:
    dates = sorted(panel["date"].unique())[-(days + 1):]
    closes = panel[panel["date"].isin(dates)].pivot_table(index="date", columns="code", values="close")
    return closes.sort_index().pct_change().iloc[1:]


def site_json(tag_df: pd.DataFrame, prim: dict, codes: set | None = None) -> dict:
    """data/chains.json：tags=[[名稱, 產業鏈, 上中下游, 手動, 檔數]]、codes={代號: [標籤序號…（主要的排第一）]}。"""
    df = tag_df if codes is None else tag_df[tag_df["code"].isin(codes)]
    info = df.groupby("tag").agg(chain=("chain", "first"), stage=("stage", "first"),
                                 extra=("extra", "max"), n=("code", "nunique")).reset_index()
    info = info.sort_values(["chain", "tag"]).reset_index(drop=True)
    index = {t: i for i, t in enumerate(info["tag"])}
    out_codes = {}
    for code, g in df.groupby("code"):
        ts = list(g["tag"])
        p = prim.get(code)
        ts.sort(key=lambda t: (t != p, t))
        out_codes[code] = [index[t] for t in ts]
    return {"tags": [[r.tag, r.chain, r.stage, int(r.extra), int(r.n)] for r in info.itertuples()],
            "codes": out_codes}
