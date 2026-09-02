"""
新聞來源設定

每個來源一筆，決定清單怎麼抓、連結長什麼樣。抓法分兩種：

    rss   有 RSS feed，直接解析（標題、連結、時間都現成）
    html  沒有 feed，從清單頁挑出符合 link_pattern 的連結
    wp    WordPress REST API，一次就把標題、時間、內文全帶回來

list_urls 可以放多個位址（分頁、不同分類、不同 feed），抓完依序合併去重 ——
單一頁面通常只有 30～40 則，湊不到想要的則數。

html 來源另有兩個選項：host 統一連結網域，dedupe="path" 表示同一路徑
即視為同一則（預設是整條網址相同才算重複）。

內文一律另外抓文章頁，用同一套通用的抽取邏輯（見 news_scraper）。
"""

SOURCES = [
    {
        "id": "ustv",
        "label": "非凡新聞",
        "kind": "html",
        # 清單頁（newslist/*）是 JS 渲染、抓不到內容，也沒有可用的 API，
        # 所以只有首頁這 30 則，是這個來源的上限。
        "list_urls": ["https://news.ustv.com.tw/"],
        "site_url": "https://news.ustv.com.tw/",
        "link_pattern": r"/newsdetail/\d+",
        # 首頁有些連結指向 s.ustv.com.tw，這個網域對外解析不到，
        # 換成 news.ustv.com.tw 的同一條路徑就讀得到。
        "host": "news.ustv.com.tw",
        # 同一則新聞會以 ?newsall=true&type=... 的形式在首頁出現第二次，
        # 用路徑（不含 query）判斷重複。
        "dedupe": "path",
    },
    {
        "id": "yahoo",
        "label": "Yahoo",
        "kind": "rss",
        # 財經 feed 只有 30 則，配上股市 feed 才夠。
        "list_urls": [
            "https://tw.news.yahoo.com/rss/finance",
            "https://tw.stock.yahoo.com/rss?category=news",
        ],
        "site_url": "https://tw.news.yahoo.com/finance/",
        "link_pattern": r"",
    },
    {
        "id": "ltn",
        "label": "自由財經",
        "kind": "html",
        "list_urls": ["https://ec.ltn.com.tw/"],
        "site_url": "https://ec.ltn.com.tw/",
        "link_pattern": r"/article/",
    },
    {
        "id": "digitimes",
        "label": "DIGITIMES",
        "kind": "html",
        # 首頁只有二十幾則，產業總覽頁才有足夠的量。
        "list_urls": [
            "https://www.digitimes.com.tw/tech/",
            "https://www.digitimes.com.tw/",
        ],
        "site_url": "https://www.digitimes.com.tw/",
        "link_pattern": r"shwnws\.asp",
    },
    {
        "id": "technews",
        "label": "TechNews",
        "kind": "wp",
        # RSS 固定只給最新 40 則（?paged=N 被忽略），但 WordPress 的
        # REST API 可以一次要 100 篇，而且內文就在回應裡，不必逐篇再抓。
        "list_urls": ["https://technews.tw/wp-json/wp/v2/posts?per_page=100"],
        "site_url": "https://technews.tw/",
        "link_pattern": r"",
    },
]

SOURCE_BY_ID = {s["id"]: s for s in SOURCES}

# 每個來源抓幾則。抓不滿就有多少列多少（非凡新聞只有首頁的 30 則可抓）。
PER_SOURCE = 60

# 內文最多保留幾個字。夠讀完重點，又不會讓單一來源的 JSON 太肥。
BODY_LIMIT = 1200
