"""
財經行事曆爬蟲（ForexFactory）

forexfactory.com 本站有 Cloudflare，直接抓會 403；但官方另外提供 JSON feed：

    https://nfs.faireconomy.media/ff_calendar_thisweek.json

回傳 [{"title","country","date","impact","forecast","previous"}, ...]
date 是 ISO 8601 含時區（來源為紐約時間，如 2026-09-04T08:30:00-04:00）。

兩個要注意的地方：

1. 只有「本週」這一個 feed —— nextweek／lastweek／thismonth 都是 404。
   所以看得到的未來事件僅限本週剩下的日子，歷史則靠每天執行逐週累積。

2. 這個端點有速率限制。短時間連續抓會回 HTTP 429 加 Retry-After，
   內容是 HTML 而不是 JSON。每次執行只抓一次，遇到 429 就跳過本次更新。
"""
import json
import logging

from curl_cffi import requests as cffi_requests

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
SITE_URL = "https://www.forexfactory.com/calendar"


class ForexFactoryCalendarScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("ForexFactoryCalendarScraper")

    def fetch_events(self) -> list[dict]:
        """
        取得本週事件。

        回傳: [{"event_time","country","title","impact","forecast","previous"}, ...]
        失敗（含被限流）則回傳空串列，由呼叫端決定是否跳過更新。
        """
        try:
            session = cffi_requests.Session(impersonate="chrome124")
            resp = session.get(
                FEED_URL,
                headers={"Accept": "application/json", "Referer": SITE_URL},
                timeout=40,
            )
        except Exception as e:
            self.logger.error(f"ForexFactory feed 讀取失敗: {e}")
            return []

        if resp.status_code == 429:
            wait = resp.headers.get("retry-after", "?")
            self.logger.warning(f"ForexFactory feed 被限流（HTTP 429，Retry-After {wait}s），本次跳過")
            return []
        if resp.status_code != 200:
            self.logger.error(f"ForexFactory feed 回應 HTTP {resp.status_code}")
            return []

        try:
            payload = json.loads(resp.content.decode("utf-8", errors="replace"))
        except ValueError:
            self.logger.error("ForexFactory feed 未回傳 JSON（可能被限流或改版）")
            return []

        if not isinstance(payload, list):
            self.logger.error(f"ForexFactory feed 格式非預期: {type(payload).__name__}")
            return []

        rows = []
        for e in payload:
            when = (e.get("date") or "").strip()
            title = (e.get("title") or "").strip()
            if not when or not title:
                continue
            rows.append({
                "event_time": when,
                "country": (e.get("country") or "").strip(),
                "title": title,
                "impact": (e.get("impact") or "").strip(),
                "forecast": (e.get("forecast") or "").strip(),
                "previous": (e.get("previous") or "").strip(),
            })

        if rows:
            days = sorted({r["event_time"][:10] for r in rows})
            self.logger.info(
                f"ForexFactory：{len(rows)} 筆事件，{days[0]} ～ {days[-1]}"
            )
        else:
            self.logger.warning("ForexFactory feed 沒有回傳任何事件")
        return rows
