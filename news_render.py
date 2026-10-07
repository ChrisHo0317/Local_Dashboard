"""
把新聞轉成靜態 HTML

每個來源一個子分頁，內容是條列式清單；點任一則會切到內文檢視，
左上角有返回鍵回到清單。

清單（標題、時間、連結）寫在頁面裡，內文另外存成 site/news/{來源}.json，
點開某一則時才抓，同一個來源只抓一次。內文佔了新聞資料的九成以上，
每個來源 60 則全部內嵌會讓首頁大到不合理。

時間換算成台北時間（UTC+8，固定位移，不依賴系統的 tz 資料庫）。
"""
from datetime import datetime, timedelta, timezone
from html import escape

import pandas as pd

from news_digest import build as build_digest, when_label
from news_sources import SOURCES

TAIPEI = timezone(timedelta(hours=8))

META = "資料來源：各新聞網站　·　點標題可看內文"
DIGEST_META = "五個來源合併去重、依重要性排序　·　點標題可看內文"


def stats(data: dict) -> dict:
    """設定分頁用的摘要。"""
    df = data.get("news", pd.DataFrame())
    if df.empty:
        return {"rows": 0, "range": "無資料", "shown": 0, "latest": "無資料", "sources": 0}
    stamps = pd.to_datetime(df["published"], errors="coerce", utc=True).dropna()
    if stamps.empty:
        span = latest = "無時間資訊"
    else:
        lo = stamps.min().tz_convert(TAIPEI).strftime("%Y-%m-%d")
        hi = stamps.max().tz_convert(TAIPEI).strftime("%Y-%m-%d")
        span, latest = f"{lo} ～ {hi}", hi
    return {
        "rows": len(df),
        "sources": df["source"].nunique(),
        "range": span,
        "shown": len(df),
        "latest": latest,
    }


HOT_META = "國際與台灣熱門財經新聞，每天 08:00、14:00、21:00 整理"


def _subtabs_html() -> str:
    btns = [
        '      <button type="button" class="subtab" data-sub="hot"'
        f' data-title="熱門新聞分析" data-meta="{escape(HOT_META)}"'
        ' aria-selected="true">熱門分析</button>',
        '      <button type="button" class="subtab" data-sub="digest"'
        f' data-title="今日重點" data-meta="{escape(DIGEST_META)}"'
        ' aria-selected="false">重點</button>',
    ]
    for s in SOURCES:
        btns.append(
            f'      <button type="button" class="subtab" data-sub="{s["id"]}"'
            f' data-title="{escape(s["label"])}" data-meta="{escape(META)}"'
            f' aria-selected="false">{escape(s["label"])}</button>'
        )
    return ('  <div class="subtabs" role="tablist" aria-label="新聞來源">\n'
            + "\n".join(btns) + "\n  </div>")




def _source_html(source: dict, part: pd.DataFrame) -> str:
    """
    各來源的清單不寫在頁面裡（五個來源約三百則，佔掉首頁一百多 KB），
    只留空殼，點進子分頁時才下載 news/list-{來源}.json 由前端排出來。
    """
    if part.empty:
        return ('    <p class="cal-empty">目前沒有抓到這個來源的新聞。</p>')

    # .news-more 同時是捲動哨兵與備援按鈕，超過首批則數時才會出現；
    # .news-article 是共用的內文殼，點哪一則就填哪一則。
    return (f'    <ul class="news-list" data-list="{source["id"]}">\n'
            '      <li class="cal-empty">載入中…</li>\n    </ul>\n'
            '    <button type="button" class="news-more" hidden>載入更多</button>\n'
            '    <div class="news-article" hidden>\n'
            '      <h2 class="news-h"></h2>\n'
            '      <div class="news-meta"></div>\n'
            '      <div class="news-body"></div>\n'
            '      <a class="news-link" target="_blank" rel="noopener">看原文 ↗</a>\n'
            '    </div>')


def lists(data: dict) -> dict:
    """每個來源的清單 [[序號, 有無內文, 網址, 標題, 時間與來源]]，寫成 news/list-{來源}.json。"""
    df = data.get("news", pd.DataFrame())
    out = {}
    for source in SOURCES:
        part = df[df["source"] == source["id"]] if not df.empty else df
        rows = []
        for n, (_, e) in enumerate(part.iterrows()):
            when = when_label(e["published"])
            meta = " · ".join(x for x in (when, source["label"]) if x)
            rows.append([n, 1 if e["body"] else 0, e["url"], e["title"], meta])
        out[source["id"]] = rows
    return out


