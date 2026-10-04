"""
指數與 ETF 成分股調整的生效日（依指數公司的固定慣例推算，標「預估」，實際以公告為準）

    MSCI 季度調整           2、5、8、11 月的最後一個營業日收盤生效（5、11 月是半年度大調整）
    FTSE 系列季度調整       3、6、9、12 月第三個星期五收盤後生效
                            （臺灣50／0050、006208，臺灣中型100／0051，富時全球指數）
    臺灣高股息／0056        6、12 月第三個星期五收盤後生效（半年調整）
    MSCI ESG 高股息／00878  跟 MSCI 半年度調整，5、11 月最後一個營業日

名單通常在生效前 2～3 週公布；生效日當天收盤常有被動資金的大量買賣（尾盤爆量）。
沒有考慮台股休市日（遇到休市通常提前一天）。
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

NOTE = "預估日期：依指數公司慣例推算，實際以公告為準；名單約在生效前 2～3 週公布"


def _last_weekday(y: int, m: int) -> date:
    d = date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _third_friday(y: int, m: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(4 - d.weekday()) % 7)
    return d + timedelta(days=14)


def events(start: date, end: date) -> list[dict]:
    """[{date, title, note}]，start～end（含）之間的調整生效日。"""
    out = []
    for y in range(start.year, end.year + 1):
        for m in (2, 5, 8, 11):
            big = m in (5, 11)
            title = "MSCI " + ("半年度" if big else "季度") + "調整生效（收盤）"
            if big:
                title += "　·　00878 同步調整"
            out.append({"date": _last_weekday(y, m), "title": title, "note": NOTE})
        for m in (3, 6, 9, 12):
            title = "FTSE 季度調整生效（臺灣50／0050、中型100、富時全球）"
            if m in (6, 12):
                title += "　·　0056 半年調整"
            out.append({"date": _third_friday(y, m), "title": title, "note": NOTE})
    return sorted((e for e in out if start <= e["date"] <= end), key=lambda e: e["date"])
