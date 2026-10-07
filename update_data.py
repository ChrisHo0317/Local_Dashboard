"""
更新各資料集 → 併入 data/

    python update_data.py                    全部
    python update_data.py market chips       只跑其中幾項
    python update_data.py market --since 2026-09-09   從某天開始補全市場日資料

供 GitHub Actions 排程與手動更新共用。網頁不在這裡產生：排程更新完資料後，
由 deploy 工作流程執行 build_static.py 並發布；本機要看就自己跑 build_static.py。

任一來源抓不到資料時「只警告、不失敗」（exit code 0），避免對方擋爬蟲時
把 workflow 弄成紅燈，也絕不會覆寫既有的資料。
"""
import logging
import sys
from datetime import date, timedelta

import pandas as pd
from curl_cffi import requests as cffi_requests

import fundamentals as fund
import market_data as md
import stock_news
from bond_data import CSV_PATH as BOND_CSV, merge_yields
from bond_scraper import MoneyDJBondScraper
from btc_data import CSV_PATH as BTC_CSV, merge_prices as merge_btc
from btc_scraper import YahooBTCScraper
from calendar_data import CSV_PATH as CAL_CSV, drop_legacy_overlap, merge_events
from calendar_scraper import ForexFactoryCalendarScraper
from chip_data import merge_futures, save_tdcc
from chip_scraper import ChipScraper
from dram_data import CSV_PATH as DRAM_CSV, merge_prices
from f1_data import (CSV_PATH as F1_CSV, SERIES_CSV, STANDINGS_CSV,
                     merge_points_series, merge_schedule, merge_standings)
from f1_scraper import F1CalendarScraper, F1StandingsScraper
from gold_data import CSV_PATH as GOLD_CSV, merge_prices as merge_gold
from gold_scraper import YahooGoldScraper
from finmind_fallback import FinMindFallback
from intel_data import today_taipei
from market_scraper import MarketScraper
from news_data import CSV_PATH as NEWS_CSV, known_articles, merge_news
from news_scraper import NewsScraper
from scraper import TrendForceScraper
from stock_data import load as load_stock, merge as merge_stock
from stock_scraper import StockScraper
from spacex_data import CSV_PATH as SPACEX_CSV, merge_launches
from spacex_scraper import SpaceXScraper
from watchlist import load_watchlist
from xmarket_data import CSV_PATH as XMARKET_CSV, merge_prices as merge_xmarket
from xmarket_scraper import XMarketScraper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("update_data")

# 殖利率 API 可帶區間，平常只要回頭抓一小段就能補上假日與漏抓；
# CSV 不存在時（第一次執行）才整段回補。
BOND_HISTORY_START = date(2023, 1, 1)   # 1年期的資料從 2023-01-03 才有
BOND_LOOKBACK_DAYS = 30

# 金價同理：平常只取近一個月，首次執行才整段回補
GOLD_HISTORY_RANGE = "5y"
GOLD_LOOKBACK_RANGE = "1mo"

# 比特幣同理
BTC_HISTORY_RANGE = "5y"
BTC_LOOKBACK_RANGE = "1mo"

# 全市場日資料：每次回頭檢查幾天，缺什麼補什麼（休市、晚公布、上次失敗都能自己補上）
MARKET_LOOKBACK_DAYS = 7
CLOSED_PATH = md.MARKET_DIR / "closed.txt"


def update_dram() -> int:
    """DRAM 現貨報價：TrendForce 每次只提供當日快照。"""
    rows = TrendForceScraper(logger=log).fetch_dram_spot()
    if not rows:
        log.warning("DRAM：未取得任何報價（TrendForce 可能擋下請求），本次不更新")
        return 0
    added = merge_prices(rows)
    log.info(f"DRAM：抓取 {len(rows)} 筆，新增 {added} 筆至 {DRAM_CSV.name}")
    return added


def update_bonds() -> int:
    """美國公債殖利率：MoneyDJ 提供歷史區間，回頭抓一段可自我修補缺漏。"""
    if BOND_CSV.exists():
        start = date.today() - timedelta(days=BOND_LOOKBACK_DAYS)
    else:
        start = BOND_HISTORY_START
        log.info(f"美債：首次執行，自 {start} 起整段回補")

    rows = MoneyDJBondScraper(logger=log).fetch_yields(start, date.today())
    if not rows:
        log.warning("美債：未取得任何資料（MoneyDJ 可能擋下請求），本次不更新")
        return 0
    added = merge_yields(rows)
    log.info(f"美債：抓取 {len(rows)} 筆，新增 {added} 筆至 {BOND_CSV.name}")
    return added