def bodies(data: dict) -> dict:
    """每個來源一份 {序號: 內文}，寫成 site/news/{來源}.json。"""
    df = data.get("news", pd.DataFrame())
    out = {}
    for source in SOURCES:
        part = df[df["source"] == source["id"]] if not df.empty else df
        out[source["id"]] = {
            str(n): e["body"] for n, (_, e) in enumerate(part.iterrows()) if e["body"]
        }
    return out


def watch_terms() -> list[str]:
    """自選股的代號與簡稱，給新聞重點加分用。"""
    from intel_data import stock_master
    from watchlist import load_watchlist

    codes = {w["code"] for w in load_watchlist()}
    if not codes:
        return []
    master = stock_master()
    names = master[master["code"].isin(codes)]["name"].tolist()
    return sorted(codes) + [n for n in names if len(n) >= 2]


def _digest_html(df: pd.DataFrame) -> str:
    """重點：跨來源合併去重、依重要性排序後的短清單。"""
    events = build_digest(df, watch_terms()) if not df.empty else []
    if not events:
        return ('  <div class="subpanel" data-sub="digest" hidden>\n'
                '    <p class="cal-empty">目前沒有可整理的新聞。</p>\n  </div>')

    items = []
    for n, e in enumerate(events):
        when = when_label(e["published"])
        tags = "".join(f'<span class="dg-tag">{escape(t)}</span>' for t in e["topics"])
        srcs = "／".join(e["sources"])
        meta = " · ".join(x for x in (when, srcs) if x)
        summary = (f'          <span class="dg-sum">{escape(e["summary"])}</span>\n'
                   if e["summary"] else "")
        items.append(
            f'      <li class="news-item dg-item" data-n="{e["n"]}"'
            f' data-source="{e["source"]}"'
            f' data-body="{"1" if e["hasBody"] else "0"}"'
            f' data-url="{escape(e["url"])}" role="button" tabindex="0">\n'
            f'        <span class="news-no">{n + 1}</span>\n'
            f'        <span class="news-main">\n'
            f'          <span class="news-title">{escape(e["title"])}</span>\n'
            f'{summary}'
            f'          <span class="news-meta">{escape(meta)}'
            f'{" " + tags if tags else ""}</span>\n'
            f'        </span>\n'
            f'      </li>'
        )

    return ('  <div class="subpanel" data-sub="digest" hidden>\n'
            '    <ul class="news-list">\n' + "\n".join(items) + "\n    </ul>\n"
            '    <button type="button" class="news-more" hidden>載入更多</button>\n'
            '    <div class="news-article" hidden>\n'
            '      <h2 class="news-h"></h2>\n'
            '      <div class="news-meta"></div>\n'
            '      <div class="news-body"></div>\n'
            '      <a class="news-link" target="_blank" rel="noopener">看原文 ↗</a>\n'
            '    </div>\n  </div>')


IMPACT_CLASS = {"利多": "up", "利空": "down"}


def _hot_topic(t: dict, items: dict) -> str:
    stars = "●" * t["importance"] + "○" * (5 - t["importance"])
    tags = "".join(f'<span class="hot-tag">{escape(x)}</span>' for x in t.get("sectors", []))
    tags += "".join(f'<span class="hot-tag is-stock">{escape(x)}</span>' for x in t.get("stocks", []))
    links = []
    times = [items[i]["time"] for i in t.get("ids", []) if i in items and items[i].get("time")]
    latest = when_label(max(times)) if times else ""
    for i in t.get("ids", [])[:3]:
        it = items.get(i)
        if not it:
            continue
        src = escape(" · ".join(x for x in (when_label(it.get("time")), "、".join(dict.fromkeys(it["srcs"]))[:30]) if x))
        title = escape(it["title"])
        link = (f'<a href="{escape(it["url"])}" target="_blank" rel="noopener noreferrer">{title}</a>'
                if it.get("url") else title)
        links.append(f'<li>{link}<span class="hot-src">{src}</span></li>')
    return (f'      <article class="hot-topic imp-{t["importance"]}">\n'
            f'        <div class="hot-head"><span class="hot-imp" title="重要性 {t["importance"]}／5">{stars}</span>'
            f'<span class="hot-impact {IMPACT_CLASS.get(t["impact"], "")}">{escape(t["impact"])}</span>'
            + (f'<span class="hot-time">{escape(latest)}</span>' if latest else "") + '</div>\n'
            f'        <h4>{escape(t["title"])}</h4>\n'
            f'        <p class="hot-sum">{escape(t["summary"])}</p>\n'
            f'        <p class="hot-why">對台股：{escape(t["why"])}</p>\n'
            + (f'        <p class="hot-tags">{tags}</p>\n' if tags else "")
            + (f'        <ul class="hot-links">{"".join(links)}</ul>\n' if links else "")
            + '      </article>')


