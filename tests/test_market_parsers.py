"""證交所、櫃買中心回應的解析（樣本格式取自 2026-09-24 的實際回應）。"""
from datetime import date

import pandas as pd

import market_scraper as ms

TWSE_MI_INDEX = {
    "stat": "OK",
    "tables": [
        {"title": "價格指數", "fields": ["指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"],
         "data": [["發行量加權股價指數", "48,024.60", "<p style ='color:green'>-</p>", "132.69", "-0.28", ""]]},
        {"title": "大盤統計資訊", "fields": ["成交統計", "成交金額(元)", "成交股數(股)", "成交筆數"],
         "data": [["1.一般股票", "718,880,491,672", "3,609,044,470", "3,037,959"],
                  ["總計(1~15)", "775,591,428,171", "8,626,109,510", "3,880,761"]]},
        {"title": "每日收盤行情", "fields": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價",
                                        "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差"],
         "data": [["2330", "台積電", "14,557,662", "75,382", "36,107,476,243", "2,480.00", "2,490.00",
                   "2,470.00", "2,475.00", "<p style= color:green>-</p>", "25.00"],
                  ["9999", "停牌", "0", "0", "0", "--", "--", "--", "--", " ", "0.00"]]},
    ],
}


def test_twse_quotes_and_summary():
    df, summary = ms.parse_twse_quotes(TWSE_MI_INDEX)
    row = df.set_index("code").loc["2330"]
    assert row["close"] == 2475.0 and row["open"] == 2480.0
    assert row["volume"] == 14557662 and row["market"] == "twse"
    assert pd.isna(df.set_index("code").loc["9999"]["close"])          # 停牌沒有價格
    assert summary["twse_index"] == 48024.60
    assert summary["twse_index_chg"] == -132.69          # 綠色的減號是負的
    assert summary["twse_turnover"] == 775591428171


def test_twse_closed_day():
    df, summary = ms.parse_twse_quotes({"stat": "很抱歉，沒有符合條件的資料!"})
    assert df is None and summary == {}


def test_twse_insti_uses_foreign_excluding_dealers():
    fields = ["證券代號", "證券名稱", "外陸資買進股數(不含外資自營商)", "外陸資賣出股數(不含外資自營商)",
              "外陸資買賣超股數(不含外資自營商)", "外資自營商買進股數", "外資自營商賣出股數",
              "外資自營商買賣超股數", "投信買進股數", "投信賣出股數", "投信買賣超股數", "自營商買賣超股數"]
    payload = {"stat": "OK", "fields": fields,
               "data": [["2330", "台積電", "1", "2", "-4,667,832", "0", "0", "0", "3", "4",
                         "-1,287,718", "242,701"]]}
    row = ms.parse_twse_insti(payload).iloc[0]
    assert (row["foreign"], row["trust"], row["dealer"]) == (-4667832, -1287718, 242701)


def test_twse_insti_value():
    payload = {"stat": "OK", "data": [
        ["自營商(自行買賣)", "0", "0", "4,235,536,088"], ["自營商(避險)", "0", "0", "-2,897,105,667"],
        ["投信", "0", "0", "-12,823,263,300"], ["外資及陸資(不含外資自營商)", "0", "0", "-32,964,613,655"],
        ["外資自營商", "0", "0", "0"], ["合計", "0", "0", "-44,449,446,534"]]}
    v = ms.parse_twse_insti_value(payload)
    assert v["foreign_value"] == -32964613655
    assert v["trust_value"] == -12823263300
    assert v["dealer_value"] == 4235536088 - 2897105667


def test_twse_margin_positions():
    payload = {"stat": "OK", "tables": [
        {"fields": ["項目", "買進", "賣出", "現金(券)償還", "前日餘額", "今日餘額"],
         "data": [["融資金額(仟元)", "30,073,340", "20,479,799", "857,972", "606,367,833", "615,103,402"]]},
        {"fields": ["代號", "名稱", "買進", "賣出", "現金償還", "前日餘額", "今日餘額", "次一營業日限額",
                    "買進", "賣出", "現券償還", "前日餘額", "今日餘額"],
         "data": [["2330", "台積電", "1", "2", "0", "29,700", "29,707", "0", "0", "0", "0", "15", "16"]]}]}
    df, summary = ms.parse_twse_margin(payload)
    row = df.iloc[0]
    assert (row["margin_bal"], row["short_bal"]) == (29707, 16)
    assert summary == {"margin_amount_prev": 606367833, "margin_amount": 615103402}


def test_twse_valuation_loss_makes_blank_pe():
    payload = {"stat": "OK", "fields": ["證券代號", "證券名稱", "收盤價", "殖利率(%)", "股利年度",
                                        "本益比", "股價淨值比", "財報年/季"],
               "data": [["1101", "台泥", "25.25", "3.17", 114, "-", "0.82", "115/2"]]}
    row = ms.parse_twse_valuation(payload).iloc[0]
    assert row["per"] is None and row["yield_pct"] == 3.17 and row["pbr"] == 0.82


def test_tpex_tables():
    quotes = {"stat": "ok", "tables": [{"data": [
        ["6488", "環球晶", "948.00", "-2.00", "944.00", "960.00", "930.00", "9,201,000",
         "8,666,445,000", "7,985"]]}]}
    df, summary = ms.parse_tpex_quotes(quotes)
    assert df.iloc[0]["close"] == 948.0 and df.iloc[0]["market"] == "tpex"
    assert summary["tpex_turnover"] == 8666445000

    insti = {"stat": "ok", "tables": [{"data": [[
        "6488", "環球晶", "2,365,104", "4,727,374", "-2,362,270", "0", "0", "0", "2,365,104",
        "4,727,374", "-2,362,270", "0", "11,000", "-11,000", "9,800", "131,796", "-121,996",
        "324,162", "440,170", "-116,008", "333,962", "571,966", "-238,004", "-2,611,274"]]}]}
    row = ms.parse_tpex_insti(insti).iloc[0]
    assert (row["foreign"], row["trust"], row["dealer"]) == (-2362270, -11000, -238004)

    margin = {"stat": "ok", "tables": [{"data": [[
        "6488", "環球晶", "15,551", "671", "325", "4", "15,893", "233", "13.29", "119,528", "387",
        "154", "19", "0", "522", "0", "0.43", "119,528", "8", ""]],
        "summary": [["", "融資金(仟元)", "210,851,410", "1", "2", "3", "211,727,513"]]}]}
    df, summary = ms.parse_tpex_margin(margin)
    assert (df.iloc[0]["margin_bal"], df.iloc[0]["short_bal"]) == (15893, 522)
    assert summary == {"margin_amount_prev": 210851410, "margin_amount": 211727513}

    pe = {"stat": "ok", "tables": [{"data": [["6488", "環球晶", "46.02", "7.7", 114, "0.81", "4.69", "115Q2"]]}]}
    row = ms.parse_tpex_valuation(pe).iloc[0]
    assert (row["per"], row["yield_pct"], row["pbr"]) == (46.02, 0.81, 4.69)


def test_tpex_holiday_and_index():
    assert ms.parse_tpex_quotes({"stat": "ok", "tables": [{"data": []}]}) == (None, {})
    idx = [{"Date": "20260924", "Close": "412.99", "Change": "-0.77"}]
    assert ms.parse_tpex_index(idx, date(2026, 9, 24)) == {"tpex_index": 412.99, "tpex_index_chg": -0.77}
    assert ms.parse_tpex_index(idx, date(2026, 9, 25)) == {}
