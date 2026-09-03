"""
新聞爬蟲

清單有兩種抓法（見 news_sources）：RSS 直接解析，HTML 則從首頁挑連結。
內文一律另外抓文章頁，用同一套通用邏輯抽取 —— 各站版型不同，但共通點是
「內文段落集中在某個容器裡」，所以依序試幾個常見容器，取 <p> 文字最長的那個。

不逐站寫死選擇器：那種寫法在對方改版時會安靜地抓到空字串，而通用策略
至少會挑到「最像內文」的區塊。抽不到內文時就留空，頁面照樣列出標題與連結。
"""
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from news_sources import BODY_LIMIT, PER_SOURCE, SOURCES

HEADERS = {"Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}

TAIPEI = timezone(timedelta(hours=8))

# 文章頁裡標示發布時間的 meta 名稱
PUB_META = re.compile(r"(article:published_time|pubdate|publishdate|date|"
                      r"datepublished|parsely-pub-date|sailthru\.date)")

# 版面上直接印出來的日期時間，例如「2026-09-02 15:15」或「2026/09/02 15:15」
PUB_TEXT = re.compile(r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}")

# 依序試這些容器，取其中 <p> 文字最長的
BODY_SELECTORS = [
    "article",
    "[itemprop=articleBody]",
    "[class*=article]",
    "[class*=content]",
    "[class*=text]",
    "main",
]

# 抽到的文字短於這個長度就當成沒抓到（多半是導覽或版權字串）
MIN_BODY = 100

# 連續抓同一站的內文之間隔多久（秒）。單篇都抓得到、連抓卻空一半，
# 就是被限流了 —— 間隔比事後重試有效得多。
REQUEST_GAP = 0.5

# 雜訊過濾只套用在短段落：長段落即使夾了一個關鍵字（文末的訂閱／廣告字樣）
# 也是真正的內文，整段丟掉會把文章刪光。導覽與版權宣告都遠短於這個長度。
NOISE_MAX_LEN = 150

# 付費牆：有些站（DIGITIMES）只公開導言，後面直接在同一段接上入會導購文字。
# 遇到這些字樣就從那裡截斷，不要把導購文字當成內文。
PAYWALL = re.compile(r"(會員登入|會員服務申請|立即訂閱|訂閱看全文|加入會員|閱讀全文)")

# 內文裡常見的雜訊段落，整段丟掉
NOISE = re.compile(
    r"(不用抽|不用搶|下載APP|加入.*粉絲團|延伸閱讀|相關新聞|更多內容|請繼續往下閱讀|"
    r"點我下載|訂閱|版權所有|未經授權|禁止轉載|Copyright|廣告|"
    r"會員登入|會員服務|申請專線|會員信箱|試用申請)"
)


class NewsScraper:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("NewsScraper")
        self.session = cffi_requests.Session(impersonate="chrome124")

    # ── 對外 ────────────────────────────────────────────────
    def fetch_all(self) -> list[dict]:
        """抓所有來源，回傳合併後的文章列表。單一來源失敗不影響其他來源。"""
        rows = []
        for source in SOURCES:
            try:
                got = self.fetch_source(source)
            except Exception as e:
                self.logger.error(f"{source['label']}：抓取失敗 {e}")
                continue
            rows.extend(got)
        return rows

    def fetch_source(self, source: dict) -> list[dict]:
        readers = {"rss": self._from_rss, "html": self._from_html, "wp": self._from_wp}
        items = readers[source["kind"]](source)
        # 同一則新聞可能以不同網址在清單上出現兩次（不同分類或不同排版位置），
        # 標題比網址可靠，用它再過一次。
        seen, unique = set(), []
        for item in items:
            key = item["title"]
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        items = unique[:PER_SOURCE]
        if not items:
            self.logger.warning(f"{source['label']}：清單沒有抓到任何文章")
            return []

        rows = []
        for order, item in enumerate(items):
            published = item.get("published", "")
            if "body" in item:              # WP API 已經把內文一起帶回來了
                body = item["body"]
            else:
                if order:
                    time.sleep(REQUEST_GAP)  # 連抓幾十篇會被限流，隔一下
                body, found = self._fetch_article(item["url"])
                # 清單上沒有時間的來源（HTML 清單），時間得從文章頁拿
                published = published or found
            rows.append({
                "source": source["id"],
                "order": str(order),
                "title": item["title"],
                "url": item["url"],
                "published": published,
                "body": body,
            })

        with_body = sum(1 for r in rows if r["body"])
        self.logger.info(
            f"{source['label']}：{len(rows)} 則（{with_body} 則取得內文）"
        )
        return rows

    # ── 清單 ────────────────────────────────────────────────
    def _from_rss(self, source: dict) -> list[dict]:
        out = []
        for url in source["list_urls"]:
            out.extend(self._one_rss(source, url))
        return out

    def _one_rss(self, source: dict, list_url: str) -> list[dict]:
        raw = self._get(list_url)
        if not raw:
            return []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            self.logger.error(f"{source['label']}：RSS 解析失敗 {e}")
            return []

        out = []
        # RSS 2.0 是 channel/item，Atom 是 entry
        for node in root.iter():
            tag = node.tag.split("}")[-1]
            if tag not in ("item", "entry"):
                continue
            title = self._text(node, "title")
            link = self._text(node, "link")
            if not link:                                  # Atom 的 link 在屬性上
                for child in node:
                    if child.tag.split("}")[-1] == "link" and child.get("href"):
                        link = child.get("href")
                        break
            if not title or not link:
                continue
            out.append({
                "title": title,
                "url": link,
                "published": self._iso(self._text(node, "pubDate")
                                       or self._text(node, "published")
                                       or self._text(node, "updated")),
            })
        return out

    def _from_wp(self, source: dict) -> list[dict]:
        """WordPress REST API：標題、連結、時間、內文一次到手。"""
        out = []
        for url in source["list_urls"]:
            raw = self._get(url)
            if not raw:
                continue
            try:
                posts = json.loads(raw)
            except ValueError as e:
                self.logger.error(f"{source['label']}：JSON 解析失敗 {e}")
                continue
            for post in posts:
                title = unescape(re.sub(r"<[^>]+>", "",
                                        post.get("title", {}).get("rendered", ""))).strip()
                link = post.get("link", "")
                if not title or not link:
                    continue
                html = post.get("content", {}).get("rendered", "")
                out.append({
                    "title": title,
                    "url": link,
                    "published": self._iso(post.get("date_gmt", "") + "Z"),
                    "body": self._clean_body(
                        self._paragraphs(BeautifulSoup(html, "html.parser"))),
                })
        return out

    def _from_html(self, source: dict) -> list[dict]:
        out, seen = [], set()
        for url in source["list_urls"]:
            self._one_html(source, url, out, seen)
        return out

    def _one_html(self, source: dict, list_url: str, out: list, seen: set) -> None:
        raw = self._get(list_url)
        if not raw:
            return
        soup = BeautifulSoup(raw, "html.parser")
        pattern = re.compile(source["link_pattern"])

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not pattern.search(href):
                continue
            title = " ".join(a.get_text(" ", strip=True).split())
            if len(title) < 10:                # 太短的多半是導覽或標籤
                continue
            url = self._normalize(urljoin(source["site_url"], href), source)
            key = urlsplit(url)._replace(query="", fragment="").geturl()                 if source.get("dedupe") == "path" else url
            if key in seen:
                continue
            seen.add(key)
            out.append({"title": title, "url": url, "published": ""})

    @staticmethod
    def _normalize(url: str, source: dict) -> str:
        """把連結導回來源指定的網域（有些站會混用讀不到的子網域）。"""
        host = source.get("host")
        if not host:
            return url
        parts = urlsplit(url)
        if parts.netloc == host:
            return url
        return parts._replace(netloc=host).geturl()

    # ── 內文 ────────────────────────────────────────────────
    def _fetch_article(self, url: str) -> tuple[str, str]:
        """抓文章頁，一併取回內文與發布時間（同一份 HTML，不多跑一趟）。"""
        raw = self._get(url, quiet=True)
        if not raw:
            return "", ""

        soup = BeautifulSoup(raw, "html.parser")
        published = self._find_published(soup, raw)

        # 抽時間要用完整的 HTML，抽內文則要先把版面雜訊拿掉，順序不能顛倒
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form",
                         "figure", "iframe", "noscript"]):
            tag.decompose()

        best = ""
        for selector in BODY_SELECTORS:
            for el in soup.select(selector):
                text = self._paragraphs(el)
                if len(text) > len(best):
                    best = text

        # 後備：有些站（例如 DIGITIMES）的內文段落不在上面那些容器裡，
        # 容器裡反而只有「■ 中文简体版 ■ English」這種導覽字串。
        # 因此不是「抓不到」才後備，而是「抓到的短到不可能是內文」就後備。
        if len(best) < MIN_BODY:
            whole = self._paragraphs(soup)
            if len(whole) > len(best):
                best = whole

        return self._clean_body(best), published

    @staticmethod
    def _paragraphs(scope) -> str:
        """把一個容器裡像內文的段落串起來。

        有些站會把同一段放在版面的兩處（例如摘要區與內文區各一份），
        照抄就會讀到重複的段落，所以同樣的文字只留第一次出現的。
        """
        out, seen = [], set()
        for p in scope.find_all("p"):
            text = " ".join(p.get_text(" ", strip=True).split())
            if len(text) < 15 or text in seen:
                continue
            if len(text) < NOISE_MAX_LEN and NOISE.search(text):
                continue
            seen.add(text)
            out.append(text)
        return "\n".join(out)

    @staticmethod
    def _clean_body(text: str) -> str:
        """截掉導購文字、限制長度。"""
        cut = PAYWALL.search(text)
        if cut:
            text = text[:cut.start()].rstrip(" .·…")
        if len(text) > BODY_LIMIT:
            text = text[:BODY_LIMIT].rstrip() + "…"
        return text

    # ── 小工具 ──────────────────────────────────────────────
    def _get(self, url: str, quiet: bool = False) -> str:
        # 連續抓幾十篇內文時偶爾會被斷線或限流，隔一下再試一次多半就過了。
        for attempt in (1, 2):
            try:
                resp = self.session.get(url, headers=HEADERS, timeout=40)
                resp.raise_for_status()
                return resp.content.decode("utf-8", errors="replace")
            except Exception as e:
                if attempt == 1:
                    time.sleep(1.5)
                    continue
                if not quiet:
                    self.logger.error(f"讀取失敗 {url[:70]}: {e}")
        return ""

    @staticmethod
    def _text(node, name: str) -> str:
        for child in node:
            if child.tag.split("}")[-1] == name and child.text:
                return " ".join(child.text.split())
        return ""

    @staticmethod
    def _iso(value: str) -> str:
        """把各種時間字串轉成 ISO；認不出來就留空。

        沒帶時區的一律當台北時間 —— 這幾個站都是台灣媒體，
        當成 UTC 會讓時間整整早八小時。
        """
        if not value:
            return ""
        value = value.strip().replace("/", "-")
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(value, fmt)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TAIPEI)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return ""

    def _find_published(self, soup, raw: str) -> str:
        """從文章頁找發布時間 —— HTML 來源的清單上沒有時間可用。"""
        for key in ("property", "name", "itemprop"):
            for meta in soup.find_all("meta", attrs={key: True}):
                if not PUB_META.fullmatch(meta.get(key, "").lower()):
                    continue
                stamp = self._iso(meta.get("content", ""))
                if stamp:
                    return stamp

        for hit in re.findall(r'"datePublished"\s*:\s*"([^"]+)"', raw):
            stamp = self._iso(hit)
            if stamp:
                return stamp

        for node in soup.find_all("time"):
            stamp = self._iso(node.get("datetime", "")) or self._iso(
                " ".join(node.get_text(" ", strip=True).split()))
            if stamp:
                return stamp

        # 最後才看內文文字：版面上通常就印著發布時間
        hit = PUB_TEXT.search(soup.get_text(" ", strip=True))
        return self._iso(hit.group(0)) if hit else ""
