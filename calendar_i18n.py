"""
財經行事曆的中文化

ForexFactory 的事件名稱是英文，而且組合性很強：
「國別前綴 + 修飾語 + 核心指標 + 週期後綴」，例如
    German Prelim CPI m/m  →  德國 初值 消費者物價指數 月增率

因此採「完整名稱對照表 + 組字規則」兩層：
  1. TITLES 有完整對照就直接用（涵蓋目前實際出現過的名稱）
  2. 否則拆解前綴／後綴，核心詞查 TERMS
  3. 都查不到就原樣保留英文 —— 寧可顯示英文，也不要猜錯財經名詞

不使用翻譯 API：GitHub Actions 上不必管金鑰，也不會因為額度或服務中斷而壞掉。
"""
import re

# ── 貨幣／地區代碼 ─────────────────────────────────────────
COUNTRIES = {
    "USD": "美國", "EUR": "歐元區", "GBP": "英國", "JPY": "日本",
    "AUD": "澳洲", "NZD": "紐西蘭", "CAD": "加拿大", "CHF": "瑞士",
    "CNY": "中國", "HKD": "香港", "SGD": "新加坡", "KRW": "南韓",
    "TWD": "台灣", "INR": "印度", "BRL": "巴西", "MXN": "墨西哥",
    "ZAR": "南非", "RUB": "俄羅斯", "SEK": "瑞典", "NOK": "挪威",
    "All": "全球",
}

# ── 影響程度 ───────────────────────────────────────────────
IMPACTS = {
    "High": "高", "Medium": "中", "Low": "低", "Holiday": "假日",
}
IMPACT_ORDER = {"High": 3, "Medium": 2, "Low": 1, "Holiday": 0}

# ── 名稱前綴（國別／地區修飾）─────────────────────────────
PREFIXES = [
    ("German", "德國"), ("French", "法國"), ("Italian", "義大利"),
    ("Spanish", "西班牙"), ("Dutch", "荷蘭"), ("Belgian", "比利時"),
    ("Greek", "希臘"), ("Portuguese", "葡萄牙"), ("Irish", "愛爾蘭"),
]

# ── 修飾語 ─────────────────────────────────────────────────
# 中文慣例上「初值／終值／修正值／快報」放在最後（如「CPI 月增率初值」），
# 「核心／月度」則放在前面（如「核心消費者物價指數」），所以分成兩組。
LEADING_MODIFIERS = [
    ("Core", "核心"), ("Monthly", "月度"), ("Weekly", "週度"),
    ("Annual", "年度"), ("Total", "整體"),
]
TRAILING_MODIFIERS = [
    ("Flash Estimate", "快報"), ("Flash", "快報"),
    ("Prelim", "初值"), ("Preliminary", "初值"),
    ("Revised", "修正值"), ("Final", "終值"),
]

# ── 週期後綴 ───────────────────────────────────────────────
SUFFIXES = [
    ("m/m", "月增率"), ("q/q", "季增率"), ("y/y", "年增率"), ("q/y", "季年增率"),
]

