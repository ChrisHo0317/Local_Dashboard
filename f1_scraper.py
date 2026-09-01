"""
F1 賽程爬蟲（f1calendar.com）

資料來源頁面：https://f1calendar.com/zh-HK

站上的表格只顯示「6 Mar 01:30」這種沒有年份、也沒標時區的字串，不能直接用。
但 Next.js 的 RSC payload 裡有完整的結構化資料，時間是 UTC，直接取那份：

    {"year":"2026","races":[
      {"name":"Australian","location":"Melbourne","round":1,
       "localeKey":"australian-grand-prix",
       "sessions":{"fp1":"2026-03-06T01:30:00Z", ..., "gp":"2026-03-08T04:00:00Z"}},
      ...]}

同一份 payload 裡另有繁體中文的對照表（因為抓的是 zh-HK 版）：
賽事以 localeKey 對應（australian-grand-prix → 澳洲大獎賽），
場次以代碼對應（fp1 → 第一節練習賽、qualifying → 排位賽、gp → 大獎賽）。
中文名稱以來源為準，只在兩種情況介入：來源沒收錄的賽事，以及港式用字改成台灣寫法。
"""
import json
import logging
import re

from curl_cffi import requests as cffi_requests

PAGE_URL = "https://f1calendar.com/zh-HK"

# 來源只有 zh-HK 版（zh-TW / zh-Hant 都會 307 轉址），用的是港式譯名。
# 這裡只換成台灣慣用寫法，用詞替換而非整名對照，複合名稱（如「托斯卡尼(意大利)大獎賽」）
# 也會一起改到。
TW_TERMS = {
    "意大利": "義大利",
    "阿塞拜疆": "亞塞拜然",
    "卡塔爾": "卡達",
    "阿布扎比": "阿布達比",
    "沙特阿拉伯": "沙烏地阿拉伯",
    "新西蘭": "紐西蘭",
}

# 來源的對照表沒有收錄的賽事（多半是當季新賽名），自己補上
FALLBACK_RACES = {
    "barcelona-catalunya-grand-prix": "巴塞隆納大獎賽",
}

# 場次代碼 → 中文的備援（頁面若改版抓不到對照表時才用）
FALLBACK_SESSIONS = {
    "fp1": "第一節練習賽", "fp2": "第二節練習賽", "fp3": "第三節練習賽",
    "qualifying": "排位賽", "sprint": "衝刺賽",
    "sprintQualifying": "衝刺排位賽", "gp": "大獎賽",
}


