"""熱門新聞：來源解析、合併計分、時段判斷、Claude 結果整理、推播不重複。"""
import json
from datetime import datetime
from types import SimpleNamespace

import hot_news as hn

RSS = """<rss><channel>
<item><title>Fed holds rates - Reuters</title><link>https://news.google.com/a</link>
<pubDate>Fri, 02 Oct 2026 13:30:00 GMT</pubDate><source url="x">Reuters</source></item>
<item><title><![CDATA[Stocks rally]]></title><link>https://cnbc.com/b</link><description><![CDATA[<p>Nasdaq record</p>]]></description>
<pubDate>Fri, 02 Oct 2026 20:00:00 GMT</pubDate></item>
</channel></rss>"""

UDN = """<script type="application/ld+json">{"@graph":[{"@type":"ItemList","itemListElement":[
{"@type":"ListItem","position":1,"item":{"headline":"台積電傳合作","url":"https://money.udn.com/1",
"description":"消息人士透露","datePublished":"2026-10-03T16:50:00+08:00"}}]}]}</script>"""


def test_parsers():
    rss = hn.parse_rss(RSS, "Google 新聞", 10)
    assert rss[0]["title"] == "Fed holds rates" and rss[0]["src"] == "Google 新聞／Reuters"
    assert rss[0]["time"] == "2026-10-02 21:30" and rss[0]["summary"] == ""
    assert rss[1]["summary"] == "Nasdaq record" and rss[1]["rank"] == 2
    udn = hn.parse_udn(UDN, "經濟日報排行", 20)
    assert udn == [{"src": "經濟日報排行", "rank": 1, "title": "台積電傳合作", "summary": "消息人士透露",
                    "url": "https://money.udn.com/1", "time": "2026-10-03 16:50"}]
    cy = hn.parse_cnyes({"items": {"tw_stock": [{"newsId": 9, "title": "外資回補", "publishAt": 1790819677}]}},
                        "tw_stock", "鉅亨網台股", 10)
    assert cy[0]["url"].endswith("/9") and cy[0]["rank"] == 1


def test_merge_scores_duplicates_higher():
    a = [{"src": "A", "rank": 1, "title": "台積電 傳合作", "summary": "", "url": "u1", "time": ""},
         {"src": "A", "rank": 2, "title": "其他新聞", "summary": "", "url": "u2", "time": ""}]
    b = [{"src": "B", "rank": 3, "title": "台積電傳合作！", "summary": "摘要", "url": "u3", "time": ""}]
    out = hn.merge([a, b], [2, 4])
    assert out[0]["title"] == "台積電 傳合作" and out[0]["srcs"] == ["A", "B"] and out[0]["summary"] == "摘要"
    assert out[0]["score"] == 1.5 and out[0]["id"] == 1 and out[1]["id"] == 2


def test_due_slot():
    done = {"2026-10-03": ["pre"]}
    assert hn.due_slot(datetime(2026, 10, 3, 9, 0), done) is None            # 盤前做過了
    assert hn.due_slot(datetime(2026, 10, 3, 14, 30), done)[0] == "mid"
    assert hn.due_slot(datetime(2026, 10, 3, 17, 30), done)[0] == "mid"    # 4 小時內都算
    assert hn.due_slot(datetime(2026, 10, 3, 18, 30), done) is None          # 超過 4 小時
    assert hn.due_slot(datetime(2026, 10, 3, 21, 5), {})[0] == "night"
    assert hn.due_slot(datetime(2026, 10, 3, 3, 0), {}) is None


class Fake:
    def __init__(self, payload):
        self.payload = payload
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.kw = kw
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(self.payload))],
                               usage=SimpleNamespace(input_tokens=9000, output_tokens=1500))


def _lists():
    item = lambda i, t: {"id": i, "score": 1.0, "srcs": ["A"], "title": t, "summary": "", "url": "", "time": ""}
    return {"intl": {"items": [item(1, "Fed holds"), item(2, "Oil jumps")], "sources": ["A"]},
            "tw": {"items": [item(1, "台積電")], "sources": ["B"]}}