def _hot_raw(region: dict, label: str) -> str:
    rows = []
    for it in region.get("items", [])[:20]:
        src = escape(" · ".join(x for x in (when_label(it.get("time")), "、".join(dict.fromkeys(it["srcs"]))[:30]) if x))
        title = escape(it["title"])
        link = (f'<a href="{escape(it["url"])}" target="_blank" rel="noopener noreferrer">{title}</a>'
                if it.get("url") else title)
        rows.append(f'<li><span class="hot-rank">{it["id"]}</span>{link}<span class="hot-src">{src}</span></li>')
    srcs = "、".join(region.get("sources", []))
    return (f'      <section><h4>{label}（{escape(srcs)}）</h4>\n'
            f'        <ol class="hot-raw-list">{"".join(rows)}</ol>\n      </section>')


def _hot_html(hot: dict) -> str:
    """熱門分析：國際、台灣熱門新聞歸成事件，對台股的影響與相關族群、個股。"""
    if not hot or not (hot.get("intl") or hot.get("tw")):
        return ('  <div class="subpanel hot" data-sub="hot">\n'
                '    <p class="cal-empty">熱門新聞分析還沒產生：每天 08:00、14:00、21:00 各整理一次。</p>\n'
                '  </div>')
    how = (f'{hot.get("model")} 分析' if hot.get("method") == "claude"
           else "只有熱門排行（尚未設定 ANTHROPIC_API_KEY，沒有 AI 分析）")
    parts = [f'  <div class="subpanel hot" data-sub="hot">\n'
             f'    <p class="hot-meta">{escape(hot.get("label", ""))}　·　{escape(hot.get("generated", ""))}'
             f'　·　{escape(how)}　·　依各來源名次與重複報導估計熱度</p>']
    if hot.get("headline"):
        parts.append(f'    <p class="hot-headline">{escape(hot["headline"])}</p>')
    if hot.get("method") == "claude":
        parts.append('    <div class="hot-grid">')
        for region, label in (("intl", "國際"), ("tw", "台灣")):
            data = hot.get(region) or {}
            items = {it["id"]: it for it in data.get("items", [])}
            topics = data.get("topics", [])
            parts.append(f'     <section class="hot-col"><h3>{label}</h3>')
            parts += [_hot_topic(t, items) for t in topics] or ['      <p class="cal-empty">沒有整理出事件。</p>']
            parts.append('     </section>')
        parts.append('    </div>')
        parts.append('    <details class="hot-raw"><summary>熱門排行原文</summary>\n    <div class="hot-grid">')
    else:
        parts.append('    <div class="hot-grid">')
    parts.append(_hot_raw(hot.get("intl") or {}, "國際"))
    parts.append(_hot_raw(hot.get("tw") or {}, "台灣"))
    parts.append('    </div>' + ('</details>' if hot.get("method") == "claude" else ""))
    parts.append('    <p class="sd-note">AI 判讀僅供參考，不是投資建議；點標題看原文。</p>\n  </div>')
    return "\n".join(parts)


def panel_html(data: dict) -> str:
    """產生新聞分頁的內容（不含 <section> 外框）。"""
    df = data.get("news", pd.DataFrame())

    body = [_hot_html(data.get("hot") or {}), _digest_html(df)]
    for source in SOURCES:
        part = df[df["source"] == source["id"]] if not df.empty else df
        body.append(
            f'  <div class="subpanel" data-sub="{source["id"]}" hidden>\n'
            f'{_source_html(source, part)}\n  </div>'
        )

    return _subtabs_html() + "\n" + "\n".join(body)