class F1CalendarScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("F1CalendarScraper")

    def fetch_schedule(self) -> list[dict]:
        """
        回傳: [{"event_time","round","race","location","session","session_key"}, ...]
        失敗則回傳空串列，由呼叫端決定是否跳過更新。
        """
        try:
            session = cffi_requests.Session(impersonate="chrome124")
            resp = session.get(
                PAGE_URL,
                headers={"Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"},
                timeout=40,
            )
            resp.raise_for_status()
        except Exception as e:
            self.logger.error(f"f1calendar 頁面讀取失敗: {e}")
            return []

        # RSC payload 是把 JSON 再字串化塞進 JS，引號都被跳脫過
        raw = resp.text.replace('\\"', '"')

        races = self._extract_races(raw)
        if not races:
            return []

        race_names = self._extract_map(raw, [r.get("localeKey", "") for r in races])
        session_names = self._drop_collisions(
            self._extract_map(raw, list(FALLBACK_SESSIONS))
        )

        rows = []
        for race in races:
            key = race.get("localeKey") or race.get("slug") or ""
            zh_race = (race_names.get(key) or FALLBACK_RACES.get(key)
                       or race.get("name") or key)
            for hk, tw in TW_TERMS.items():
                zh_race = zh_race.replace(hk, tw)
            for skey, when in (race.get("sessions") or {}).items():
                if not when:
                    continue
                rows.append({
                    "event_time": when,
                    "round": str(race.get("round", "")),
                    "race": zh_race,
                    "location": race.get("location", ""),
                    "session": session_names.get(skey) or FALLBACK_SESSIONS.get(skey, skey),
                    "session_key": skey,
                })

        if rows:
            days = sorted({r["event_time"][:10] for r in rows})
            self.logger.info(
                f"f1calendar：{len(races)} 站、{len(rows)} 個場次，{days[0]} ～ {days[-1]}"
            )
        else:
            self.logger.warning("f1calendar 沒有解析出任何場次")
        return rows

    def _extract_races(self, raw: str) -> list[dict]:
        """從 payload 取出 races 陣列。"""
        m = re.search(r'\{"year":"(\d{4})","races":\[', raw)
        if not m:
            self.logger.error("f1calendar：找不到 races 資料（頁面可能改版）")
            return []

        start = raw.index("[", m.end() - 1)
        depth, i = 0, start
        while i < len(raw):
            if raw[i] == "[":
                depth += 1
            elif raw[i] == "]":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            self.logger.error("f1calendar：races 陣列不完整")
            return []

        try:
            races = json.loads(raw[start:i + 1])
        except ValueError as e:
            self.logger.error(f"f1calendar：races 解析失敗 {e}")
            return []

        self.logger.info(f"f1calendar：{m.group(1)} 年賽季，共 {len(races)} 站")
        return races

    @staticmethod
    def _drop_collisions(mapping: dict) -> dict:
        """
        丟掉「多個代碼對到同一個名稱」的項目，改交給 FALLBACK_SESSIONS。

        來源的 zh-HK 對照把 sprint 與 sprintQualifying 都寫成「衝刺排位賽」，
        兩者一個是週六的衝刺賽、一個是週五的衝刺排位賽，混在一起看不出差別。
        """
        by_value = {}
        for key, value in mapping.items():
            by_value.setdefault(value, []).append(key)
        return {k: v for k, v in mapping.items() if len(by_value[v]) == 1}

    @staticmethod
    def _extract_map(raw: str, keys: list[str]) -> dict:
        """
        在 payload 裡找 "<key>":"<中文>" 形式的對照。

        必須確認值含中文才採用：races 陣列裡也有 "fp1":"2026-03-06T01:30:00Z"
        這種同名的鍵，而且出現在對照表之前，不檢查的話會抓到時間戳。
        """
        out = {}
        for key in keys:
            if not key:
                continue
            for m in re.finditer('"' + re.escape(key) + '"\\s*:\\s*"([^"]{1,40})"', raw):
                value = m.group(1)
                if any("一" <= ch <= "鿿" for ch in value):
                    out[key] = value
                    break
        return out


# ─────────────────────────────────────────────────────────────
# 車手／車隊積分榜（f1-boxbox.com）
# ─────────────────────────────────────────────────────────────
STANDINGS_URL = "https://f1-boxbox.com/zh-tw/formula-1/{year}/standings"

# 站上的中文名簡繁混雜（「阿蘭·普羅斯特」是正體、「乔治·拉塞尔」是簡體），
# 用 OpenCC 統一轉成台灣正體。沒裝 opencc 時就原樣保留。
try:
    from opencc import OpenCC
    _CC = OpenCC("s2twp")
except Exception:                                   # pragma: no cover
    _CC = None


def _num(value) -> str:
    """來源對「0 勝／0 頒獎台」的車手直接省略該欄位，沒有就是 0。"""
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "0"


def _to_tw(text: str) -> str:
    if not text or _CC is None:
        return text
    try:
        return _CC.convert(text)
    except Exception:
        return text