def update_gold() -> int:
    """國際金價：Yahoo Finance 提供歷史區間，回頭抓一段可自我修補缺漏。"""
    if GOLD_CSV.exists():
        period = GOLD_LOOKBACK_RANGE
    else:
        period = GOLD_HISTORY_RANGE
        log.info(f"黃金：首次執行，整段回補 {period}")

    rows = YahooGoldScraper(logger=log).fetch_prices(period)
    if not rows:
        log.warning("黃金：未取得任何資料（Yahoo Finance 可能拒絕請求），本次不更新")
        return 0
    added = merge_gold(rows)
    log.info(f"黃金：抓取 {len(rows)} 筆，新增 {added} 筆至 {GOLD_CSV.name}")
    return added


def update_btc() -> int:
    """比特幣價格：Yahoo Finance 提供歷史區間，回頭抓一段可自我修補缺漏。"""
    if BTC_CSV.exists():
        period = BTC_LOOKBACK_RANGE
    else:
        period = BTC_HISTORY_RANGE
        log.info(f"比特幣：首次執行，整段回補 {period}")

    rows = YahooBTCScraper(logger=log).fetch_prices(period)
    if not rows:
        log.warning("比特幣：未取得任何資料（Yahoo Finance 可能拒絕請求），本次不更新")
        return 0
    added = merge_btc(rows)
    log.info(f"比特幣：抓取 {len(rows)} 筆，新增 {added} 筆至 {BTC_CSV.name}")
    return added


def update_calendar() -> int:
    """財經行事曆：一次抓本月與下個月（來源可指定區間）。"""
    rows = ForexFactoryCalendarScraper(logger=log).fetch_events()
    if not rows:
        log.warning("行事曆：未取得任何事件，本次不更新")
        return 0
    added = merge_events(rows)
    dropped = drop_legacy_overlap()
    if dropped:
        log.info(f"行事曆：清掉 {dropped} 筆換來源前的重複資料")
    log.info(f"行事曆：抓取 {len(rows)} 筆，新增 {added} 筆至 {CAL_CSV.name}")
    return added + dropped


def update_f1() -> int:
    """F1 賽程：來源一次提供整季，以最新抓到的為準（賽程會改期）。"""
    rows = F1CalendarScraper(logger=log).fetch_schedule()
    if not rows:
        log.warning("F1：未取得任何場次（頁面可能改版），本次不更新")
        return 0
    changed = merge_schedule(rows)
    log.info(f"F1 賽程：抓取 {len(rows)} 個場次，"
             + (f"已更新 {F1_CSV.name}" if changed else "與現有資料相同"))
    return changed


def update_f1_standings() -> int:
    """
    F1 積分榜與逐站積分走勢：同一個頁面就有，一次抓完。
    每站之後都會變，一律以最新抓到的為準。
    """
    year = date.today().year
    data = F1StandingsScraper(logger=log).fetch(year)
    if not data["standings"] and not data["series"]:
        log.warning("F1 積分榜：未取得任何資料（頁面可能改版），本次不更新")
        return 0

    changed = merge_standings(data["standings"])
    log.info(f"F1 積分榜：抓取 {len(data['standings'])} 筆，"
             + (f"已更新 {STANDINGS_CSV.name}" if changed else "與現有資料相同"))

    changed_series = merge_points_series(data["series"])
    log.info(f"F1 積分走勢：抓取 {len(data['series'])} 筆，"
             + (f"已更新 {SERIES_CSV.name}" if changed_series else "與現有資料相同"))

    return changed + changed_series


def update_spacex() -> int:
    """SpaceX 發射：來源一次提供整份清單，發射時間常改期，以最新抓到的為準。"""
    rows = SpaceXScraper(logger=log).fetch_launches()
    if not rows:
        log.warning("SpaceX：未取得任何資料（API 可能改版），本次不更新")
        return 0
    changed = merge_launches(rows)
    log.info(f"SpaceX：抓取 {len(rows)} 筆，"
             + (f"已更新 {SPACEX_CSV.name}" if changed else "與現有資料相同"))
    return changed


