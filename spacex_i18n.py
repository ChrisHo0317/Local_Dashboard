"""
SpaceX 發射資料的中文化

來源的欄位取值範圍很小（火箭 4 種、任務類型 9 種、回收方式 6 種、
發射場約 10 個），所以直接用對照表；任務名稱則以規則處理
（「X Mission」→「X 任務」），查不到的部分原樣保留英文。
"""
import re

# ── 火箭 ───────────────────────────────────────────────────
VEHICLES = {
    "Falcon 9": "獵鷹 9 號",
    "Falcon Heavy": "重型獵鷹",
    "Falcon 1": "獵鷹 1 號",
    "Starship": "星艦",
}

# ── 任務類型 ───────────────────────────────────────────────
MISSION_TYPES = {
    "starlink": "星鏈",
    "commercialSatellite": "商業衛星",
    "nssl": "國安太空發射",
    "resupply": "太空站補給",
    "rideshare": "共乘發射",
    "hsf": "載人航太",
    "science": "科學任務",
    "starship": "星艦",
}

# ── 回收方式 ───────────────────────────────────────────────
RETURN_SITES = {
    "Droneship": "無人回收船",
    "Landing Zone": "陸上著陸區",
    "Expended": "不回收",
    "Landing Zone / Expended": "陸上著陸區／不回收",
    "Landing Zone, Droneship": "陸上著陸區＋無人船",
    "Mechazilla": "發射塔夾臂回收",
}

# ── 發射場 ─────────────────────────────────────────────────
# 值有時帶尾端空白或缺少州名，正規化後再查
LAUNCH_SITES = {
    "SLC-40, Florida": "SLC-40，佛羅里達",
    "SLC-4E, California": "SLC-4E，加州",
    "LC-39A, Florida": "LC-39A，佛羅里達",
    "Pad 1, Starbase": "Starbase 1 號發射台",
    "Pad 2, Starbase": "Starbase 2 號發射台",
    "Starbase, Texas": "Starbase，德州",
    "Omelek Island": "歐姆雷克島",
    "SLC-4E": "SLC-4E，加州",
    "Kwajalein Atoll": "瓜加林環礁",
}

# ── 任務狀態 ───────────────────────────────────────────────
STATUSES = {
    "upcoming": "即將發射",
    "in-progress": "進行中",
    "final": "已完成",
}
# 狀態的重要性，供篩選使用（數字越大越重要）
STATUS_RANK = {"upcoming": 3, "in-progress": 3, "final": 1}

# ── 任務名稱裡常見的專有名詞 ───────────────────────────────
# 只收「中文媒體確實有慣用譯名」的；Crew-12、CRS-5、Transporter-15 這類
# 中文報導本來就沿用原名，硬翻反而不好認，一律保留原文。
MISSION_TERMS = {
    "Starlink": "星鏈",
    "Polaris Dawn": "北極星黎明",
    "Roman Space Telescope": "羅曼太空望遠鏡",
    "Europa Clipper": "歐羅巴快船",
    "Psyche": "普賽克",
}

_MISSION = re.compile(r"^(.*?)\s+Mission$", re.I)


def translate_vehicle(value: str) -> str:
    return VEHICLES.get((value or "").strip(), value or "")


def translate_mission_type(value: str) -> str:
    return MISSION_TYPES.get((value or "").strip(), value or "")


def translate_return_site(value: str) -> str:
    return RETURN_SITES.get((value or "").strip(), value or "")


def translate_launch_site(value: str) -> str:
    key = " ".join((value or "").split())      # 收掉多餘空白
    return LAUNCH_SITES.get(key, key)


def translate_status(value: str) -> str:
    return STATUSES.get((value or "").strip(), value or "")


def status_rank(value: str) -> int:
    return STATUS_RANK.get((value or "").strip(), 1)


def translate_title(title: str) -> str:
    """
    任務名稱。來源大小寫不一致（Starlink Mission / STARLINK MISSION /
    starlink mission 都有），先正規化再處理。
    """
    raw = " ".join((title or "").split())
    if not raw:
        return ""

    # 不動大小寫：專有名詞表本來就是忽略大小寫比對的，
    # 硬套 title() 會把 IM-2 變成 Im-2。
    m = _MISSION.match(raw)
    body = m.group(1) if m else raw

    for en, zh in sorted(MISSION_TERMS.items(), key=lambda kv: -len(kv[0])):
        if body.lower() == en.lower():
            body = zh
            break
        if body.lower().startswith(en.lower() + "-"):
            body = zh + body[len(en):]
            break

    if not m:
        return body
    # 中文名後面不加空格（星鏈任務），英文名才加（Crew-12 任務）
    sep = "" if body and "一" <= body[-1] <= "鿿" else " "
    return f"{body}{sep}任務"
