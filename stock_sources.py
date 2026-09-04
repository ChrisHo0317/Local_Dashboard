"""
個股資料來源設定

公開資訊觀測站（MOPS）自己的 API 沒有 CORS 標頭，瀏覽器不能直接呼叫，
所以「排程抓、存成 JSON、前端讀」的那幾類走證交所的開放資料：

    https://openapi.twse.com.tw/v1/opendata/...

真正即時的個股查詢走另一組端點（www.twse.com.tw/rwd/...），那組有
Access-Control-Allow-Origin: *，頁面上的 JS 可以當場呼叫，不必經過排程。
端點寫在頁面的 JS 裡（見 build_static 的個股查詢），不在這裡。

欄位只留下頁面上會用到的：原始資料一份 1.4 MB，全塞進去手機會等很久。
"""

# (資料集 id, 開放資料 id, 說明)
DATASETS = [
    ("revenue", "t187ap05_L", "上市公司每月營業收入"),
    ("announce", "t187ap04_L", "上市公司重大訊息"),
    ("income", "t187ap06_L_ci", "上市公司綜合損益表（單季）"),
]

BASE_URL = "https://openapi.twse.com.tw/v1/opendata/"

# 來源欄位 → 我們的欄位。順序就是 CSV 的欄位順序。
FIELDS = {
    "revenue": [
        ("公司代號", "code"),
        ("公司名稱", "name"),
        ("產業別", "industry"),
        ("資料年月", "month"),
        ("營業收入-當月營收", "revenue"),
        ("營業收入-上月營收", "prev_month"),
        ("營業收入-去年當月營收", "prev_year"),
        ("營業收入-上月比較增減(%)", "mom"),
        ("營業收入-去年同月增減(%)", "yoy"),
        ("累計營業收入-當月累計營收", "cum"),
        ("累計營業收入-前期比較增減(%)", "cum_yoy"),
    ],
    "announce": [
        ("公司代號", "code"),
        ("公司名稱", "name"),
        ("發言日期", "date"),
        ("發言時間", "time"),
        ("主旨 ", "subject"),
        ("符合條款", "clause"),
        ("事實發生日", "happened"),
        ("說明", "body"),
    ],
    "income": [
        ("公司代號", "code"),
        ("公司名稱", "name"),
        ("年度", "year"),
        ("季別", "quarter"),
        ("營業收入", "revenue"),
        ("營業毛利（毛損）淨額", "gross"),
        ("營業利益（損失）", "operating"),
        ("稅前淨利（淨損）", "pretax"),
        ("淨利（淨損）歸屬於母公司業主", "net"),
        ("基本每股盈餘（元）", "eps"),
    ],
}

# 重大訊息的說明全文很長，截到這個長度就好（點「看原文」可以到 MOPS 看）
BODY_LIMIT = 1500