def update_news() -> int:
    """新聞：逐來源取代。單一來源失敗不影響其他來源。

    只抓清單上新出現的文章的內文，看過的沿用 CSV 裡的 —— 這個排程
    十分鐘跑一次，每次重抓兩百多篇會被對方當成濫用。
    """
    rows = NewsScraper(logger=log).fetch_all(known_articles())
    if not rows:
        log.warning("新聞：所有來源都沒有抓到文章，本次不更新")
        return 0
    changed = merge_news(rows)
    log.info(f"新聞：抓取 {len(rows)} 則，"
             + (f"已更新 {NEWS_CSV.name}" if changed else "與現有資料相同"))
    return changed


def update_stock() -> int:
    """
    個股：最新一期的清單（營收、重訊、財報、除權息，上市＋上櫃）以市場為單位
    整批取代；同時把月營收、單季損益、重訊併進歷史（fundamentals）。
    """
    got = StockScraper(logger=log).fetch_all()
    if not got:
        log.warning("個股：所有資料集都沒抓到，本次不更新")
        return 0
    changed = 0
    for key, by_market in got.items():
        for market, rows in by_market.items():
            changed += merge_stock(key, market, rows)

    rev_list = load_stock("revenue")
    cur, prev = fund.revenue_from_list(rev_list)
    added = fund.upsert_revenue(cur) + fund.upsert_revenue(prev, overwrite=False)
    if not cur.empty:
        latest = (int(cur["year"].max()), int(cur[cur["year"] == cur["year"].max()]["month"].max()))
        gaps = fund.revenue_gaps(latest)
        if gaps:
            session = cffi_requests.Session(impersonate="chrome124")
            for y, m in gaps:
                filled = fund.upsert_revenue(fund.fetch_mops_revenue(y, m, session, log),
                                             overwrite=False)
                log.info(f"月營收：補 {y}-{m:02d}，新增 {filled} 筆")
                added += filled
    ytd = fund.income_from_list(load_stock("income"))
    single = fund.to_single_quarter(ytd, fund.load_income())
    added += fund.upsert_income(single)
    ann = load_stock("announce")
    added += fund.append_announce(ann)
    log.info(f"個股：清單異動 {changed} 筆，歷史新增或修正 {added} 筆")
    return changed + added


def _closed_days() -> set:
    if not CLOSED_PATH.exists():
        return set()
    return set(CLOSED_PATH.read_text(encoding="utf-8").split())


def _mark_closed(day: date) -> None:
    days = _closed_days() | {day.isoformat()}
    CLOSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLOSED_PATH.write_text("\n".join(sorted(days)) + "\n", encoding="utf-8")


def _history_end() -> date | None:
    path = md.MARKET_DIR / "history_base.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path, columns=["date"])["date"].max().date()


def _fallback(day: date, fm: FinMindFallback) -> int:
    """官方來源那天還缺的資料，只替自選股向 FinMind 補。"""
    watch = [w["code"] for w in load_watchlist()]
    if not watch:
        return 0
    stocks = md.load_stocks()
    markets = dict(zip(stocks["code"], stocks["market"]))
    present = md.present_groups(day)
    changed = 0
    for market in ("twse", "tpex"):
        missing = [g for g in ("quotes", "insti", "margin") if g not in present[market]]
        codes = [c for c in watch if markets.get(c) == market]
        if missing and codes:
            log.info(f"全市場：{day} {market} 缺 {missing}，改用 FinMind 補自選股 {len(codes)} 檔")
            changed += md.save_day(day, fm.fill(day, missing, codes, markets))
    return changed


