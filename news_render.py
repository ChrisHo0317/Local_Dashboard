"""
把新聞轉成靜態 HTML

每個來源一個子分頁，內容是條列式清單；點任一則會切到內文檢視，
左上角有返回鍵回到清單。清單與內文都是產生頁面時就寫好的靜態內容，
切換只是顯示／隱藏，不需要再連線。

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

    items, articles = [], []
    for n, (_, e) in enumerate(part.iterrows()):
        key = f'{source["id"]}-{n}'
        when = _when(e["published"])
        meta = " · ".join(x for x in (when, source["label"]) if x)

        items.append(
            f'      <li class="news-item" data-article="{key}" role="button" tabindex="0">\n'
            f'        <span class="news-no">{n + 1}</span>\n'
            f'        <span class="news-main">\n'
            f'          <span class="news-title">{escape(e["title"])}</span>\n'
            f'          <span class="news-meta">{escape(meta)}</span>\n'
            f'        </span>\n'
            f'      </li>'
        )

        if e["body"]:
            paras = "\n".join(f'        <p>{escape(line)}</p>'
                              for line in e["body"].split("\n") if line.strip())
        else:
            paras = ('        <p class="news-nobody">這則新聞抓不到內文'
                     '（可能是影音報導或需要訂閱），請點下方連結看原文。</p>')

        articles.append(
            f'    <div class="news-article" data-article="{key}" hidden>\n'
            f'      <button type="button" class="news-back">← 返回列表</button>\n'
            f'      <h2 class="news-h">{escape(e["title"])}</h2>\n'
            f'      <div class="news-meta">{escape(meta)}</div>\n'
            f'      <div class="news-body">\n{paras}\n      </div>\n'
            f'      <a class="news-link" href="{escape(e["url"])}" target="_blank"'
            f' rel="noopener">看原文 ↗</a>\n'
            f'    </div>'
        )

    return ('    <ul class="news-list">\n' + "\n".join(items) + "\n    </ul>\n"
            + "\n".join(articles))


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
