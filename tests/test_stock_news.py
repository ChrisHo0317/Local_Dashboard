"""強勢股新聞：挑股票、解析來源、合併、規則與 Claude 結果、快取沿用。"""
import json
from datetime import datetime
from types import SimpleNamespace

import pandas as pd

import stock_news as sn

TPE = sn.TAIPEI


def _panel():
    days = pd.bdate_range("2026-09-01", periods=25)
    rows = []
    for i, d in enumerate(days):
        # 甲：一路漲而且最近 5 天漲更快、成交大
        rows.append({"date": d, "code": "1111", "market": "twse",
                     "close": 100 + i + (3 * (i - 19) if i > 19 else 0), "turnover": 5e8,
                     "foreign": 10000.0, "trust": -2000.0})
        # 乙：有漲但最近變慢
        rows.append({"date": d, "code": "2222", "market": "twse",
                     "close": 100 + (2 * i if i <= 19 else 38 + 0.1 * (i - 19)), "turnover": 5e8,
                     "foreign": 0.0, "trust": 0.0})
        # 丙：越來越強但成交太少，是自選股
        rows.append({"date": d, "code": "3333", "market": "tpex",
                     "close": 50 + 0.2 * i + (2 * (i - 19) if i > 19 else 0), "turnover": 1e6,
                     "foreign": 0.0, "trust": 0.0})
        # ETF 不列入
        rows.append({"date": d, "code": "0050", "market": "twse",
                     "close": 100 + i + (5 * (i - 19) if i > 19 else 0), "turnover": 9e9,
                     "foreign": 0.0, "trust": 0.0})
    panel = pd.DataFrame(rows)
    master = pd.DataFrame({"code": ["1111", "2222", "3333"], "name": ["甲", "乙", "丙"],
                           "market": ["twse", "twse", "tpex"],
                           "industry": ["半導體業", "半導體業", "光電業"]})
    return panel, master


def test_pick_targets_strong_liquid_then_watch():
    panel, master = _panel()
    out = sn.pick_targets(panel, master, watch_codes={"3333"})
    assert [t["code"] for t in out] == ["1111", "3333"]
    a, c = out
    assert a["rank"] == 1 and c["rank"] is None and c["watch"]
    assert a["a"] > 0 and a["s"] > 0 and len(a["daily"]) == 5
    assert a["foreign"] == 50 and a["trust"] == -10          # 5 天 × 1 萬股 → 50 張
    assert a["market"] == "上市" and c["market"] == "上櫃"
    assert sn.pick_targets(panel, master, watch_codes=set())[-1]["code"] == "1111"


GOOGLE = """<?xml version="1.0"?><rss><channel>
<item><title>光頡領軍被動元件漲停 - 工商時報</title><link>https://news.google.com/a</link>
<pubDate>Thu, 01 Oct 2026 07:00:00 GMT</pubDate><source url="x">工商時報</source></item>
<item><title>壞日期</title><link>x</link><pubDate>???</pubDate></item>
</channel></rss>"""


def test_parse_google_strips_source_and_converts_time():
    items = sn.parse_google(GOOGLE)
    assert len(items) == 1
    it = items[0]
    assert it["title"] == "光頡領軍被動元件漲停" and it["source"] == "工商時報"
    assert it["time"] == datetime(2026, 10, 1, 15, 0, tzinfo=TPE)
    assert sn.parse_google("not xml") == []


def test_parse_cnyes_and_announcements():
    payload = {"data": {"items": [
        {"newsId": 1, "title": "光頡(<mark>3624</mark>)漲停", "summary": "摘要", "publishAt": 1790819677},
        {"newsId": 2, "title": "沒有時間"}]}}
    items = sn.parse_cnyes(payload)
    assert len(items) == 1 and items[0]["title"] == "光頡(3624)漲停"
    assert items[0]["url"].endswith("/news/id/1") and items[0]["source"] == "鉅亨網"

    ann = pd.DataFrame({"code": ["3624", "3624", "9999"], "date": ["1151001", "1150901", "1151001"],
                        "time": ["153000", "90000", "100000"],
                        "subject": ["公告漲價", "太舊", "別檔"], "body": ["內容", "", ""]})
    got = sn.announcements(ann, "3624", datetime(2026, 9, 25, tzinfo=TPE))
    assert [g["title"] for g in got] == ["公告漲價"]
    assert got[0]["time"] == datetime(2026, 10, 1, 15, 30, tzinfo=TPE) and got[0]["kind"] == "a"


def _item(title, day, source="工商時報", kind="n", summary=""):
    return {"kind": kind, "title": title, "url": "", "source": source,
            "time": datetime(2026, 10, day, 9, 0, tzinfo=TPE), "summary": summary}


def test_merge_items_dedupes_filters_and_orders():
    since = datetime(2026, 9, 28, tzinfo=TPE)
    a = [_item("光頡 漲停！", 1, "鉅亨網")]
    b = [_item("光頡漲停", 2), _item("太舊的新聞", 1).copy() | {"time": datetime(2026, 9, 1, tzinfo=TPE)},
         _item("光頡接單", 2)]
    out = sn.merge_items(a, b, since=since)
    assert [it["title"] for it in out] == ["光頡接單", "光頡 漲停！"]   # 重複的留先出現的、新到舊
    assert len(sn.merge_items(a, b, since=since, limit=1)) == 1


