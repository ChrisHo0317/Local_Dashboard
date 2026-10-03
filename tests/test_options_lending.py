"""選擇權籌碼、台指期夜盤、借券賣出與當沖的解析。"""
import market_scraper as ms
import options_data as od


def test_options_parsers():
    pc = od.parse_pc([{"Date": "20261002", "PutCallVolumeRatio%": "89.16", "PutCallOIRatio%": "80.84"}])
    assert pc == {"2026-10-02": {"pc_vol": 89.16, "pc_oi": 80.84}}
    insti = od.parse_insti([
        {"Date": "20261002", "ContractCode": "臺指選擇權", "CallPut": "CALL", "Item": "外資及陸資", "OpenInterest(Net)": "-1,113"},
        {"Date": "20261002", "ContractCode": "臺指選擇權", "CallPut": "PUT", "Item": "投信", "OpenInterest(Net)": "105"},
        {"Date": "20261002", "ContractCode": "電子選擇權", "CallPut": "PUT", "Item": "投信", "OpenInterest(Net)": "9"}])
    assert insti == {"2026-10-02": {"fi_call_oi": -1113.0, "it_put_oi": 105.0}}
    large = od.parse_large([
        {"Date": "20261002", "Contract": "TXO", "CallPut": "買權", "SettlementMonth": "666666", "TypeOfTraders": "0",
         "Top5Buy": "9205", "Top5Sell": "12927", "Top10Buy": "10760", "Top10Sell": "13843"},
        {"Date": "20261002", "Contract": "TXO", "CallPut": "買權", "SettlementMonth": "202610", "TypeOfTraders": "0",
         "Top5Buy": "1", "Top5Sell": "1", "Top10Buy": "1", "Top10Sell": "1"}])
    assert large == {"2026-10-02": {"top5_call": -3722.0, "top10_call": -3083.0}}
    night = od.parse_night([
        {"Date": "20261002", "Contract": "TX", "ContractMonth(Week)": "202611", "TradingSession": "盤後", "Last": "48655"},
        {"Date": "20261002", "Contract": "TX", "ContractMonth(Week)": "202610", "TradingSession": "盤後", "Last": "48475"},
        {"Date": "20261002", "Contract": "TX", "ContractMonth(Week)": "202610", "TradingSession": "一般", "Last": "48671"},
        {"Date": "20261002", "Contract": "TX", "ContractMonth(Week)": "202703", "TradingSession": "盤後", "Last": "-"}])
    assert night == [{"項目": "台指期夜盤", "收盤": 48475.0, "日期": "2026-10-02"}]


def test_lending_and_daytrade_parsers():
    lend = ms.parse_twse_lending({"stat": "OK", "data": [
        ["2330", "台積電", "1", "0", "0", "0", "1", "9", "14,917,000", "120,000", "834,000", "0", "14,203,000", "9", ""]]})
    assert lend.iloc[0]["sbl_bal"] == 14_203_000 and lend.iloc[0]["sbl_sell"] == 120_000
    dt, summ = ms.parse_twse_daytrade({"stat": "OK", "tables": [
        {"fields": ["當日沖銷交易總成交股數", "當日沖銷交易總成交股數占市場比重%"], "data": [["2,219,003,000", "20.14"]]},
        {"fields": ["證券代號", "證券名稱", "暫停現股賣出後現款買進當沖註記", "當日沖銷交易成交股數"],
         "data": [["2330", "台積電", "", "2,500,000"]]}]})
    assert summ == {"twse_daytrade_pct": 20.14} and dt.iloc[0]["dt_vol"] == 2_500_000
    day, tp = ms.parse_tpex_lending([{"Date": "1151002", "SecuritiesCompanyCode": "3624",
                                      "SecuritiesBorrowingBalancePreviousDay": "5", "SecuritiesBorrowingSale": "2",
                                      "SecuritiesBorrowingBalanceOfTheMarketDay": "7"}])
    assert day == "2026-10-02" and tp.iloc[0]["sbl_bal"] == 7 and tp.iloc[0]["sbl_sell"] == 2
    assert ms.parse_tpex_daytrade([{"Date": "1151001", "DayTradingVolumeOfTheMarket": "22.83%"}]) == {"2026-10-01": 22.83}
