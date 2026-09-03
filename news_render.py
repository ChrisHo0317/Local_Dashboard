"""
把新聞轉成靜態 HTML

每個來源一個子分頁，內容是條列式清單；點任一則會切到內文檢視，
左上角有返回鍵回到清單。

清單（標題、時間、連結）寫在頁面裡，內文另外存成 docs/news/{來源}.json，
點開某一則時才抓，同一個來源只抓一次。內文佔了新聞資料的九成以上，
每個來源 60 則全部內嵌會讓首頁大到不合理。

時間換算成台北時間（UTC+8，固定位移，不依賴系統的 tz 資料庫）。
"""
from datetime import datetime, timedelta, timezone
from html import escape

import pandas as pd

from news_sources import SOURCES

TAIPEI = timezone(timedelta(hours=8))

META = "資料來源：各新聞網站　·　點標題可看內文"


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


def _subtabs_html() -> str:
    btns = []
    for i, s in enumerate(SOURCES):
        btns.append(
            f'      <button type="button" class="subtab" data-sub="{s["id"]}"'
            f' data-title="{escape(s["label"])}" data-meta="{escape(META)}"'
            f' aria-selected="{"true" if i == 0 else "false"}">{escape(s["label"])}</button>'
        )
    return ('  <div class="subtabs" role="tablist" aria-label="新聞來源">\n'
            + "\n".join(btns) + "\n  </div>")


def _when(value: str) -> str:
    """RSS 有時間就顯示台北時間；HTML 來源沒有時間就留空。"""
    if not value:
        return ""
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return ""
    local = ts.tz_convert(TAIPEI)
    return f"{local.month}/{local.day:02d} {local.strftime('%H:%M')}"


def _source_html(source: dict, part: pd.DataFrame) -> str:
    if part.empty:
        return ('    <p class="cal-empty">目前沒有抓到這個來源的新聞。</p>')

    items = []
    for n, (_, e) in enumerate(part.iterrows()):
        when = _when(e["published"])
        meta = " · ".join(x for x in (when, source["label"]) if x)
        # 標題、時間、連結都掛在清單項目上，內文檢視要用時再取 ——
        # 每則各存一份內文檢視的話，同樣的標題會在頁面裡出現兩次。
        items.append(
            f'      <li class="news-item" data-n="{n}"'
            f' data-body="{"1" if e["body"] else "0"}"'
            f' data-url="{escape(e["url"])}" role="button" tabindex="0">\n'
            f'        <span class="news-no">{n + 1}</span>\n'
            f'        <span class="news-main">\n'
            f'          <span class="news-title">{escape(e["title"])}</span>\n'
            f'          <span class="news-meta">{escape(meta)}</span>\n'
            f'        </span>\n'
            f'      </li>'
        )

    # .news-more 同時是捲動哨兵與備援按鈕，超過首批則數時才會出現；
    # .news-article 是共用的內文殼，點哪一則就填哪一則。
    return ('    <ul class="news-list">\n' + "\n".join(items) + "\n    </ul>\n"
            '    <button type="button" class="news-more" hidden>載入更多</button>\n'
            '    <div class="news-article" hidden>\n'
            '      <h2 class="news-h"></h2>\n'
            '      <div class="news-meta"></div>\n'
            '      <div class="news-body"></div>\n'
            '      <a class="news-link" target="_blank" rel="noopener">看原文 ↗</a>\n'
            '    </div>')


def bodies(data: dict) -> dict:
    """每個來源一份 {序號: 內文}，寫成 docs/news/{來源}.json。"""
    df = data.get("news", pd.DataFrame())
    out = {}
    for source in SOURCES:
        part = df[df["source"] == source["id"]] if not df.empty else df
        out[source["id"]] = {
            str(n): e["body"] for n, (_, e) in enumerate(part.iterrows()) if e["body"]
        }
    return out


def panel_html(data: dict) -> str:
    """產生新聞分頁的內容（不含 <section> 外框）。"""
    df = data.get("news", pd.DataFrame())

    body = []
    for i, source in enumerate(SOURCES):
        part = df[df["source"] == source["id"]] if not df.empty else df
        hidden = "" if i == 0 else " hidden"
        body.append(
            f'  <div class="subpanel" data-sub="{source["id"]}"{hidden}>\n'
            f'{_source_html(source, part)}\n  </div>'
        )

    return _subtabs_html() + "\n" + "\n".join(body)
