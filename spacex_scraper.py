"""
SpaceX 發射資料爬蟲

https://www.spacex.com/launches 是純前端渲染的空殼（HTML 只有 3KB），
資料來自官網自己呼叫的 API：

    https://content.spacex.com/api/spacex-website/launches-page-tiles
        整份清單（含歷史），每筆有 title / vehicle / launchSite / returnSite /
        launchDate / launchTime / missionType / missionStatus
    https://sxcontent9668.azureedge.us/cms-assets/future_missions.json
        即將發射任務的精確時間（epoch 秒），以 correlationId 對應

要注意的地方：

- **官網一次只公布一場即將發射的任務**，而且那一筆的 launchDate 是 null，
  精確時間要去 future_missions.json 取。所以「發射排程」實際上是
  「一場即將發射 + 歷史紀錄」，不是完整的未來排程表。
- launchDate／launchTime 是分開的兩個欄位，且沒有標時區。對照官網顯示，
  這是發射場當地時間；但來源沒給時區，硬套會出錯，因此一律當成 UTC 存，
  由頁面統一換算顯示（誤差最多幾小時，對「哪一天發射」的判讀不影響）。
- 任務名稱大小寫不一致（Starlink Mission / STARLINK MISSION / starlink mission
  都有），中文化時會先正規化。
"""
import json
import logging
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

TILES_URL = "https://content.spacex.com/api/spacex-website/launches-page-tiles"
FUTURE_URL = "https://sxcontent9668.azureedge.us/cms-assets/future_missions.json"
PAGE_URL = "https://www.spacex.com/launches"


class SpaceXScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("SpaceXScraper")

    def fetch_launches(self) -> list[dict]:
        """
        回傳: [{"launch_time","title","vehicle","launch_site","return_site",
                "mission_type","status","link"}, ...]
        失敗則回傳空串列，由呼叫端決定是否跳過更新。
        """
        tiles = self._get_json(TILES_URL, "發射清單")
        if not isinstance(tiles, list) or not tiles:
            return []

        # 即將發射那一筆的精確時間（launchDate 是 null，只能從這裡拿）
        future = self._get_json(FUTURE_URL, "即將發射時間") or {}
        upcoming_ts = {}
        if isinstance(future, dict):
            for cid, item in future.items():
                secs = ((item or {}).get("PrimaryLaunchDate") or {}).get("Seconds")
                if secs:
                    upcoming_ts[cid] = datetime.fromtimestamp(int(secs), timezone.utc)

        rows = []
        for t in tiles:
            title = (t.get("title") or "").strip()
            if not title:
                continue

            when = self._launch_time(t, upcoming_ts)
            rows.append({
                "launch_time": when.strftime("%Y-%m-%dT%H:%M:%SZ") if when else "",
                "title": title,
                "vehicle": (t.get("vehicle") or "").strip(),
                "launch_site": " ".join((t.get("launchSite") or "").split()),
                "return_site": (t.get("returnSite") or "").strip(),
                "mission_type": (t.get("missionType") or "").strip(),
                "status": (t.get("missionStatus") or "").strip(),
                # 進行中的任務會帶預計返回時間，但格式是自由文字（"October 2026"）
                "return_time": (t.get("returnDateTime") or "").strip(),
                "link": (t.get("link") or "").strip(),
            })

        dated = [r for r in rows if r["launch_time"]]
        upcoming = [r for r in rows if r["status"] in ("upcoming", "in-progress")]
        self.logger.info(
            f"SpaceX：{len(rows)} 筆任務（{len(dated)} 筆有時間、"
            f"{len(upcoming)} 筆即將發射或進行中）"
        )
        return rows

    def _launch_time(self, tile: dict, upcoming_ts: dict) -> datetime | None:
        """組出發射時間；即將發射的那筆改用 future_missions 的精確時間。"""
        cid = tile.get("correlationId")
        if cid and cid in upcoming_ts:
            return upcoming_ts[cid]

        day = (tile.get("launchDate") or "").strip()
        if not day:
            return None
        clock = (tile.get("launchTime") or "00:00:00").strip() or "00:00:00"
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(f"{day} {clock}", fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            return datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def _get_json(self, url: str, what: str):
        try:
            session = cffi_requests.Session(impersonate="chrome124")
            resp = session.get(
                url,
                headers={"Accept": "application/json", "Referer": PAGE_URL},
                timeout=90,
            )
            resp.raise_for_status()
            return json.loads(resp.content.decode("utf-8", errors="replace"))
        except Exception as e:
            self.logger.error(f"SpaceX {what} 讀取失敗: {e}")
            return None