class F1StandingsScraper:
    """
    抓 f1-boxbox.com 的車手與車隊積分榜。

    頁面的 RSC payload 裡有結構化的 driverStandings / constructorStandings
    （名次、積分、勝場、頒獎台、名次升降），但名字是英文；
    中文名則在渲染後的 HTML 連結文字裡：

        <a href="/zh-tw/formula-1/drivers/kimi-antonelli">基米·安托內利</a>
        <a href="/zh-tw/formula-1/teams/mercedes">梅賽德斯</a>

    兩邊以 id 對起來，就能得到「中文名 + 完整數據」。
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("F1StandingsScraper")

    def fetch(self, year: int) -> dict:
        """
        一次取回積分榜與逐站積分走勢（同一個頁面就有，不必抓兩次）。

        回傳 {"standings": [...], "series": [...]}；失敗則兩者皆為空串列。
        """
        html = self._fetch_html(year)
        if not html:
            return {"standings": [], "series": []}
        return {
            "standings": self._parse_standings(html),
            "series": self._parse_series(html),
        }

    def fetch_standings(self, year: int) -> list[dict]:
        """只要積分榜時用這個。"""
        return self.fetch(year)["standings"]

    def _fetch_html(self, year: int) -> str:
        """"""
        try:
            session = cffi_requests.Session(impersonate="chrome124")
            resp = session.get(
                STANDINGS_URL.format(year=year),
                headers={"Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"},
                timeout=40,
            )
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            self.logger.error(f"f1-boxbox 頁面讀取失敗: {e}")
            return ""

    def _parse_standings(self, html: str) -> list[dict]:
        raw = html.replace('\\"', '"')

        drivers = self._grab_array(raw, "driverStandings")
        teams = self._grab_array(raw, "constructorStandings")
        if not drivers and not teams:
            self.logger.error("f1-boxbox：找不到積分榜資料（頁面可能改版）")
            return []

        driver_zh = self._link_names(html, "drivers")
        team_zh = self._link_names(html, "teams")

        rows = []
        for d in drivers:
            rows.append({
                "kind": "driver",
                "position": str(d.get("positionText") or d.get("positionDisplayOrder", "")),
                "name": driver_zh.get(d.get("id", ""), "") or d.get("name", ""),
                "name_en": d.get("name", ""),
                "team": team_zh.get(d.get("constructorId", ""), "") or d.get("constructorName", ""),
                "points": _num(d.get("points")),
                "wins": _num(d.get("wins")),
                "podiums": _num(d.get("podiums")),
                "gained": _num(d.get("positionsGained")),
            })
        for t in teams:
            rows.append({
                "kind": "constructor",
                "position": str(t.get("positionText") or t.get("positionDisplayOrder", "")),
                "name": team_zh.get(t.get("id", ""), "") or t.get("name", ""),
                "name_en": t.get("name", ""),
                "team": "",
                "points": _num(t.get("points")),
                "wins": _num(t.get("wins")),
                "podiums": _num(t.get("podiums")),
                "gained": _num(t.get("positionsGained")),
            })

        self.logger.info(
            f"f1-boxbox：{len(drivers)} 位車手、{len(teams)} 支車隊"
        )
        return rows

    def _parse_series(self, html: str) -> list[dict]:
        """
        逐站累積積分（冠軍積分走勢圖用）。

        driverStandingsTimeSeries / constructorStandingsTimeSeries 每筆是
        「某人在第 N 站結束後的累積積分」，名字同樣是英文，用連結文字補中文。
        """
        raw = html.replace('\\"', '"')
        driver_zh = self._link_names(html, "drivers")
        team_zh = self._link_names(html, "teams")

        rows = []
        for key, kind, zh_map, id_field in (
            ("driverStandingsTimeSeries", "driver", driver_zh, "driverId"),
            ("constructorStandingsTimeSeries", "constructor", team_zh, "constructorId"),
        ):
            for e in self._grab_array(raw, key):
                ident = e.get(id_field) or e.get("id") or ""
                rows.append({
                    "kind": kind,
                    "round": _num(e.get("round")),
                    "id": str(ident),
                    "name": zh_map.get(str(ident), "") or e.get("name", ""),
                    "points": _num(e.get("points")),
                })

        if rows:
            rounds = {int(r["round"]) for r in rows if r["round"].isdigit()}
            self.logger.info(
                f"f1-boxbox：積分走勢 {len(rows)} 筆，第 {min(rounds)} ～ {max(rounds)} 站"
            )
        return rows

    def _grab_array(self, raw: str, key: str) -> list[dict]:
        m = re.search('"' + key + '"' + r'\s*:\s*\[', raw)
        if not m:
            return []
        start = raw.index("[", m.end() - 1)
        depth, i = 0, start
        while i < len(raw):
            if raw[i] == "[":
                depth += 1
            elif raw[i] == "]":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            return []
        try:
            return json.loads(raw[start:i + 1])
        except ValueError as e:
            self.logger.error(f"f1-boxbox：{key} 解析失敗 {e}")
            return []

    @staticmethod
    def _link_names(html: str, section: str) -> dict:
        """從 <a href=".../drivers/<id>">中文名</a> 取出 id → 中文名。"""
        out = {}
        pattern = r'href="/[^"]*/' + section + r'/([a-z0-9-]+)"[^>]*>([^<]{1,30})</a>'
        for m in re.finditer(pattern, html):
            name = m.group(2).strip()
            if name and any("一" <= c <= "鿿" for c in name):
                out.setdefault(m.group(1), _to_tw(name))
        return out