def update_market(since: date | None = None) -> int:
    """
    上市＋上櫃每日收盤、三大法人、融資融券、本益比。每次回頭檢查幾天，
    只抓缺的那幾類。休市日記在 closed.txt，之後不再重問。
    """
    today = today_taipei()
    start = since or today - timedelta(days=MARKET_LOOKBACK_DAYS)
    base_end = _history_end()
    closed = _closed_days()
    scraper = MarketScraper(logger=log)
    fm = None
    changed = 0
    day = start
    while day <= today:
        if day.weekday() >= 5 or day.isoformat() in closed or (base_end and day <= base_end):
            day += timedelta(days=1)
            continue
        present = md.present_groups(day)
        need = {m: set(md.GROUPS) - present[m] - md.LATEST_ONLY[m] - md.UNAVAILABLE[m]
                for m in ("twse", "tpex")}
        if any(need.values()):
            out = scraper.fetch(day, need)
            if out["closed"]:
                if day < today:
                    _mark_closed(day)
                    log.info(f"全市場：{day} 休市")
            else:
                n = sum(md.save_day(day, f) for f in out["frames"])
                n += md.merge_summary(day, out["summary"])
                for names in out["names"]:
                    md.merge_stocks(names)
                log.info(f"全市場：{day} 抓 {len(out['frames'])} 類，檔案{'有更新' if n else '無變動'}")
                changed += n
                if day < today:
                    fm = fm or FinMindFallback(logger=log)
                    changed += _fallback(day, fm)
        day += timedelta(days=1)
    changed += _tpex_latest(scraper)
    return changed


def _tpex_latest(scraper) -> int:
    """上櫃借券賣出與當沖比重只有最新一天，存到官方回報的那天（那天的日期檔要已經在）。"""
    got = scraper.tpex_latest()
    n = 0
    day = got["lending_day"]
    if day and got["lending"] is not None and md._path(date.fromisoformat(day)).exists():
        n += md.save_day(date.fromisoformat(day), got["lending"])
    for d, pct in (got["daytrade"] or {}).items():
        if pct is not None:
            n += md.merge_summary(date.fromisoformat(d), {"tpex_daytrade_pct": pct})
    return n


def repair_history() -> int:
    """
    一次性修補：market_db 匯出的歷史裡，有幾天只有一個市場有資料（例如上市那天漏抓），
    會讓 K 線缺一根、法人合計少一半、N 日漲跌算錯天數。找出這些日子，
    向官方依日期補回缺的那個市場，併進 history_base.parquet。

        python update_data.py repair
    """
    path = md.MARKET_DIR / "history_base.parquet"
    if not path.exists():
        return 0
    base = pd.read_parquet(path)
    universe = set(base["code"])
    counts = base.groupby(["date", "market"]).size().unstack(fill_value=0)
    typical = counts.median()
    scraper = MarketScraper(logger=log)
    added = []
    for day, row in counts.iterrows():
        need = {m: {"quotes", "insti", "margin"}
                for m in ("twse", "tpex") if row.get(m, 0) < typical.get(m, 0) * 0.9}
        if not need:
            continue
        out = scraper.fetch(day.date(), need)
        if out["closed"] or not out["frames"]:
            log.warning(f"修補：{day.date()} 官方也沒有資料，略過")
            continue
        merged = None
        for f in out["frames"]:
            f = f[f["code"].isin(universe)]
            merged = f if merged is None else merged.merge(f, on=["code", "market"], how="outer")
        merged = merged.assign(date=day).reindex(columns=base.columns)
        added.append(merged)
        log.info(f"修補：{day.date()} 補 {', '.join(need)} 共 {len(merged)} 檔")
    if not added:
        log.info("修補：歷史沒有缺漏")
        return 0
    fixed = pd.concat([base] + added, ignore_index=True)
    fixed = fixed.drop_duplicates(["date", "code"], keep="first").sort_values(["code", "date"])
    for col in ("open", "high", "low", "close"):
        fixed[col] = fixed[col].astype("float32")
    for col in ("volume", "turnover", "foreign", "trust", "dealer", "margin_bal", "short_bal"):
        fixed[col] = pd.to_numeric(fixed[col], errors="coerce").round().astype("Int64")
    fixed.reset_index(drop=True).to_parquet(path, index=False, compression="zstd",
                                            compression_level=19)
    return sum(len(a) for a in added)


def update_events() -> int:
    """權值事件（除權息、減資、變更面額）與注意股、處置股：每次回頭抓近 45 天，順便看未來幾天。"""
    today = today_taipei()
    scraper = MarketScraper(logger=log)
    added = md.merge_events(scraper.events(today - timedelta(days=45), today + timedelta(days=10)))
    flags = md.merge_flags(scraper.flags())
    log.info(f"權值事件：新增 {added} 筆；注意／處置：{'有更新' if flags else '無變動'}")
    return added + flags