def test_analyze_cleans_result_and_requests_schema():
    topic = lambda imp, ids: {"title": "t", "summary": "s", "impact": "利多", "why": "w",
                              "sectors": ["半導體", "a", "b", "c"], "stocks": [], "importance": imp, "ids": ids}
    fake = Fake({"headline": "h", "intl": [topic(3, [1, 9]), topic(7, [2])], "tw": [topic(0, [1])],
                 "alerts": [{"key": "非農爆冷", "text": "x"}, {"key": "", "text": "y"}]})
    out = hn.analyze(_lists(), [], "測試", client=fake)
    assert [t["importance"] for t in out["intl"]] == [5, 3]           # 夾在 1～5、依重要性排序
    assert out["intl"][1]["ids"] == [1] and len(out["intl"][0]["sectors"]) == 3
    assert out["tw"][0]["importance"] == 1 and out["alerts"] == [{"key": "非農爆冷", "text": "x"}]
    assert fake.kw["output_config"]["format"]["type"] == "json_schema"
    assert "已推播過的事件：（無）" in fake.kw["messages"][0]["content"]


def test_update_pushes_new_alerts_once(tmp_path, monkeypatch):
    import alerts
    sent = []
    monkeypatch.setenv("BARK_KEY", "test")
    monkeypatch.setattr(alerts, "send", lambda msg, key, server: sent.append(msg["title"]) or True)
    monkeypatch.setattr(hn, "fetch", lambda logger=None: _lists())
    result = {"headline": "h", "intl": [], "tw": [], "alerts": [{"key": "非農爆冷", "text": "x"}]}
    monkeypatch.setattr(hn, "analyze", lambda lists, pushed, label, client=None: dict(result))
    path = tmp_path / "hot.json"
    assert hn.update(now=datetime(2026, 10, 3, 8, 5), path=path) == 1
    assert hn.update(now=datetime(2026, 10, 3, 8, 20), path=path) == 0      # 同一時段不重做
    assert hn.update(now=datetime(2026, 10, 3, 14, 5), path=path) == 1      # 下一個時段，同一件事不再推
    data = json.loads(path.read_text(encoding="utf-8"))
    assert sent == ["財經快訊：非農爆冷"] and data["done"]["2026-10-03"] == ["pre", "mid"]
    assert data["method"] == "claude" and "非農爆冷" in data["pushed"]


def test_when_label_and_alert_time():
    from news_digest import when_label
    assert when_label("2026-10-07T06:31:00Z") == "10/7 14:31"          # RSS 的 UTC → 台北時間
    assert when_label("2026-10-07 09:24") == "10/7 09:24"              # 熱門新聞存的已經是台北時間
    assert when_label("") == "" and when_label("壞掉") == ""
    lists = {"tw": {"items": [{"id": 1, "time": "2026-10-07 09:24"}, {"id": 2, "time": "2026-10-07 13:05"},
                              {"id": 3, "time": ""}]}}
    assert hn.alert_time({"region": "tw", "ids": [1, 2, 3]}, lists) == "10/7 13:05"   # 相關新聞裡最新的
    assert hn.alert_time({"region": "intl", "ids": [1]}, lists) == "" and hn.alert_time({"key": "x"}, None) == ""


def test_push_body_starts_with_news_time(monkeypatch):
    import alerts
    sent = []
    monkeypatch.setenv("BARK_KEY", "test")
    monkeypatch.setattr(alerts, "send", lambda msg, key, server: sent.append(msg["body"]) or True)
    lists = {"tw": {"items": [{"id": 4, "time": "2026-10-07 14:31"}]}}
    hn.push([{"key": "台積電", "text": "內容", "region": "tw", "ids": [4]}], {}, "2026-10-07", lists)
    assert sent == ["10/7 14:31　內容"]

