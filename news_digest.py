"""
新聞重點：把五個來源的兩百多則壓成一份短清單

三件事：

    合併   不同媒體報導同一件事的算一則（標題的字元 2-gram 相似度）
    評分   多家報導、命中關注主題、夠新的往前排；例行的個股營收流水帳往後
    摘要   取內文第一段的前幾十個字

沒有用任何語言模型 —— 規則看得懂也改得動，而且不必把金鑰放進排程。
代價是摘要只是原文開頭，不是真的重寫。
"""
import re
from datetime import datetime, timedelta, timezone

import pandas as pd

from news_sources import SOURCE_BY_ID

TAIPEI = timezone(timedelta(hours=8))

# 這份清單決定「什麼算重要」，照自己關心的東西改
TOPICS = [
    # (權重, 名稱, 關鍵字)
    (4, "半導體 / AI", ["半導體", "晶圓", "晶片", "台積電", "先進封裝", "封測", "CoWoS",
                        "HBM", "記憶體", "DRAM", "NAND", "矽光子", "CPO", "光通訊",
                        "AI", "輝達", "NVIDIA", "GPU", "ASIC", "台積", "聯電", "日月光"]),
    (3, "台股", ["台股", "加權指數", "外資", "法人", "漲停", "跌停", "融資",
                 "權值股", "櫃買", "上市櫃", "ETF"]),
    (3, "總體經濟", ["聯準會", "Fed", "升息", "降息", "通膨", "CPI", "關稅", "貿易",
                     "匯率", "新台幣", "GDP", "央行", "G20", "利率"]),
    (2, "公司營運", ["法說", "財報", "營收", "獲利", "毛利", "EPS", "訂單", "產能",
                     "擴產", "投資", "併購", "收購", "增資"]),
    (2, "能源 / 太空", ["低軌", "衛星", "SpaceX", "電廠", "核能", "綠電", "儲能"]),
]

# 例行的個股營收流水帳：「胡連8月營收月減0.1%」這種，一天幾十則，
# 每則都只有一個數字，不該擠掉真正的新聞
ROUTINE = re.compile(r"^.{1,8}\s*\d{1,2}\s*月營收")

# 盤中／盤後的例行行情稿
ROUTINE_MARKET = re.compile(r"(台股盤[中後]|盤前掃描|早盤|收盤speed|快訊)")

# 公司自己發的公告（法說會邀請、受邀參加論壇之類），是流程不是新聞
NOTICE = re.compile(r"^【(公告|法說會|說明會|重訊)】|受邀參加|舉辦法人說明會")

# 有些站的標題前面掛著發稿時間，比對與顯示都不需要
TIME_PREFIX = re.compile(r"^\s*20\d{2}[/-]\d{1,2}[/-]\d{1,2}\s+\d{1,2}:\d{2}\s*")

# 標題裡這些字通常是釣魚式寫法，不影響內容重要性，比對前先拿掉
NOISE_CHARS = re.compile(r"[「」『』（）()【】\[\]？?！!。、，,．\.：:；;～~\-—…\s]")

# 不同媒體寫同一件事，用字差很多，門檻要鬆
MERGE_THRESHOLD = 0.22
# 同一家媒體的兩則幾乎不會是同一件事 —— 但例行稿的格式一模一樣
# （「胡連8月營收月減0.1%」對「立積8月營收月增0.7%」），鬆門檻會把它們
# 錯併成一則。同來源只在幾乎逐字相同時才合併，那是真的重複抓到。
SAME_SOURCE_THRESHOLD = 0.9
KEEP = 30                 # 重點最多留幾則
SUMMARY_LIMIT = 90        # 摘要最多幾個字


def _grams(title: str) -> set:
    """標題的字元 2-gram。中文沒有空白可切，2-gram 已經夠分辨。"""
    clean = NOISE_CHARS.sub("", title)
    return {clean[i:i + 2] for i in range(len(clean) - 1)} or {clean}


def _similar(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _topics(text: str) -> tuple[int, list]:
    """回傳 (主題加總權重, 命中的主題名稱)。"""
    score, names = 0, []
    for weight, name, words in TOPICS:
        if any(w in text for w in words):
            score += weight
            names.append(name)
    return score, names


def _fresh(published: str, now: pd.Timestamp) -> int:
    if not published:
        return 0
    ts = pd.to_datetime(published, errors="coerce", utc=True)
    if pd.isna(ts):
        return 0
    hours = (now - ts).total_seconds() / 3600
    if hours <= 12:
        return 3
    if hours <= 24:
        return 2
    if hours <= 48:
        return 1
    return 0


def _summary(body: str, title: str = "") -> str:
    """取內文第一段，太長就截斷；跟標題講一樣的話就不用再寫一次。"""
    if not body:
        return ""
    first = next((ln.strip() for ln in body.split("\n") if len(ln.strip()) > 20), "")
    if not first:
        return ""
    if title and _similar(_grams(first[:60]), _grams(title)) >= 0.5:
        return ""
    if len(first) > SUMMARY_LIMIT:
        first = first[:SUMMARY_LIMIT].rstrip("，、,. ") + "…"
    return first


def build(df: pd.DataFrame) -> list[dict]:
    """把所有來源的新聞壓成重點清單，分數高的在前。"""
    if df.empty:
        return []

    now = pd.Timestamp.now(tz="UTC")
    items = []
    for _, r in df.iterrows():
        title = TIME_PREFIX.sub("", r["title"]).strip()
        items.append({
            "source": r["source"], "n": int(float(r["order"] or 0)),
            "title": title, "url": r["url"],
            "published": r["published"], "body": r["body"],
            "grams": _grams(title),
        })

    # 同一件事合併：跟已成群的比，像就併進去
    events = []
    for item in items:
        for ev in events:
            same_source = all(m["source"] == item["source"] for m in ev["members"])
            need = SAME_SOURCE_THRESHOLD if same_source else MERGE_THRESHOLD
            if _similar(item["grams"], ev["grams"]) >= need:
                ev["members"].append(item)
                ev["grams"] |= item["grams"]
                break
        else:
            events.append({"grams": set(item["grams"]), "members": [item]})

    out = []
    for ev in events:
        # 代表作：有內文的優先，其次標題最長的（通常資訊最完整）
        members = sorted(ev["members"],
                         key=lambda m: (bool(m["body"]), len(m["title"])), reverse=True)
        lead = members[0]
        sources = []
        for m in members:
            label = SOURCE_BY_ID.get(m["source"], {}).get("label", m["source"])
            if label not in sources:
                sources.append(label)

        text = " ".join(m["title"] for m in members)
        topic_score, topics = _topics(text + lead["body"][:120])
        score = topic_score + (len(sources) - 1) * 4
        score += max(_fresh(m["published"], now) for m in members)
        if ROUTINE.match(lead["title"]):
            score -= 5
        if ROUTINE_MARKET.search(lead["title"]):
            score -= 3
        if NOTICE.search(lead["title"]):
            score -= 6

        stamps = [m["published"] for m in members if m["published"]]
        out.append({
            "title": lead["title"],
            "summary": _summary(lead["body"], lead["title"]),
            "source": lead["source"],
            "n": lead["n"],
            "url": lead["url"],
            "published": max(stamps) if stamps else "",
            "sources": sources,
            "topics": topics,
            "score": score,
            "hasBody": bool(lead["body"]),
        })

    out.sort(key=lambda e: (e["score"], e["published"]), reverse=True)
    return out[:KEEP]
