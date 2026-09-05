"""
財經行事曆爬蟲（FXStreet）

原本用 ForexFactory 的 JSON feed，但那個 feed 只有「本週」一種
（nextweek／thismonth 都是 404），所以永遠只看得到本週剩下的日子。
本站的 HTML 有 Cloudflare，連真實瀏覽器都會被擋成 403，抓不到月曆。

改用 FXStreet 行事曆頁背後的端點，可以指定任意區間：

    https://calendar-api.fxsstatic.com/en/api/v2/eventDates/{起}/{迄}

回傳 [{"dateUtc","countryCode","name","volatility","consensus","previous",...}]

一次抓本月 1 日到下個月底，涵蓋頁面要顯示的「過去幾天 + 未來 45 天」。

只留 HIGH 與 MEDIUM：LOW 一個月有七百多筆，多是次要國家的次要指標，
全放進頁面只會讓真正該注意的事件被淹掉。
"""
import json
import logging
from datetime import date, timedelta

from curl_cffi import requests as cffi_requests

API = "https://calendar-api.fxsstatic.com/en/api/v2/eventDates/"
SITE_URL = "https://www.fxstreet.com/economic-calendar"

KEEP_VOLATILITY = {"HIGH", "MEDIUM"}

# 來源的波動度 → 我們既有的影響程度欄位（沿用 ForexFactory 時期的字面值，
# 中文化與排序都吃這組字）
IMPACT = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low", "NONE": "Low"}


class ForexFactoryCalendarScraper:
    """名字沿用舊的，換來源不必動呼叫端；抓的是 FXStreet 的行事曆。"""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("CalendarScraper")

    def fetch_events(self) -> list[dict]:
        """
        取得本月與下個月的事件。

        回傳: [{"event_time","country","title","impact","forecast","previous"}, ...]
        失敗則回傳空串列，由呼叫端決定是否跳過更新。
        """
        today = date.today()
        start = today.replace(day=1)
        # 下個月的最後一天：跳到下下個月 1 號再退一天
        after_next = (start + timedelta(days=62)).replace(day=1)
        end = after_next - timedelta(days=1)

        url = f"{API}{start}T00:00:00Z/{end}T23:59:59Z"
        try:
            session = cffi_requests.Session(impersonate="chrome124")
            resp = session.get(
                url,
                headers={"Accept": "application/json",
                         "Origin": "https://www.fxstreet.com",
                         "Referer": SITE_URL},
                timeout=60,
            )
        except Exception as e:
            self.logger.error(f"行事曆讀取失敗: {e}")
            return []

        if resp.status_code != 200:
            self.logger.error(f"行事曆回應 HTTP {resp.status_code}")
            return []

        try:
            payload = json.loads(resp.content.decode("utf-8", errors="replace"))
        except ValueError:
            self.logger.error("行事曆回應不是 JSON（可能被擋或改版）")
            return []
        if not isinstance(payload, list):
            self.logger.error("行事曆回應格式不符（不是清單）")
            return []

        rows = []
        for item in payload:
            if item.get("volatility") not in KEEP_VOLATILITY:
                continue
            when = item.get("dateUtc") or ""
            title = (item.get("name") or "").strip()
            if not when or not title:
                continue
            rows.append({
                "event_time": when,
                "country": (item.get("countryCode") or "").strip(),
                "title": title,
                "impact": IMPACT.get(item.get("volatility"), "Low"),
                "forecast": _text(item.get("consensus"), item.get("unit")),
                "previous": _text(item.get("previous"), item.get("unit")),
            })

        self.logger.info(f"行事曆：{start} ～ {end} 取得 {len(rows)} 筆（中／高影響）")
        return rows


def _text(value, unit) -> str:
    """把數值與單位合成顯示字串；沒有值就留空。"""
    if value is None or value == "":
        return ""
    text = f"{value:g}" if isinstance(value, (int, float)) else str(value)
    if unit == "percentage":
        return text + "%"
    return text
