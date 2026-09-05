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
    # FXStreet 用的是國碼而不是貨幣碼（同一份表兩種都認，舊資料才不會變成空白）
    "US": "美國", "EMU": "歐元區", "UK": "英國", "DE": "德國", "FR": "法國",
    "IT": "義大利", "ES": "西班牙", "NL": "荷蘭", "BE": "比利時", "PT": "葡萄牙",
    "GR": "希臘", "IE": "愛爾蘭", "AT": "奧地利", "FI": "芬蘭",
    "JP": "日本", "CN": "中國", "AU": "澳洲", "NZ": "紐西蘭", "CA": "加拿大",
    "CH": "瑞士", "KR": "南韓", "TW": "台灣", "IN": "印度", "ID": "印尼",
    "SG": "新加坡", "HK": "香港", "BR": "巴西", "MX": "墨西哥", "TR": "土耳其",
    "RU": "俄羅斯", "SE": "瑞典", "NO": "挪威", "DK": "丹麥", "PL": "波蘭",
    "ZA": "南非", "SA": "沙烏地阿拉伯", "IL": "以色列", "WW": "全球",
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
    ("s.a.", "（季調）"), ("n.s.a.", "（未季調）"), ("n.s.a", "（未季調）"),
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
    # ── 換到 FXStreet 之後才出現的寫法 ──
    "Composite PMI": "綜合採購經理人指數",
    "Gross Domestic Product": "國內生產毛額",
    "Producer Price Index": "生產者物價指數",
    "Building Permits": "建築許可",
    "Real Retail Sales": "實質零售銷售",
    "Retail Sales ex Autos": "零售銷售（不含汽車）",
    "Core Retail Sales": "核心零售銷售",
    "Durable Goods Orders": "耐久財訂單",
    "Existing Home Sales": "成屋銷售",
    "New Home Sales": "新屋銷售",
    "Pending Home Sales": "待完成房屋銷售",
    "Consumer Credit Change": "消費信貸變動",
    "Business Inventories": "企業庫存",
    "Wholesale Inventories": "批發庫存",
    "Capacity Utilization": "產能利用率",
    "Import Price Index": "進口物價指數",
    "Export Price Index": "出口物價指數",
    "Current Account n.s.a.": "經常帳（未季調）",
    "AiG Industry Index": "AiG 產業指數",
    "Interest Rate Decision": "利率決議",
    "Consumer Confidence Index": "消費者信心指數",
    "Economic Sentiment Indicator": "經濟景氣指標",
    "Industrial Confidence": "工業信心指數",
    "Services Sentiment": "服務業景氣指數",
    "Initial Jobless Claims": "初次申請失業救濟金人數",
    "Continuing Jobless Claims": "續領失業救濟金人數",
    "Nonfarm Payrolls": "非農就業人數",
    "ADP Employment Change": "ADP 就業人數變動",
    "ADP Employment Change 4-week average": "ADP 就業人數變動 四週平均",
    "Net Change in Employment": "就業人數淨變動",
    "Participation Rate": "勞動參與率",
    "Part-Time Employment": "兼職就業人數",
    "Full-Time Employment": "全職就業人數",
    "U6 Underemployment Rate": "U6 廣義失業率",
    "Unemployment Rate s.a.": "失業率（季調）",
    "Personal Spending": "個人消費支出",
    "Personal Income": "個人所得",
    "Retail Sales Control Group": "零售銷售控制組",
    "Trade Balance s.a.": "貿易餘額（季調）",
    "Trade Balance USD": "貿易餘額（美元）",
    "Trade Balance CNY": "貿易餘額（人民幣）",
    "Gross Domestic Product Annualized": "國內生產毛額 年化",
    "Consumer Inflation Expectations": "消費者通膨預期",
    "Michigan Consumer Sentiment Index": "密西根大學消費者信心指數",
    "Michigan Consumer Expectations Index": "密西根大學消費者預期指數",
    "UoM 1-year Consumer Inflation Expectations": "密西根大學 1 年期通膨預期",
    "UoM 5-year Consumer Inflation Expectation": "密西根大學 5 年期通膨預期",
    "ZEW Survey – Economic Sentiment": "ZEW 經濟景氣指數",
    "ZEW Survey – Expectations": "ZEW 景氣預期指數",
    "ZEW Survey – Current Situation": "ZEW 現況指數",
    "Sentix Investor Confidence": "Sentix 投資人信心指數",
    "Westpac Consumer Confidence": "Westpac 消費者信心指數",
    "Philadelphia Fed Manufacturing Survey": "費城聯準銀製造業指數",
    "Nondefense Capital Goods Orders ex Aircraft": "非國防資本財訂單（不含飛機）",
    "IMF Meeting": "IMF 會議",
    "RBNZ Interest Rate Decision": "紐西蘭央行利率決議",
    "RBNZ Monetary Policy Review": "紐西蘭央行貨幣政策檢討",
    "PBoC Interest Rate Decision": "中國人民銀行利率決議",

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
_SPEAKS = re.compile(r"^(.*?)\s+(?:Speaks|speech)$")

# 來源寫法的正規化（見 normalize）。順序有意義：先拆括號裡的週期，
# 再處理機構前綴，最後收拾多餘空白。
_NORMALIZE = [
    (re.compile(r"\s*\(YoY\)", re.I), " y/y"),
    (re.compile(r"\s*\(MoM\)", re.I), " m/m"),
    (re.compile(r"\s*\(QoQ\)", re.I), " q/q"),
    (re.compile(r"\s*\(WoW\)", re.I), " w/w"),
    (re.compile(r"\s*\(YTD\)", re.I), " 年初至今"),
    # PMI 的編製機構：名稱不同但講的是同一個指標
    (re.compile(r"^(S&P Global|HCOB|Judo Bank|Jibun Bank|au Jibun Bank|Caixin|"
                r"RatingDog|ISM|NBS|Ai Group|BusinessNZ|SVME|HSBC|Markit)\s+", re.I), ""),
    # 「Consumer Price Index (CPI)」這種括號縮寫是重複資訊
    (re.compile(r"\s*\((CPI|PPI|GDP|PMI|PCE|CPIF|HICP)\)", re.I), ""),
    (re.compile(r"\s{2,}"), " "),
]


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


def normalize(title: str) -> str:
    """把來源的寫法整理成規則吃得下的樣子。

    FXStreet 的名稱格式跟原本的 ForexFactory 不同：週期寫成「(YoY)」而不是
    「y/y」，PMI 前面還會掛編製機構（S&P Global、HCOB、Judo Bank…）。
    不先正規化的話，同一個指標會因為寫法不同而整批查不到。
    """
    title = (title or "").strip()
    for pattern, repl in _NORMALIZE:
        title = pattern.sub(repl, title)
    return title.strip()


def translate_title(title: str) -> str:
    """把事件名稱轉成中文；無法確定的部分保留英文。"""
    title = normalize(title)
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
