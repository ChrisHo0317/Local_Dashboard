# Local_Dashboard — 市場走勢

DRAM 現貨報價、美國公債殖利率、國際金價的歷史走勢圖，以及中文化的財經行事曆，資料每日自動更新。

**線上瀏覽：** https://chrisho0317.github.io/Local_Dashboard/

---

## 為什麼有兩個版本

GitHub Pages 只能託管靜態檔案，無法執行 Dash 的伺服器端 callback，因此本專案提供兩種呈現方式，兩者共用同一份資料與同一個 `chart.build_figure()`：

| 版本 | 進入點 | 說明 |
|------|--------|------|
| 本地 Dash | `app.py` | 在自己電腦跑，`http://localhost:8051` |
| 靜態頁面 | `build_static.py` → `docs/index.html` | GitHub Pages 對外瀏覽 |

靜態版把淺色 / 深色兩份圖表 JSON 內嵌進頁面，由前端 `Plotly.react` 切換。hover、框選縮放等 Plotly 原生互動都保留。

## 頁面結構

靜態版分成兩個分頁，由底部懸浮式標籤列切換（切換時指示器會滑動）：

| 分頁 | 內容 |
|------|------|
| DRAM | DRAM 現貨報價（TrendForce）|
| 美債殖利率 | 美國公債 1／2／5／10／20／30 年期殖利率（MoneyDJ）|
| 黃金 | 國際金價 COMEX 近月期貨，USD／盎司（Yahoo Finance）|
| 行事曆 | 財經事件行事曆，中文化、表格呈現（ForexFactory）|
| 設定 | 外觀（深色模式）、各資料集資訊與顯示開關、關於 |

要新增圖表分頁，在 `build_static.py` 的 `PANELS` 加一筆即可 —— 標籤列、分頁、圖例、設定頁的資料卡片都會跟著生成，滑動指示器依按鈕實際位置計算，不需要改任何數值。

版本號顯示於標頭右上角。

設定分頁中每張資料卡片的右上角有顯示開關，可自行決定哪些分頁要出現在底部標籤列；選擇存在瀏覽器的 localStorage，重新開啟仍會保留。

## 圖表操作

- **時間軸縮圖**：圖表下方的橫向縮圖顯示完整區間，拖曳兩端可縮放，主圖同步顯示選取範圍。
- **快速區間**：左上角 `1月` / `3月` / `6月` / `全部` 按鈕。預設顯示最近 3 個月。
- **y 軸自動縮放**：改變時間軸範圍（區間按鈕、拖曳縮圖、雙指縮放）或開關型號後，y 軸會依目前可見的資料重算，短區間才不會擠成一團。
- **手機手勢**：單指**按下當下**就出現垂直指標線與該時間點各型號報價，按住可拖曳移動；
  指標顯示中再輕點一下即收起。雙指縮放時間軸。單指不會平移或框選縮放，
  要回到全區間按左上角「全部」。
- **型號開關**：圖表下方的色點按鈕點開後列出全部 9 個型號，可逐項顯示 / 隱藏，另有「全部顯示 / 全部隱藏」。
  靜態版用這個自製圖例取代 Plotly 內建的那一份 —— 9 個型號橫排在手機上會佔掉大半畫面。

---

## 安裝

```bash
pip install -r requirements.txt
```

## 使用

```bash
python app.py            # 本地 Dash 版 → http://localhost:8051
python build_static.py   # 重新產生 docs/index.html
python update_data.py    # 爬取最新報價 → 更新 CSV → 重建 HTML
```

`export_from_sqlite.py`（匯出初始資料）與 `make_icons.py`（產生圖示）都是一次性工具，一般使用不會用到。

## 加入 iPhone / Android 主畫面

用 Safari 或 Chrome 開啟上方網址 → 分享選單 →「加入主畫面」。
圖示是 K 線與上升趨勢線，名稱為「市場走勢」，開啟後為獨立視窗（無瀏覽器網址列）。

---

## 檔案說明

| 檔案 | 用途 |
|------|------|
| `dram_data.py` | 讀寫 `data/dram_prices.csv`，以 `(item, price_date)` 去重 |
| `bond_data.py` | 讀寫 `data/bond_yields.csv`，同時是年期定義的唯一來源 |
| `bond_scraper.py` | MoneyDJ 殖利率爬蟲（可帶區間取歷史）|
| `gold_data.py` | 讀寫 `data/gold_prices.csv` |
| `gold_scraper.py` | Yahoo Finance 金價爬蟲 |
| `calendar_data.py` | 讀寫 `data/calendar_events.csv` |
| `calendar_scraper.py` | ForexFactory 行事曆爬蟲（官方 JSON feed）|
| `calendar_i18n.py` | 事件名稱／國別／影響程度的中文化 |
| `calendar_render.py` | 行事曆分頁的 HTML 產生 |
| `chart.py` | `build_figure()` / `build_bond_figure()` — 唯一的圖表定義來源 |
| `docs/` | 發佈目錄：`index.html`（產生）+ 圖示與 `manifest.webmanifest`（靜態） |
| `scraper.py` | TrendForce DRAM 現貨報價爬蟲（僅提供當日快照）|
| `update_data.py` | 爬蟲 → 合併 CSV → 重建靜態頁 |
| `build_static.py` | 產生 `docs/index.html` |
| `app.py` | 本地 Dash 版 |
| `export_from_sqlite.py` | 自本機 SQLite 匯出初始 CSV |
| `make_icons.py` | 產生 `docs/` 底下的網站圖示：K 線 + 趨勢線（需 Pillow）|
| `version.py` | 版本號，顯示於頁尾與本地 Dash 標頭 |