BACKFILL_LIMIT = 80   # 每次最多重抓幾天，排程每次補一些，補完就什麼都不做


def backfill(limit: int = BACKFILL_LIMIT) -> int:
    """
    歷史資料回補（可以重複執行，做完的不會再抓）：

      1. 權值事件表比歷史起點晚 → 從歷史起點補抓證交所的除權息、減資、變更面額
      2. 歷史底稿（一次性匯出的那段）：
           上市：收盤記成 0、但當天有成交的日子 → 重抓收盤行情修正零價
           上櫃：每一天都重抓收盤行情 → 修正零價並取得參考價（還原權值用）
         一天一個市場寫一個修補檔（data/market/patch/），寫過就不再抓
      3. 之後的日期檔裡上櫃沒有參考價的（加這欄以前抓的）→ 重抓收盤行情補上

    新的日子優先（強勢股、類股看的是最近幾個月）。
    """
    path = md.MARKET_DIR / "history_base.parquet"
    scraper = MarketScraper(logger=log)
    done = 0
    if path.exists():
        base = pd.read_parquet(path, columns=["date", "code", "market", "close", "volume"])
        start = base["date"].min().date()
        events = md.load_events()
        if events.empty or pd.Timestamp(events["date"].min()) > pd.Timestamp(start) + pd.Timedelta(days=10):
            done += md.merge_events(scraper.events(start, today_taipei()))
        bad = base[((base["close"] <= 0) | base["close"].isna()) & (base["volume"] > 0)]
        need = []
        for day in sorted(base["date"].unique(), reverse=True):
            d = pd.Timestamp(day).date()
            if not md.patch_path(d, "tpex").exists():
                need.append((d, "tpex"))
            twse_bad = bad[(bad["date"] == day) & (bad["market"] == "twse")]
            if len(twse_bad) and not md.patch_path(d, "twse").exists():
                need.append((d, "twse"))
        base_end = base["date"].max().date()
    else:
        base, bad, need, base_end = None, None, [], None
    # 之後的日期檔：上櫃沒有參考價的
    for d in sorted(md.dates(), reverse=True):
        if base_end and d <= base_end:
            continue
        day = md.load_day(d)
        tp = day[day["market"] == "tpex"]
        if len(tp) and tp["ref"].isna().all():
            need.append((d, "tpex-day"))
    need.sort(key=lambda x: x[0], reverse=True)
    if not need:
        log.info("回補：歷史資料都補齊了")
        return done
    for d, kind in need[:limit]:
        market = "twse" if kind == "twse" else "tpex"
        df = scraper.quotes(d, market)
        if df is None or df.empty:
            log.warning(f"回補：{d} {market} 抓不到，下次再試")
            continue
        if kind == "tpex-day":
            done += md.save_day(d, df)
            continue
        df = df.copy()
        rows = base[(base["date"] == pd.Timestamp(d)) & (base["market"] == market)]
        broken = set(rows.loc[(rows["close"] <= 0) | rows["close"].isna(), "code"])
        fix = df["code"].isin(broken)
        for col in ("open", "high", "low", "close"):
            df.loc[~fix, col] = float("nan")          # 只修壞掉的價格，其他保留底稿原值
        if market == "twse":
            df = df[fix]
        md.save_patch(d, market, df)
        done += 1
    left = max(len(need) - limit, 0)
    log.info(f"回補：這次補 {min(len(need), limit)} 天，還剩 {left} 天")
    return done


def update_signal_log() -> int:
    """選股條件當天的命中名單記下來（訊號績效的往後追蹤）。"""
    import intel_data
    import signal_perf
    import signals
    from chip_data import load_tdcc
    panel = intel_data.daily_panel(260)
    if panel.empty:
        return 0
    master = intel_data.stock_master()
    results = signals.run(panel, fund.load_revenue(), intel_data.pe_series(panel), load_tdcc(), master)
    day = panel["date"].max().strftime("%Y-%m-%d")
    n = signal_perf.append_log(day, results)
    log.info(f"訊號紀錄：{day} {'記錄 ' + str(n) + ' 筆' if n else '與上次相同'}")
    return int(bool(n))


