"""
產生 GitHub Pages 用的靜態頁面 docs/index.html

沒有伺服器端 callback，改把淺色 / 深色兩份圖表 JSON 內嵌進頁面，
由前端 Plotly.react 切換。hover、legend 點選隱藏型號、框選縮放等
Plotly 原生互動全部保留。

    python build_static.py
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path

import plotly.io as pio

from chart import build_figure
from dram_data import BASE_DIR, latest_date, load_dram

DOCS_DIR = BASE_DIR / "docs"
OUTPUT = DOCS_DIR / "index.html"

TPL = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DRAM 現貨報價</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  :root { --bg: #ffffff; --fg: #212529; --muted: #6c757d; --border: #dee2e6; }
  html[data-theme="dark"] { --bg: #1e2130; --fg: #e8e8e8; --muted: #9aa0ac; --border: #333849; }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg);
         font-family: -apple-system, "Segoe UI", "Microsoft JhengHei", sans-serif;
         transition: background .2s, color .2s; }
  .wrap { max-width: 1400px; margin: 0 auto; padding: 24px 20px 40px; }
  header { display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
           justify-content: space-between; margin-bottom: 16px; }
  h1 { font-size: 20px; margin: 0 0 4px; font-weight: 600; }
  .meta { font-size: 13px; color: var(--muted); }
  #toggle { cursor: pointer; font-size: 13px; padding: 7px 14px; border-radius: 6px;
            border: 1px solid var(--border); background: transparent; color: var(--fg); }
  #toggle:hover { border-color: var(--muted); }
  #chart { width: 100%; height: 600px; }
  footer { margin-top: 20px; font-size: 12px; color: var(--muted); line-height: 1.7; }
  footer a { color: inherit; }
  @media (max-width: 640px) { #chart { height: 460px; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>DRAM 現貨報價趨勢</h1>
      <div class="meta">資料來源：TrendForce　最後報價日：__LATEST__</div>
    </div>
    <button id="toggle" type="button">深色模式</button>
  </header>

  <div id="chart"></div>

  <footer>
    共 __ROWS__ 筆報價，__ITEMS__ 種型號，區間 __RANGE__。<br>
    圖表由 <a href="https://github.com/ChrisHo0317/Local_Dashboard">Local_Dashboard</a> 每日自動更新　·　
    頁面產生時間：__BUILT__
  </footer>
</div>

<script>
const FIG_LIGHT = __FIG_LIGHT__;
const FIG_DARK  = __FIG_DARK__;
const CONFIG = {responsive: true, displaylogo: false};

function render(dark) {
  const fig = dark ? FIG_DARK : FIG_LIGHT;
  Plotly.react('chart', fig.data, fig.layout, CONFIG);
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  document.getElementById('toggle').textContent = dark ? '淺色模式' : '深色模式';
}

let dark = false;
try {
  const saved = localStorage.getItem('dram-theme');
  dark = saved ? saved === 'dark'
               : window.matchMedia('(prefers-color-scheme: dark)').matches;
} catch (e) { dark = false; }

render(dark);

document.getElementById('toggle').addEventListener('click', () => {
  dark = !dark;
  render(dark);
  try { localStorage.setItem('dram-theme', dark ? 'dark' : 'light'); } catch (e) {}
});
</script>
</body>
</html>
"""


def build() -> Path:
    """讀 CSV、產生 docs/index.html，回傳輸出路徑。"""
    df = load_dram()

    if df.empty:
        rows = items = 0
        date_range = "無資料"
    else:
        rows = len(df)
        items = df["item"].nunique()
        first = df["price_date"].min().strftime("%Y-%m-%d")
        date_range = f"{first} ～ {latest_date(df)}"

    built = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M (UTC+8)")

    html = (
        TPL.replace("__FIG_LIGHT__", pio.to_json(build_figure(df, dark=False)))
           .replace("__FIG_DARK__", pio.to_json(build_figure(df, dark=True)))
           .replace("__LATEST__", latest_date(df) or "無資料")
           .replace("__ROWS__", str(rows))
           .replace("__ITEMS__", str(items))
           .replace("__RANGE__", date_range)
           .replace("__BUILT__", built)
    )

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"[完成] 已產生 {path}（{path.stat().st_size // 1024} KB）")