## 資料格式

`data/dram_prices.csv`

| 欄位 | 說明 |
|------|------|
| `item` | 型號，如 `DDR5 16Gb (2Gx8) 4800/5600` |
| `price_date` | 報價日期 `YYYY-MM-DD` |
| `avg_price` | 盤平均（USD） |

`data/bond_yields.csv`

| 欄位 | 說明 |
|------|------|
| `item` | 年期，如 `10年期` |
| `price_date` | 日期 `YYYY-MM-DD` |
| `yield_pct` | 殖利率（%）|

`data/gold_prices.csv`

| 欄位 | 說明 |
|------|------|
| `item` | 商品，目前只有 `COMEX 黃金期貨` |
| `price_date` | 日期 `YYYY-MM-DD` |
| `price_usd` | 收盤價（USD／盎司）|

`data/calendar_events.csv`

| 欄位 | 說明 |
|------|------|
| `event_time` | 事件時間，ISO 8601 含時區（來源為紐約時間）|
| `country` | 貨幣／地區代碼 |
| `title` | 英文原名（中文於產生頁面時翻譯，不寫進 CSV）|
| `impact` | High / Medium / Low / Holiday |
| `forecast` / `previous` | 市場預估值與前值 |

---

## 自動更新

`.github/workflows/update.yml` 每日 UTC 01:00（台灣 09:00）執行 `update_data.py`，有新報價才 commit。也可在 Actions 分頁手動觸發。

> GitHub Actions 使用資料中心 IP，TrendForce 的 Cloudflare 有可能擋下請求。`update_data.py` 在抓不到資料時只印警告並正常結束，不會讓 workflow 變紅，也不會覆寫既有 CSV。若長期無法在雲端爬取，可改於本機排程執行 `update_data.py` 後推送。

## 設定（首次部署）

- **Settings → Pages** → Source: `Deploy from a branch` → `main` / `/docs`
- **Settings → Actions → General → Workflow permissions** → `Read and write permissions`

---

## 版本

目前 **v0.3.003**，顯示在頁面右下角與本地 Dash 的標題旁 —— GitHub Pages 與瀏覽器都會快取，用版本號比對才能確定手機上看到的是不是最新版。

格式 `vMAJOR.MINOR.PATCH`，PATCH 固定三位數。**一般改動一律只遞增 PATCH**；前兩組除非明確指示否則不變更。改 `version.py` 後重跑 `build_static.py` 即可。

每日自動更新報價**不算**版本變更，workflow 不會動到 `version.py`。

---

資料來源：[TrendForce 集邦科技](https://www.trendforce.com.tw/price/dram/dram_spot)　·　[MoneyDJ 債券](https://www.moneydj.com/bond/defaultBD.xdjhtm)　·　[Yahoo Finance](https://finance.yahoo.com/quote/GC%3DF/)　·　[ForexFactory](https://www.forexfactory.com/calendar)

---

## 關於金價的資料來源

原本指定的來源是 truney.com，但該站有 Cloudflare 人機驗證，連真實 Chrome 都會停在
「正在執行安全驗證」而逾時，無法用於自動更新。同樣被擋的還有 Stooq（JS proof-of-work）
與台灣銀行黃金存摺頁（JS 渲染）。

最後改用 Yahoo Finance 的 `GC=F`（COMEX 黃金近月期貨），單位為 USD／盎司。
這是連續合約，Yahoo 會自動接續換月，適合看長期趨勢；若要嚴格的單一合約價格則不適用。

## 關於行事曆

forexfactory.com 本站有 Cloudflare，直接抓會 403，但官方另外提供 JSON feed
（`nfs.faireconomy.media/ff_calendar_thisweek.json`）可以正常取得。

兩個限制要知道：

- **只有「本週」一個 feed**，nextweek／lastweek／thismonth 都是 404。所以看得到的
  未來事件僅限本週剩下的日子，歷史則靠每天執行逐週累積。
- **有速率限制**，短時間連抓會回 HTTP 429。每次執行只抓一次，遇到 429 就跳過本次更新。

事件以表格呈現（時間／影響／事件／預估／前值），每天一個 `<tbody>` 讓各天欄位對齊，
並在今天「已過去」與「還沒到」的事件之間插入紅色的現在時間標示線，每 30 秒更新一次。
捲動時標題會釘在畫面上方（說明文字自動收起），表頭與日期依序釘在其下，日期捲到下一天才更換。
時鐘、今天標記、標示線位置全部在瀏覽器端計算 —— 頁面會被 CDN 快取，寫死的話隔天就會標錯。

中文化不使用翻譯 API，改用 `calendar_i18n.py` 的「完整名稱對照表 + 組字規則」：
事件名稱組合性很強（`German Prelim CPI m/m` = 國別前綴 + 修飾語 + 核心指標 + 週期後綴），
拆解後查表即可。查不到的核心詞會保留英文 —— 寧可顯示英文，也不要猜錯財經名詞。
CSV 只存英文原名，改了對照表重跑 `build_static.py` 就會全部更新，不必重抓資料。
