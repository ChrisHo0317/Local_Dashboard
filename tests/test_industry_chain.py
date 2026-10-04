"""細產業：解析櫃買中心產業價值鏈頁、名稱整理、補充表、主要細產業、強勢紀錄族群判斷。"""
import numpy as np
import pandas as pd

import industry_chain as ic
import stock_news

PAGE = """
<div class="chain-title-panel">上游</div>
<div id="ic_link_D100" class="company-chain-panel" style="x">IC設計</div>
<div class="chain-title-panel">中游</div>
<div id="ic_link_D300" class="company-chain-panel" style="x">IC/晶圓製造</div>
<div id="ic_link_D400" class="company-chain-panel" style="x">生產製程<br/>及<br/>檢測設備</div>
<div id="companyList_D100" title="IC設計" class="x-hidden"><div id="sc_link_D150" class="subchain"><span>&#9658;</span>&nbsp;記憶體IC&nbsp;(2家)</div>
<table id="sc_company_D150"><tr><td><b>本國上市公司(1家)</b></td></tr><tr><td><a href="company_basic.php?stk_code=2408" class="c" title="南亞科">南亞科</a></td></tr>
<tr><td><b>本國興櫃公司(1家)</b></td></tr><tr><td><a href="company_basic.php?stk_code=9999" class="c" title="興櫃">興櫃</a></td></tr></table></div>
<div id="companyList_D300" title="IC/晶圓製造" class="x-hidden"><div id="sc_link_D310" class="subchain-hover"><span>&#9658;</span>&nbsp;晶圓製造&nbsp;(1家)</div>
<table id="sc_company_D310"><tr><td><b>本國上市公司(1家)</b></td></tr><tr><td><a href="company_basic.php?stk_code=2330" class="c" title="台積電">台積電</a></td></tr></table></div>
<div id="companyList_D400" title="設備" class="x-hidden"><div class="company-list"><table><tr><td><b>本國上櫃公司(1家)</b></td>
<td><a href="company_basic.php?stk_code=3131" class="c" title="弘塑">弘塑</a></td></tr></table></div></div>
"""


def test_parse_and_label():
    rows = ic.parse_chain(PAGE, "半導體")
    assert ("2408", "半導體", "上游", "IC設計", "記憶體IC") in rows
    assert ("2330", "半導體", "中游", "IC/晶圓製造", "晶圓製造") in rows
    assert ("3131", "半導體", "中游", "生產製程及檢測設備", "") in rows
    assert not any(r[0] == "9999" for r in rows)                    # 興櫃不收
    assert ic.label("半導體", "IC/晶圓製造", "晶圓製造") == "晶圓代工"
    assert ic.label("半導體", "生產製程及檢測設備", "") == "半導體設備"
    assert ic.label("通信網路", "其他零組件", "") == "通信網路・其他零組件"
    assert ic.label("電腦及週邊設備", "伺服器", "") == "伺服器"


def test_extra_and_tags(tmp_path, monkeypatch):
    path = tmp_path / "extra.csv"
    path.write_text("# 註解\n細產業,代號,名稱,備註\n光通訊,4979,華星光,\n晶圓代工,2330,台積電,重複\n", encoding="utf-8")
    monkeypatch.setattr(ic, "EXTRA_PATH", path)
    ex = ic.load_extra()
    assert list(ex["tag"]) == ["光通訊", "晶圓代工"]
    chain = pd.DataFrame([("2330", "半導體", "中游", "IC/晶圓製造", "晶圓製造")], columns=ic.COLUMNS)
    tg = ic.tags(chain, ex)
    # 和官方同名的補充合併成一類，官方那筆優先
    assert len(tg[(tg.code == "2330")]) == 1 and tg[tg.code == "2330"]["extra"].iloc[0] == 0
    assert tg[tg.code == "4979"]["extra"].iloc[0] == 1


def test_primary_by_correlation():
    rng = np.random.default_rng(1)
    days = pd.bdate_range("2026-07-01", periods=60)
    mem = rng.normal(0, 0.02, 60)
    fab = rng.normal(0, 0.02, 60)
    R = pd.DataFrame(index=days)
    for c in ["m1", "m2", "m3", "m4"]:
        R[c] = mem + rng.normal(0, 0.003, 60)
    for c in ["f1", "f2", "f3", "f4"]:
        R[c] = fab + rng.normal(0, 0.003, 60)
    R["X"] = mem + rng.normal(0, 0.003, 60)          # 走勢像記憶體
    rows = [(c, "記憶體", "半導體", "", 0) for c in ["m1", "m2", "m3", "m4", "X"]]
    rows += [(c, "晶圓代工", "半導體", "", 0) for c in ["f1", "f2", "f3", "f4", "X"]]
    tg = pd.DataFrame(rows, columns=["code", "tag", "chain", "stage", "extra"])
    p = ic.primary(tg, R)
    assert p["X"] == "記憶體" and p["f1"] == "晶圓代工"
    # 沒有報酬資料：取最小的類別
    p2 = ic.primary(tg, None)
    assert p2["X"] in ("記憶體", "晶圓代工")
    js = ic.site_json(tg, p)
    names = [t[0] for t in js["tags"]]
    assert js["tags"][js["codes"]["X"][0]][0] == "記憶體" and set(names) == {"記憶體", "晶圓代工"}


class FakeMkt:
    ok = True

    def __init__(self):
        self.liquid = pd.DataFrame({"industry": ["半導體業"] * 5, "r5": [5, 4, 3, 2, -1]},
                                   index=["A", "B", "C", "D", "E"])

    def r5(self, c):
        return float(self.liquid["r5"].get(c, 0))

    def corr(self, a, b):
        return 0.8

    def name(self, c):
        return c


def test_groups_use_fine_tags(monkeypatch):
    tag_of = {"A": ["記憶體", "晶圓代工"], "B": ["記憶體"], "C": ["晶圓代工"], "D": ["記憶體"]}
    members = {"記憶體": {"A", "B", "D"}, "晶圓代工": {"A", "C"}}
    monkeypatch.setattr(stock_news, "_chain_maps",
                        lambda: (tag_of, {k: len(v) for k, v in members.items()}, members))
    stocks = {c: {"method": "rules", "industry": "半導體業"} for c in ["A", "B", "C"]}
    stock_news.attach_groups(stocks, FakeMkt())
    # A 同時是記憶體與晶圓代工：記憶體當天有 A、B 兩檔強勢股，晶圓代工有 A、C 兩檔 → 一樣多取比較小的類別
    assert stocks["A"]["group"] == "晶圓代工"
    assert stocks["B"]["group"] == "記憶體"
    assert {m[0] for m in stocks["B"]["members"]} == {"A", "D"} and stocks["B"]["linked"]