# ── 核心指標詞 ─────────────────────────────────────────────
TERMS = {
    "CPI": "消費者物價指數",
    "PPI": "生產者物價指數",
    "GDP": "國內生產毛額",
    "PMI": "採購經理人指數",
    "Manufacturing PMI": "製造業採購經理人指數",
    "Services PMI": "服務業採購經理人指數",
    "Non-Manufacturing PMI": "非製造業採購經理人指數",
    "Construction PMI": "營建業採購經理人指數",
    "Retail Sales": "零售銷售",
    "Trade Balance": "貿易帳",
    "Goods Trade Balance": "商品貿易帳",
    "Current Account": "經常帳",
    "Employment Change": "就業人數變動",
    "Unemployment Rate": "失業率",
    "Unemployment Claims": "初領失業金人數",
    "Unemployment Change": "失業人數變動",
    "Non-Farm Employment Change": "非農就業人數",
    "ADP Non-Farm Employment Change": "ADP 非農就業人數",
    "Average Hourly Earnings": "平均時薪",
    "Consumer Confidence": "消費者信心指數",
    "Business Confidence": "企業信心指數",
    "Industrial Production": "工業生產",
    "Factory Orders": "工廠訂單",
    "Building Approvals": "建築許可",
    "Building Consents": "營建許可",
    "Housing Starts": "新屋開工",
    "Construction Spending": "營建支出",
    "Crude Oil Inventories": "原油庫存",
    "Natural Gas Storage": "天然氣庫存",
    "Household Spending": "家庭支出",
    "Private Sector Credit": "民間信貸",
    "Money Supply": "貨幣供給",
    "M4 Money Supply": "M4 貨幣供給",
    "Monetary Base": "貨幣基數",
    "Mortgage Approvals": "房貸核准件數",
    "Net Lending to Individuals": "個人淨放款",
    "Labor Productivity": "勞動生產力",
    "Nonfarm Productivity": "非農生產力",
    "Unit Labor Costs": "單位勞動成本",
    "Capital Spending": "資本支出",
    "Company Operating Profits": "企業營業利益",
    "Commodity Prices": "商品價格",
    "Overseas Trade Index": "海外貿易指數",
    "Official Cash Rate": "官方現金利率",
    "Overnight Rate": "隔夜拆款利率",
    "Beige Book": "聯準會褐皮書",
    "Bank Holiday": "銀行假日",
    "G20 Meetings": "G20 會議",
    "JOLTS Job Openings": "JOLTS 職缺數",
    "Challenger Job Cuts": "挑戰者裁員人數",
    "Consumer Price Index": "消費者物價指數",
    "Gov Budget Balance": "政府預算餘額",
    "Ivey PMI": "Ivey 採購經理人指數",
    "ISM Manufacturing PMI": "ISM 製造業採購經理人指數",
    "ISM Services PMI": "ISM 服務業採購經理人指數",
    "ISM Manufacturing Prices": "ISM 製造業物價指數",
    "GDT Price Index": "全球乳製品拍賣價格指數",
    "BRC Shop Price Index": "BRC 零售物價指數",
    "Nationwide HPI": "Nationwide 房價指數",
    "MI Inflation Gauge": "MI 通膨指標",
    "RCM/TIPP Economic Optimism": "RCM/TIPP 經濟樂觀指數",
    "API Weekly Statistical Bulletin": "API 週度原油庫存報告",
    "ANZ Business Confidence": "ANZ 企業信心指數",
    "ANZ Commodity Prices": "ANZ 商品價格",
    "Omdia Total Vehicle Sales": "Omdia 汽車總銷量",
    "RatingDog Manufacturing PMI": "RatingDog 製造業採購經理人指數",
    "RatingDog Services PMI": "RatingDog 服務業採購經理人指數",
    "Rate Statement": "利率聲明",
    "Press Conference": "記者會",
    "Monetary Policy Statement": "貨幣政策聲明",
}

# 完整名稱的例外對照（規則拼不出來、或習慣譯法不同的）
TITLES = {
    "BOC Rate Statement": "加拿大央行利率聲明",
    "BOC Press Conference": "加拿大央行記者會",
    "RBNZ Rate Statement": "紐西蘭央行利率聲明",
    "RBNZ Press Conference": "紐西蘭央行記者會",
    "RBNZ Monetary Policy Statement": "紐西蘭央行貨幣政策聲明",
    "FOMC Statement": "FOMC 會後聲明",
    "FOMC Press Conference": "FOMC 記者會",
    "FOMC Meeting Minutes": "FOMC 會議紀要",
    "Federal Funds Rate": "聯邦資金利率",
    "Main Refinancing Rate": "歐洲央行主要再融資利率",
    "ECB Press Conference": "歐洲央行記者會",
    "Monetary Policy Summary": "貨幣政策摘要",
    "Official Bank Rate": "英國央行基準利率",
    "Bank Holiday": "銀行假日",
}

