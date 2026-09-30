"""
個股資料來源設定（上市＋上櫃）

排程抓、存成 JSON、前端讀的那幾類，走兩個交易所的開放資料：

    上市   https://openapi.twse.com.tw/v1/opendata/...
    上櫃   https://www.tpex.org.tw/openapi/v1/...

同一類資料兩邊的欄位名稱不一樣（上櫃的代號叫 SecuritiesCompanyCode），
財報還依產業分成六種格式（一般業、銀行、證券、金控、保險、異業），
所以每個目標欄位列出「可能的來源欄位」，依序取第一個有值的。

注意：綜合損益表是「年初至今累計」，不是單季。單季數字由 fundamentals.py
用前幾季的累計相減算出來。

欄位只留下頁面上會用到的：原始資料一份 1.4 MB，全塞進去手機會等很久。
"""

TWSE_OPEN = "https://openapi.twse.com.tw/v1/"
TPEX_OPEN = "https://www.tpex.org.tw/openapi/v1/"

INCOME_KINDS = ["ci", "basi", "bd", "fh", "ins", "mim"]

# (資料集 id, 市場, 網址, 說明)
DATASETS = (
    [("revenue", "twse", TWSE_OPEN + "opendata/t187ap05_L", "上市公司每月營業收入"),
     ("revenue", "tpex", TPEX_OPEN + "mopsfin_t187ap05_O", "上櫃公司每月營業收入"),
     ("announce", "twse", TWSE_OPEN + "opendata/t187ap04_L", "上市公司重大訊息"),
     ("announce", "tpex", TPEX_OPEN + "mopsfin_t187ap04_O", "上櫃公司重大訊息")]
    + [("income", "twse", TWSE_OPEN + f"opendata/t187ap06_L_{k}", f"上市公司綜合損益表（{k}）")
       for k in INCOME_KINDS]
    + [("income", "tpex", TPEX_OPEN + f"mopsfin_t187ap06_O_{k}", f"上櫃公司綜合損益表（{k}）")
       for k in INCOME_KINDS]
    + [("exdiv", "twse", TWSE_OPEN + "exchangeReport/TWT48U_ALL", "上市除權除息預告"),
       ("exdiv", "tpex", TPEX_OPEN + "tpex_exright_prepost", "上櫃除權除息預告")]
)

CODE = ["公司代號", "SecuritiesCompanyCode", "Code"]
NAME = ["公司名稱", "CompanyName", "Name"]

# 目標欄位 → 依序嘗試的來源欄位。順序就是 CSV 的欄位順序（最後會再加 market）。
FIELDS = {
    "revenue": [
        ("code", CODE),
        ("name", NAME),
        ("industry", ["產業別"]),
        ("month", ["資料年月"]),
        ("revenue", ["營業收入-當月營收"]),
        ("prev_month", ["營業收入-上月營收"]),
        ("prev_year", ["營業收入-去年當月營收"]),
        ("mom", ["營業收入-上月比較增減(%)"]),
        ("yoy", ["營業收入-去年同月增減(%)"]),
        ("cum", ["累計營業收入-當月累計營收"]),
        ("cum_yoy", ["累計營業收入-前期比較增減(%)"]),
    ],
    "announce": [
        ("code", CODE),
        ("name", NAME),
        ("date", ["發言日期"]),
        ("time", ["發言時間"]),
        ("subject", ["主旨 ", "主旨"]),
        ("clause", ["符合條款"]),
        ("happened", ["事實發生日"]),
        ("body", ["說明"]),
    ],
    "income": [
        ("code", CODE),
        ("name", NAME),
        ("year", ["年度", "Year"]),
        ("quarter", ["季別", "Season"]),
        ("revenue", ["營業收入", "淨收益", "收益", "收入", "利息淨收益"]),
        ("gross", ["營業毛利（毛損）淨額", "營業毛利（毛損）"]),
        ("operating", ["營業利益（損失）", "營業利益"]),
        ("pretax", ["稅前淨利（淨損）", "繼續營業單位稅前淨利（淨損）",
                    "繼續營業單位稅前損益", "繼續營業單位稅前純益（純損）"]),
        ("net", ["淨利（淨損）歸屬於母公司業主", "淨利（損）歸屬於母公司業主"]),
        ("eps", ["基本每股盈餘（元）"]),
    ],
    "exdiv": [
        ("code", CODE + ["SecuritiesCompanyCode"]),
        ("name", NAME),
        ("date", ["Date", "ExRrightsExDividendDate"]),
        ("kind", ["Exdividend", "ExRrightsExDividend"]),
        ("cash", ["CashDividend"]),
        ("stock_ratio", ["StockDividendRatio"]),
    ],
}

COLUMNS = {key: [dst for dst, _ in cols] + ["market"] for key, cols in FIELDS.items()}

# 重大訊息的說明全文很長，截到這個長度就好（點「看原文」可以到 MOPS 看）
BODY_LIMIT = 1500
