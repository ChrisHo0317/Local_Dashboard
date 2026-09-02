"""
新聞來源設定

每個來源一筆，決定清單怎麼抓、連結長什麼樣。抓法分兩種：

    rss   有 RSS feed，直接解析（標題、連結、時間都現成）
    html  沒有 feed，從首頁挑出符合 link_pattern 的連結

內文一律另外抓文章頁，用同一套通用的抽取邏輯（見 news_scraper）。
"""

SOURCES = [
    {
        "id": "ustv",
        "label": "非凡新聞",
        "kind": "html",
        "list_url": "https://news.ustv.com.tw/",
        "site_url": "https://news.ustv.com.tw/",
        "link_pattern": r"/newsdetail/\d+",
    },
    {
        "id": "yahoo",
        "label": "Yahoo",
        "kind": "rss",
        "list_url": "https://tw.news.yahoo.com/rss/finance",
        "site_url": "https://tw.news.yahoo.com/finance/",
        "link_pattern": r"",
    },
    {
        "id": "ltn",
        "label": "自由財經",
        "kind": "html",
        "list_url": "https://ec.ltn.com.tw/",
        "site_url": "https://ec.ltn.com.tw/",
        "link_pattern": r"/article/",
    },
    {
        "id": "digitimes",
        "label": "DIGITIMES",
        "kind": "html",
        "list_url": "https://www.digitimes.com.tw/",
        "site_url": "https://www.digitimes.com.tw/",
        "link_pattern": r"shwnws\.asp",
    },
    {
        "id": "technews",
        "label": "TechNews",
        "kind": "rss",
        "list_url": "https://technews.tw/feed/",
        "site_url": "https://technews.tw/",
        "link_pattern": r"",
    },
]

SOURCE_BY_ID = {s["id"]: s for s in SOURCES}

# 每個來源抓幾則。抓太多的話每日更新會很久，頁面也會變肥。
PER_SOURCE = 12

# 內文最多保留幾個字。夠讀完重點，又不會讓頁面爆掉。
BODY_LIMIT = 1200