def test_rules_prefers_keyword_news_about_the_company():
    items = [_item("盤中速報 - 光頡(3624)股價拉至漲停", 2, "鉅亨網"),
             _item("聯亞攻上漲停，光通訊題材再被點火", 2),          # 標題沒提到這檔
             _item("光頡電阻報價調漲 訂單滿到年底", 1)]
    r = sn.analyze_rules(items, "光頡")
    assert r["key"] == [2] and r["category"] in ("接單／新產品", "產品漲價")
    assert r["confidence"] == "低"
    none = sn.analyze_rules([_item("盤中速報 - 光頡漲停", 1, "鉅亨網")], "光頡")
    assert none["key"] == [] and none["category"] == "原因不明"


class FakeClient:
    def __init__(self, payload, stop="end_turn"):
        self.calls = 0
        self.payload, self.stop = payload, stop
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls += 1
        self.kw = kw
        return SimpleNamespace(stop_reason=self.stop,
                               content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=200))


RESULT = {"relevant": [1, 3, 9], "reason": "電阻報價調漲", "category": "產品漲價",
          "confidence": "中", "key": [3, 2], "points": ["報價調漲"]}


def test_claude_result_maps_ids_and_requests_schema():
    client = FakeClient(RESULT)
    an = sn.ClaudeAnalyzer(client=client)
    r = an("prompt", 3)
    assert r["relevant"] == [0, 2]                      # 9 超出範圍丟掉
    assert r["key"] == [2]                              # 2 不在 relevant 裡
    kw = client.kw
    assert kw["model"] == sn.MODEL and kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["extra_body"] == {"fallbacks": "default"}
    assert an.tokens_in == 1000 and an.cost() > 0
    assert sn.ClaudeAnalyzer(client=FakeClient(RESULT, stop="refusal"))("p", 3) is None


def _job(code="3624"):
    t = {"code": code, "name": "光頡", "market": "上櫃", "industry": "電子零組件業", "rank": 1,
         "watch": False, "s": 25.0, "r5": 12.0, "p5": 2.0, "a": 10.0, "tv": 3.2,
         "daily": [("09/28", 1.0)] * 5, "foreign": 100, "trust": None, "ind_r5": 3.0, "ind_n": 20}
    items = [_item("光頡漲停", 2), _item("無關", 2), _item("光頡電阻報價調漲", 1)]
    return {"target": t, "items": items, "revenue": "2026 年 8 月營收、年增 +10.0%"}


def test_analyze_all_uses_claude_then_reuses_cache():
    client = FakeClient(RESULT)
    out = sn.analyze_all([_job()], {}, sn.ClaudeAnalyzer(client=client))
    s = out["3624"]
    assert s["method"] == "claude" and s["why"] == "電阻報價調漲" and client.calls == 1
    assert [it["t"] for it in s["items"]] == ["光頡電阻報價調漲", "光頡漲停"]   # 關鍵的排前面、無關的不存
    assert s["items"][0]["key"] and not s["items"][1]["key"] and s["total"] == 3

    again = sn.analyze_all([_job()], out, sn.ClaudeAnalyzer(client=client))
    assert client.calls == 1 and again["3624"]["why"] == "電阻報價調漲"   # 資料沒變不再呼叫

    # 上次是規則、這次有 Claude 可用 → 重新分析
    rules = sn.analyze_all([_job()], {}, sn.ClaudeAnalyzer(client=None))
    assert rules["3624"]["method"] == "rules"
    redo = sn.analyze_all([_job()], rules, sn.ClaudeAnalyzer(client=client))
    assert redo["3624"]["method"] == "claude" and client.calls == 2


def test_prompt_lists_numbered_items_and_context():
    job = _job()
    text = sn.build_prompt(job["target"], job["items"], job["revenue"])
    assert "[1]" in text and "[3]" in text and "外資 +100 張" in text
    assert "最新月營收" in text and "3624 光頡" in text


# ── 族群與歷史 ──────────────────────────────────────────────
def _group_market():
    days = pd.bdate_range("2026-09-01", periods=25)
    rows = []
    for i, d in enumerate(days):
        wave = [0, 2, -1, 3, 1][i % 5]
        # 甲、乙、丙同步漲（同一個節奏），丁走自己的路
        for code, base, k in (("1111", 100, 1.0), ("2222", 50, 1.1), ("3333", 80, 0.9)):
            rows.append({"date": d, "code": code, "market": "twse",
                         "close": base + i * k + wave * k, "turnover": 5e8,
                         "foreign": 0.0, "trust": 0.0})
        rows.append({"date": d, "code": "4444", "market": "twse",
                     "close": 60 + (i % 3) - 0.5 * i, "turnover": 5e8, "foreign": 0.0, "trust": 0.0})
    panel = pd.DataFrame(rows)
    master = pd.DataFrame({"code": ["1111", "2222", "3333", "4444"],
                           "name": ["光頡", "國巨", "華新科", "大立光"],
                           "market": ["twse"] * 4, "industry": ["電子零組件業"] * 4})
    return sn.Market(panel, master)