def update_chips() -> int:
    """集保股權分散（每週）、期貨三大法人未平倉（每日）。"""
    scraper = ChipScraper(logger=log)
    changed = 0
    day, tdcc = scraper.fetch_tdcc()
    if tdcc is not None and save_tdcc(day, tdcc):
        log.info(f"集保：新增 {day} 共 {len(tdcc)} 檔")
        changed += 1
    fut = scraper.fetch_futures()
    if merge_futures(fut):
        log.info(f"期貨法人：新增 {fut['date']}")
        changed += 1
    return changed


def update_xmarket() -> int:
    """Yahoo Finance 的指數、期貨、龍頭股、原物料、匯率（xmarket_data.SYMBOLS）＋台指期夜盤。"""
    from xmarket_data import SYMBOLS, load_xmarket
    have = set(load_xmarket()["item"]) if XMARKET_CSV.exists() else set()
    scraper = XMarketScraper(logger=log)
    rows = []
    for symbol, name in SYMBOLS:
        # 新加的項目第一次抓 5 年，之後只抓近一個月
        rows += scraper._fetch_one(symbol, name, "1mo" if name in have else "5y")
    import options_data
    rows += options_data.night_rows(logger=log)
    if not rows:
        log.warning("跨市場：未取得任何資料，本次不更新")
        return 0
    added = merge_xmarket(rows)
    log.info(f"跨市場：抓取 {len(rows)} 筆，新增 {added} 筆")
    return added


# 命令列可以只跑其中一項：python update_data.py news
JOBS = {
    "dram": update_dram,
    "bonds": update_bonds,
    "gold": update_gold,
    "btc": update_btc,
    "calendar": update_calendar,
    "f1": update_f1,
    "f1standings": update_f1_standings,
    "spacex": update_spacex,
    "news": update_news,
    "stock": update_stock,
    "market": update_market,
    "chips": update_chips,
    "xmarket": update_xmarket,
    "events": update_events,
    "backfill": backfill,
    "signallog": update_signal_log,
    "options": lambda: __import__("options_data").update(log),
    # 總經：國發會、央行、經濟部、FRED（每天早上與晚上各一次，官方數據大多是月資料）
    "macro": lambda: __import__("macro_data").update(log),
    # 外資持股比率（上市＋上櫃，每日；上櫃 www 被擋時下次再補）
    "qfii": lambda: __import__("qfii_data").update(log),
    # 法說會（公開資訊觀測站，上個月～下個月）
    "calls": lambda: __import__("earnings_calls").update(log),
    # 細產業（櫃買中心產業價值鏈，一週重抓一次）
    "chain": lambda: __import__("industry_chain").update(log),
    # 已發行股數（市場熱度的權值股分項用；每天早上一次）
    "shares": lambda: __import__("shares_data").update(log),
    # 國際／台灣熱門新聞分析：新聞排程每 10 分鐘呼叫，08:00、14:00、21:00 三個時段各做一次
    "hotnews": lambda: __import__("hot_news").update(log),
    # 盤前／盤後摘要（Claude 整理、Bark 推播；依台北時間決定是盤前還是盤後）
    "digest": lambda: __import__("market_digest").update(log),
    # 強勢股新聞與上漲原因（會呼叫 Claude，見 stock_news.py）
    "stocknews": lambda: stock_news.update(log),
}

# 不在預設清單裡的一次性工作（要明確指定才會跑）
MANUAL_JOBS = {"repair": repair_history,
               # 本機一次補完：python update_data.py backfillall
               "backfillall": lambda: backfill(limit=10_000),
               # 不管時段，現在就整理一次熱門新聞
               "hotnewsnow": lambda: __import__("hot_news").update(log, force=True)}


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    since = None
    if "--since" in argv:
        i = argv.index("--since")
        since = date.fromisoformat(argv[i + 1])
        del argv[i:i + 2]
    jobs = {**JOBS, **MANUAL_JOBS}
    if argv:
        unknown = [a for a in argv if a not in jobs]
        if unknown:
            log.error(f"不認得的項目：{' '.join(unknown)}；"
                      f"可用的有 {' '.join(jobs)}")
            return 2
        names = argv
    else:
        names = list(JOBS)

    added = 0
    for name in names:
        added += update_market(since) if name == "market" else jobs[name]()
    log.info("有新資料" if added else "無新資料")
    return 0


if __name__ == "__main__":
    sys.exit(main())