# 央行／機構縮寫，用於「XXX Speaks」
INSTITUTIONS = {
    "FOMC Member": "FOMC 官員",
    "BOE Gov": "英國央行總裁",
    "BOE": "英國央行",
    "BOC Gov": "加拿大央行總裁",
    "BOC": "加拿大央行",
    "RBA Gov": "澳洲央行總裁",
    "RBA Assist Gov": "澳洲央行助理總裁",
    "RBA": "澳洲央行",
    "RBNZ Gov": "紐西蘭央行總裁",
    "RBNZ": "紐西蘭央行",
    "ECB President": "歐洲央行總裁",
    "ECB": "歐洲央行",
    "Fed Chair": "聯準會主席",
    # 國別前綴會先被拆掉，這裡只放不含國名的部分，否則會變成「德國德國央行總裁」
    "Buba President": "央行總裁",
    "SNB Chairman": "瑞士央行主席",
    "BOJ Gov": "日本央行總裁",
    "BOJ": "日本央行",
}

_AUCTION = re.compile(r"^(\d+)-y Bond Auction$")
_SPEAKS = re.compile(r"^(.*?)\s+Speaks$")


def translate_country(code: str) -> str:
    return COUNTRIES.get(code, code)


def translate_impact(impact: str) -> str:
    return IMPACTS.get(impact, impact)


def _strip_prefix(title: str) -> tuple[str, str]:
    """拆出國別前綴，回傳 (中文前綴, 其餘英文)。"""
    for en, zh in PREFIXES:
        if title.startswith(en + " "):
            return zh, title[len(en) + 1:]
    return "", title


def _strip_suffix(title: str) -> tuple[str, str]:
    """拆出週期後綴，回傳 (其餘英文, 中文後綴)。"""
    for en, zh in SUFFIXES:
        if title.endswith(" " + en):
            return title[: -(len(en) + 1)], zh
    return title, ""


def _strip_modifiers(title: str) -> tuple[str, str, str]:
    """
    拆出修飾語，回傳 (置前的中文, 置後的中文, 其餘英文)。

    英文一律寫在前面（Final Manufacturing PMI、Prelim CPI），
    但 CPI Flash Estimate 這類也會出現在後面，因此前後都要掃。
    """
    lead, trail = [], []
    changed = True
    while changed:
        changed = False
        for en, zh in LEADING_MODIFIERS:
            if title.startswith(en + " "):
                lead.append(zh); title = title[len(en) + 1:]; changed = True; break
        if changed:
            continue
        for en, zh in TRAILING_MODIFIERS:
            if title.startswith(en + " "):
                trail.append(zh); title = title[len(en) + 1:]; changed = True; break
            if title.endswith(" " + en):
                trail.append(zh); title = title[: -(len(en) + 1)]; changed = True; break
    return "".join(lead), "".join(trail), title


def translate_title(title: str) -> str:
    """把事件名稱轉成中文；無法確定的部分保留英文。"""
    title = (title or "").strip()
    if not title:
        return ""

    if title in TITLES:
        return TITLES[title]

    # 「10-y Bond Auction」→「10 年期公債標售」
    m = _AUCTION.match(title)
    if m:
        return f"{m.group(1)} 年期公債標售"

    prefix, rest = _strip_prefix(title)

    m = _AUCTION.match(rest)
    if m:
        sep = " " if prefix else ""
        return f"{prefix}{sep}{m.group(1)} 年期公債標售"

    # 「FOMC Member Waller Speaks」→「FOMC 官員 Waller 談話」
    m = _SPEAKS.match(rest)
    if m:
        who = m.group(1)
        for en, zh in sorted(INSTITUTIONS.items(), key=lambda kv: -len(kv[0])):
            if who.startswith(en + " "):
                return f"{prefix}{zh} {who[len(en) + 1:]} 談話"
            if who == en:
                return f"{prefix}{zh}談話"
        return f"{prefix}{who} 談話"

    if rest in TERMS:
        return f"{prefix}{TERMS[rest]}"

    rest, suffix = _strip_suffix(rest)
    if rest in TERMS:
        return f"{prefix}{TERMS[rest]}{suffix}"

    lead, trail, core = _strip_modifiers(rest)
    if core in TERMS:
        return f"{prefix}{lead}{TERMS[core]}{suffix}{trail}"

    # 核心詞查不到就保留英文，只把能確定的部分中文化
    out = f"{prefix}{lead}{core}{suffix}{trail}".strip()
    return out or title