def test_norm_theme_and_code_lookup():
    assert sn.norm_theme(" 被動元件族群 ") == "被動元件"
    assert sn.norm_theme("AI概念股") == "AI"
    mkt = _group_market()
    assert mkt.code_of("國巨") == "2222" and mkt.code_of("國巨(2222)") == "2222"
    assert mkt.code_of("華新") == "3333"                     # 唯一的開頭相符
    assert mkt.code_of("國巨2222") == "2222"                 # 中文緊接代號
    assert mkt.code_of("台積電") is None
    assert mkt.corr("1111", "2222") > 0.9 and mkt.corr("1111", "4444") < 0.6


def _entry(method, theme="", news_linked=False, named=(), industry="電子零組件業"):
    return {"name": "", "method": method, "theme": theme, "news_linked": news_linked,
            "named": list(named), "industry": industry, "items": []}


def test_attach_groups_with_claude_verifies_by_price():
    mkt = _group_market()
    stocks = {"1111": _entry("claude", "被動元件", True, ["國巨", "大立光"])}
    sn.attach_groups(stocks, mkt)
    s = stocks["1111"]
    assert s["group"] == "被動元件" and s["linked"]
    codes = [m[0] for m in s["members"]]
    assert codes == ["2222"]                     # 大立光走勢不同步，不列入
    assert s["members"][0][5] and not s["members"][0][4]   # 新聞有提到、不在強勢股名單

    # 新聞沒說族群、只有兩檔強勢股同族群 → 不算連動；三檔以上才算
    two = {"1111": _entry("claude", "被動元件"), "2222": _entry("claude", "被動元件")}
    sn.attach_groups(two, mkt)
    assert not two["1111"]["linked"] and two["1111"]["members"][0][0] == "2222"
    three = {c: _entry("claude", "被動元件") for c in ("1111", "2222", "3333")}
    sn.attach_groups(three, mkt)
    assert all(s["linked"] for s in three.values())

    solo = {"4444": _entry("claude", "", False)}
    sn.attach_groups(solo, mkt)
    assert solo["4444"]["group"] == "" and not solo["4444"]["linked"]


def test_attach_groups_without_claude_uses_industry_and_correlation():
    mkt = _group_market()
    stocks = {"1111": _entry("rules")}
    sn.attach_groups(stocks, mkt)
    s = stocks["1111"]
    assert s["group"] == "電子零組件業" and s["linked"]
    assert sorted(m[0] for m in s["members"]) == ["2222", "3333"]


def test_history_replaces_same_day(tmp_path):
    path = tmp_path / "h.parquet"
    day = {"1111": {"name": "光頡", "rank": 1, "watch": False, "s": 20.0, "r5": 10.0, "a": 5.0,
                    "tag": "產品漲價", "why": "報價調漲", "conf": "中", "method": "claude",
                    "group": "被動元件", "linked": True, "members": [["2222", "國巨", 8.0, 0.8, False, True]],
                    "items": [{"t": "光頡漲價", "u": "https://x", "src": "鉅亨網", "key": True}]}}
    sn.save_history(day, "2026-10-01", path)
    sn.save_history({**day, "3333": {**day["1111"], "name": "華新科", "rank": 2}}, "2026-10-02", path)
    sn.save_history(day, "2026-10-02", path)                 # 開盤前重跑同一天：整批取代
    h = sn.load_history(path)
    assert sorted(h["date"]) == ["2026-10-01", "2026-10-02"]
    row = h.iloc[0]
    assert row["key_t"] == "光頡漲價" and bool(row["linked"])
    assert json.loads(row["members"])[0][0] == "2222"


def test_record_pages(tmp_path, monkeypatch):
    import intel_build as ib
    path = tmp_path / "h.parquet"
    base = {"name": "光頡", "rank": 1, "watch": False, "s": 20.0, "r5": 10.0, "a": 5.0,
            "tag": "產品漲價", "why": "報價調漲", "conf": "中", "method": "claude",
            "group": "被動元件", "linked": True, "members": [], "items": []}
    sn.save_history({"1111": base, "4444": {**base, "name": "大立光", "rank": None,
                                            "linked": False, "group": ""}}, "2026-10-01", path)
    sn.save_history({"1111": base}, "2026-10-02", path)
    monkeypatch.setattr(ib, "load_strong_history", lambda: sn.load_history(path))
    ib._strong_record(tmp_path)
    ix = json.loads((tmp_path / "record" / "index.json").read_text(encoding="utf-8"))
    assert ix["dates"] == ["2026-10-01", "2026-10-02"]
    assert ix["themes"] == [["被動元件", [1, 1]]]
    assert ix["stocks"]["1111"] == ["光頡", [0, 1]] and ix["summary"][0] == [2, 1, 1]
    day = json.loads((tmp_path / "record" / "2026-10-01.json").read_text(encoding="utf-8"))
    by = {r[0]: r for r in day["rows"]}
    assert by["4444"][2] is None and by["1111"][11] == "被動元件" and by["1111"][12] is True
