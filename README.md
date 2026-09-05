# Local_Dashboard — 市場走勢

DRAM 現貨報價、美國公債殖利率、國際金價的歷史走勢圖，以及中文化的財經行事曆與 F1 賽程表，資料每日自動更新。

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

分頁先分成幾類，標題下方的分類切換決定底部標籤列顯示哪一組；「設定」不屬於任何一類，
每一組都在。切換分類與分頁時指示器都會滑動。

出廠分成**財經**與**個人追蹤**兩類，但**分類完全可以自己改**：設定分頁的「分類」卡片
可以新增／改名／刪除分組，長按分頁左邊的 ≡ 把它拖到別的分組，或調整組內順序
（底部標籤列的排列會跟著走）。設定存在瀏覽器的 localStorage，換裝置不會跟著走。

- 刪除分組時，裡面的分頁會移到第一個分組，不會消失；最後一個分組不能刪
- 只剩一個分組時，分類切換那一列會自動隱藏（沒有東西好切）
- 開啟頁面時顯示的是**第一組的第一個分頁**，依你排的順序；那一個被關掉就往後找下一個
- 改版新增分頁時，舊的設定裡沒有它，會自動補進它出廠時所屬的那一組

下表的「分類」是出廠值：

| 分類 | 分頁 | 內容 |
|------|------|------|
| 財經 | DRAM | DRAM 現貨報價（TrendForce）|
| 財經 | 美債殖利率 | 美國公債 1／2／5／10／20／30 年期殖利率（MoneyDJ）|
| 財經 | 黃金 | 國際金價 COMEX 近月期貨，USD／盎司（Yahoo Finance）|
| 財經 | 行事曆 | 財經事件行事曆，本月與下月、中／高影響，中文化、表格呈現（FXStreet）|
| 個人追蹤 | F1 | 賽程（清單列出每場大獎賽，點進去看該站場次）／積分（車手、車隊：走勢圖 + 積分榜）（F1 Calendar、f1-boxbox）|
| 財經 | SpaceX | 發射排程，依月份分組、繁體中文（SpaceX 官方 API）|
| 財經 | 個股 | 查詢（即時向證交所查行情與本益比／殖利率／股價淨值比）／營收／重訊／財報（公開資訊觀測站開放資料）|
| 財經 | 新聞 | 第一個子分頁是**重點**（五個來源合併去重、依重要性排序的 30 則，附一句摘要與主題標籤）；其餘子分頁是各來源的完整清單，各 60 則（非凡新聞 30 則）|
| 個人追蹤 | 筆記 | 純本機的文字筆記，存在瀏覽器的 localStorage，不上傳也不進 repo |
| — | 設定 | 外觀（深色模式）、各資料集資訊與顯示開關、關於 |

新聞內文、筆記編輯、F1 單站賽程這類「進到某一則」的畫面，返回鍵和頁面標題一起釘在畫面上方，捲到中段也按得到；
在畫面上**往右滑**也等於按返回鍵。手勢只在有東西可返回時才生效，起點在會橫向捲動的東西上（底部標籤列、
子分頁列）則讓它自己捲；起點在輸入框裡要滑更長（130px）才算，才不會跟移游標混在一起。
F1 賽程與單站場次共用同一張表格，切換的只是要顯示哪些列 —— 篩選、「今天」標記、現在時間標示線都不必各做一份。

要新增圖表分頁，在 `build_static.py` 的 `PANELS` 加一筆即可（`group` 欄位決定歸在哪一類） —— 標籤列、分頁、圖例、設定頁的資料卡片都會跟著生成，滑動指示器依按鈕實際位置計算，不需要改任何數值。

版本號與資料來源說明都在標頭右上角，標題留在左邊。

重新整理沒有按鈕：**頁面捲到最上方時往下拉**即可，拉過門檻會出現向上的箭頭，
放開就重新載入（網址帶一次性參數以繞過 CDN 快取）。加到主畫面之後
（standalone）沒有瀏覽器自己的下拉重新整理，所以這個手勢是自己實作的；
圖表區有自己的觸控處理，要在圖表以外的地方拉。

設定分頁中每張資料卡片預設是收合的，點標題可以展開看該分頁的資料摘要（最後更新日、筆數、涵蓋區間、來源）；
展開了哪幾張同樣記在 localStorage。卡片右上角有顯示開關，可自行決定哪些分頁要出現在底部標籤列；選擇存在瀏覽器的 localStorage，重新開啟仍會保留。

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
| `calendar_scraper.py` | FXStreet 行事曆爬蟲（可指定區間，抓本月與下月）|
| `calendar_i18n.py` | 事件名稱／國別／影響程度的中文化 |
| `calendar_render.py` | 行事曆分頁的 HTML 產生 |
| `f1_data.py` | 讀寫 `data/f1_schedule.csv` |
| `f1_scraper.py` | f1calendar.com 賽程爬蟲 + f1-boxbox 積分榜爬蟲 |
| `f1_render.py` | F1 分頁的 HTML 產生：二／三階分頁 + 賽程表 + 積分榜 |
| `spacex_data.py` | 讀寫 `data/spacex_launches.csv` |
| `spacex_scraper.py` | SpaceX 官方 API 爬蟲 |
| `spacex_i18n.py` | 火箭／任務類型／發射場／回收方式的中文化 |
| `spacex_render.py` | SpaceX 分頁的 HTML 產生 |
| `news_sources.py` | 新聞來源清單（網址、抓取方式、每個來源取幾則）|
| `news_data.py` | 讀寫 `data/news_articles.csv`，每次整批取代 |
| `news_scraper.py` | 各新聞站的清單與內文抓取（RSS 或 HTML）|
| `news_digest.py` | 新聞重點：跨來源合併同一件事、依重要性評分、取內文首段當摘要 |
| `news_render.py` | 新聞分頁的 HTML 產生：重點、各來源清單 + 內文檢視 |
| `notes_render.py` | 筆記分頁的空殼 HTML（內容全在 localStorage，由頁面 JS 繪製）|
| `stock_sources.py` | 個股三個資料集的端點與欄位對照 |
| `stock_scraper.py` | 證交所開放資料爬蟲（月營收、重大訊息、季報損益）|
| `stock_data.py` | 讀寫 `data/stock_*.csv`，整批取代 |
| `stock_render.py` | 個股分頁的 HTML 空殼與 JSON 輸出 |
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

`data/news_articles.csv`

| 欄位 | 說明 |
|------|------|
| `source` | 來源代碼：`ustv` / `yahoo` / `ltn` / `digitimes` / `technews` |
| `order` | 該來源清單上的順序，0 起算 |
| `title` / `url` | 標題與原文網址 |
| `published` | 發布時間 ISO 8601（只有 RSS 來源有）|
| `body` | 內文（截斷至 1200 字；抓不到時留空）|

清單一次列 12 則，捲到底再接 10 則。內文不寫進 index.html，而是每個來源一份
`docs/news/{來源}.json`，點開某一則時才抓、同一個來源只抓一次 —— 內文佔了新聞資料的
九成以上，全部內嵌會讓首頁大到不合理。

因此**本機要用 HTTP 開才看得到內文**（`python -m http.server -d docs`）；
用 `file://` 直接開 `docs/index.html` 會被瀏覽器的 CORS 規則擋掉，
此時內文區會顯示載入失敗並提示改看原文，其餘功能不受影響。

新聞每天換一批，舊的不保留，`update_data.py` 會整批覆寫這個檔案。

---

## 自動更新

兩個排程：

| Workflow | 頻率 | 做什麼 |
|----------|------|--------|
| `update.yml` | 每日 UTC 01:00（台灣 09:00）| 行情、行事曆、F1、SpaceX |
| `news.yml` | 每 10 分鐘 | 只更新新聞 |

兩者都有新資料才 commit，也都可在 Actions 分頁手動觸發。

新聞另外排程是因為一天更新一次等於永遠在看昨天的頭條。為了撐得起這個頻率，
抓取是**增量**的：清單上已經看過的文章直接沿用 CSV 裡的內文，只有新出現的
才連文章頁 —— 一輪通常只有幾篇要抓，十幾秒就跑完（第一次或整批換新時才會久）。

`python update_data.py news` 可以只跑新聞；不帶參數則全跑。可用的項目有
`dram bonds gold calendar f1 f1standings spacex news`。

> GitHub 的排程本來就不準，高頻的 cron 尤其如此，實際間隔可能是十幾分鐘到半小時；
> 加上 Pages 的 CDN 快取（約 10 分鐘），手機上看到的還會再晚一些。**在頁面最上方
> 往下拉**會重新載入並帶一次性參數，可以繞過快取。

> GitHub Actions 使用資料中心 IP，TrendForce 的 Cloudflare 有可能擋下請求。`update_data.py` 在抓不到資料時只印警告並正常結束，不會讓 workflow 變紅，也不會覆寫既有 CSV。若長期無法在雲端爬取，可改於本機排程執行 `update_data.py` 後推送。

## 設定（首次部署）

- **Settings → Pages** → Source: `Deploy from a branch` → `main` / `/docs`
- **Settings → Actions → General → Workflow permissions** → `Read and write permissions`

---

## 版本

目前 **v0.3.041**，顯示在頁面右下角與本地 Dash 的標題旁 —— GitHub Pages 與瀏覽器都會快取，用版本號比對才能確定手機上看到的是不是最新版。

格式 `vMAJOR.MINOR.PATCH`，PATCH 固定三位數。**一般改動一律只遞增 PATCH**；前兩組除非明確指示否則不變更。改 `version.py` 後重跑 `build_static.py` 即可。

每日自動更新報價**不算**版本變更，workflow 不會動到 `version.py`。

---

資料來源：[TrendForce 集邦科技](https://www.trendforce.com.tw/price/dram/dram_spot)　·　[MoneyDJ 債券](https://www.moneydj.com/bond/defaultBD.xdjhtm)　·　[Yahoo Finance](https://finance.yahoo.com/quote/GC%3DF/)　·　[FXStreet](https://www.fxstreet.com/economic-calendar)　·　[非凡新聞](https://news.ustv.com.tw/)　·　[Yahoo 財經](https://tw.news.yahoo.com/finance/)　·　[自由財經](https://ec.ltn.com.tw/)　·　[DIGITIMES](https://www.digitimes.com.tw/)　·　[TechNews](https://technews.tw/)

---

## 關於金價的資料來源

原本指定的來源是 truney.com，但該站有 Cloudflare 人機驗證，連真實 Chrome 都會停在
「正在執行安全驗證」而逾時，無法用於自動更新。同樣被擋的還有 Stooq（JS proof-of-work）
與台灣銀行黃金存摺頁（JS 渲染）。

最後改用 Yahoo Finance 的 `GC=F`（COMEX 黃金近月期貨），單位為 USD／盎司。
這是連續合約，Yahoo 會自動接續換月，適合看長期趨勢；若要嚴格的單一合約價格則不適用。

## 關於行事曆

原本用 ForexFactory 的 JSON feed（`ff_calendar_thisweek.json`），但那個 feed 只有
「本週」一種 —— nextweek／lastweek／thismonth 全是 404，所以永遠只看得到本週剩下
的日子。本站 HTML 有 Cloudflare，連真實 Chrome 開 `/calendar?month=this` 都是 403，
月曆抓不到。

改用 FXStreet 行事曆頁背後的端點，可以指定任意區間：

```
https://calendar-api.fxsstatic.com/en/api/v2/eventDates/{起}/{迄}
```

每次抓本月 1 日到下個月底，涵蓋頁面要顯示的「過去 3 天 + 未來 45 天」。

上方的影響程度是**勾選式**的：每個等級一顆標籤，各自開關（不是互斥的「以上」級距），沒勾的整顆淡掉。只列資料裡真的有的等級 —— 來源只給中／高，多一顆按了沒反應的「低」很怪。

**只留 HIGH 與 MEDIUM**：LOW 一個月有七百多筆，多是次要國家的次要指標，
全放進頁面只會讓真正該注意的事件被淹掉。

換來源之後名稱寫法也變了（週期是 `(YoY)` 而不是 `y/y`、PMI 前面掛編製機構、
國別欄放國碼而不是貨幣碼），所以 `calendar_i18n.py` 多了一層 `normalize()`
把這些整理成既有規則吃得下的樣子，`COUNTRIES` 也同時認貨幣碼與國碼 ——
換來源之前累積的舊資料才不會變成空白。

兩邊對同一場事件的寫法完全不同，去重比對不到，重疊的日子會列出兩套，
所以 `drop_legacy_overlap()` 會把新來源已涵蓋日期內的舊資料清掉（更早的歷史保留）。

事件以表格呈現（時間／影響／事件／預估／前值），每天一個 `<tbody>` 讓各天欄位對齊，
並在今天「已過去」與「還沒到」的事件之間插入紅色的現在時間標示線，每 30 秒更新一次。
捲動時標題會釘在畫面上方（說明文字自動收起），表頭與日期依序釘在其下，日期捲到下一天才更換。
時鐘、今天標記、標示線位置全部在瀏覽器端計算 —— 頁面會被 CDN 快取，寫死的話隔天就會標錯。

中文化不使用翻譯 API，改用 `calendar_i18n.py` 的「完整名稱對照表 + 組字規則」：
事件名稱組合性很強（`German Prelim CPI m/m` = 國別前綴 + 修飾語 + 核心指標 + 週期後綴），
拆解後查表即可。查不到的核心詞會保留英文 —— 寧可顯示英文，也不要猜錯財經名詞。
CSV 只存英文原名，改了對照表重跑 `build_static.py` 就會全部更新，不必重抓資料。

## 關於 F1 賽程

f1calendar.com 站上的表格只顯示「6 Mar 01:30」這種沒有年份、也沒標時區的字串，
不能直接用。改取 Next.js RSC payload 裡的結構化資料 —— 時間是 UTC，另有輪次、
地點與繁體中文對照表。

三個要注意的地方：

- 來源只有 **zh-HK** 版（zh-TW / zh-Hant 都會 307 轉址），用的是港式譯名。
  `TW_TERMS` 只把用詞換成台灣寫法（意大利→義大利、卡塔爾→卡達、阿布扎比→阿布達比…），
  其餘一律照來源。
- 來源的 zh-HK 對照把 `sprint` 與 `sprintQualifying` **都寫成「衝刺排位賽」**，
  兩者一個是週六的衝刺賽、一個是週五的排位賽，混在一起看不出差別。
  偵測到多個代碼對到同一個名稱時就改用自己的名稱。
- 當季新賽名（如 2026 的 Barcelona-Catalunya）來源可能還沒收錄中文，
  由 `FALLBACK_RACES` 補上。

賽程會改期，所以每次更新以最新抓到的整季資料為準，不像其他資料集是累積式的。

賽程可逐站摺疊，預設只展開「進行中或下一場」那一站（整季 20 幾站不會一次全部攤開），
點組標題可自行展開或收合，多站可同時展開。

版面依「大獎賽」分組（一個賽事週末一組），不是依日期 —— 練習賽、排位賽、正賽本來就是
同一個週末的事，照日期拆開反而看不出整體。組標題顯示輪次、賽事、地點與日期區間。

## 關於 F1 積分榜

來源 https://f1-boxbox.com/zh-tw/formula-1/2026/standings

頁面的 RSC payload 裡有結構化的 `driverStandings` / `constructorStandings`
（名次、積分、勝場、頒獎台、名次升降），但名字是英文；中文名在渲染後的 HTML
連結文字裡（`<a href=".../drivers/kimi-antonelli">基米·安托內利</a>`），
兩邊以 id 對起來就能得到「中文名 + 完整數據」。

兩個要注意的地方：

- 站上的中文名**簡繁混雜**（「阿蘭·普羅斯特」是正體、「乔治·拉塞尔」是簡體），
  用 OpenCC 的 `s2twp` 統一轉成台灣正體。沒裝 opencc 時原樣保留。
- 來源對「0 勝／0 頒獎台」的車手**直接省略該欄位**（23 位裡有 15 位），
  沒有就是 0，不能當成缺值。

同一個頁面還有 `driverStandingsTimeSeries` / `constructorStandingsTimeSeries`，
是每個人在各站結束後的**累積積分**，拿來畫冠軍積分走勢圖（2026 賽季 408 筆、12 站）。

積分榜與走勢每站之後都會變，舊快照沒有保留意義，一律以最新抓到的為準。

積分走勢圖與積分榜的配色取自來源網站的車隊代表色（頁面在車隊連結前放一個帶背景色的
小色塊）。車手沿用所屬車隊的顏色 —— 來源自己的圖例也是這樣 —— 因此同隊兩位車手會同色，
第二位改用虛線區分。積分榜的名稱前也放同一個顏色的細長條，兩邊對得起來。

F1 分頁的層次是：`賽程` 與 `積分` 兩個子分頁，`積分` 底下再分 `車手` / `車隊`
兩個孫分頁，各自是「走勢圖 + 積分榜」。走勢圖是嵌在分頁裡的圖表（不自成一個主分頁），
在 `build_static.py` 的 `EXTRA_CHARTS` 定義，並沿用同一套收合式圖例與延後繪製邏輯 ——
圖表在隱藏的分頁裡量不到寬度，一定要顯示的當下才畫。

## 關於 SpaceX 發射排程

https://www.spacex.com/launches 是純前端渲染的空殼（HTML 只有 3KB），
資料來自官網自己呼叫的 API：

- `content.spacex.com/api/spacex-website/launches-page-tiles` — 整份清單（含歷史），
  2006 年至今 720 筆
- `sxcontent9668.azureedge.us/cms-assets/future_missions.json` — 即將發射任務的
  精確時間（epoch 秒），以 `correlationId` 對應

三個要注意的地方：

- **官網一次只公布一場即將發射的任務**，而且那一筆的 `launchDate` 是 null，
  精確時間得去 `future_missions.json` 取。所以這張表實際上是
  「一場即將發射 + 近期發射紀錄」，不是完整的未來排程。
- `launchDate` / `launchTime` 是分開的兩個欄位，而且**沒有標時區**。
  硬猜會出錯，因此一律當成 UTC 存、由頁面統一換算顯示。
- 任務名稱大小寫不一致（`Starlink Mission` / `STARLINK MISSION` / `starlink mission`
  都有），中文化時會先正規化；`IM-2` 這類全大寫的專有名詞則保留原樣。

720 筆裡有 421 筆是星鏈，全部混在一起會蓋掉其他任務，所以篩選提供「星鏈以外」。
版面依月份分組並可摺疊，預設展開本月。

**進行中的任務**（如仍在軌的 Crew-12）獨立成一區置頂，比照官網的 Ongoing Missions，
並顯示來源提供的預計返回時間。這一區不受顯示窗限制 —— 那是「現在的狀態」而不是歷史，
Crew-12 是 2026-02 發射，照日期會被 90 天的窗濾掉。

## 關於新聞的資料來源

原本還指定了第六個來源「公開法說會」（alphamemo.ai/free-transcripts）。該頁在真實
Chrome 中同樣是空的 —— 內容區只有標題與一行說明，沒有任何逐字稿連結，也沒有可用的
XHR，判斷需登入才看得到清單，因此沒有納入。

DIGITIMES 只公開文章的前導段落，所以內文較短；點「看原文 ↗」可到原站閱讀全文。
非凡新聞有部分是影音報導，這類沒有可抽取的內文。

## 關於個股的即時查詢

公開資訊觀測站（MOPS）自己的 API 沒有 `Access-Control-Allow-Origin` 標頭，
瀏覽器不能直接呼叫，靜態頁面又沒有後端可以代打，所以「即時」只做得到一半：

| 子分頁 | 怎麼來的 |
|--------|---------|
| 查詢 | **即時**（走勢圖是單指拖曳往回看、雙指縮放、輕點顯示當日收盤，再點一次收起）。`www.twse.com.tw/rwd/` 這組端點帶 `Access-Control-Allow-Origin: *`，頁面上的 JS 當場呼叫 —— 股號建議、逐月成交、本益比／殖利率／股價淨值比都是按下去才去要的 |
| 營收 / 重訊 / 財報 | 排程更新。證交所開放資料（`openapi.twse.com.tw`）沒有 CORS，只能由 GitHub Actions 抓下來存成 `docs/stock/*.json`，進子分頁時才載 |

三份 JSON 加起來六百多 KB，所以不內嵌在 `index.html` 裡，跟新聞內文一樣按需下載。

查過某一檔之後（例如 2330），營收／重訊／財報就只列那一檔 —— 清單上方會出現
「只看 2330　台積電 ✕」，按 ✕ 或查另一檔就換掉。鎖定的公司在某份資料裡沒有東西時
（例如最近沒發重大訊息），會直接說明是哪一種空，而不是給一個看起來像壞掉的空清單。

## 新聞重點是怎麼挑的

兩百多則新聞平鋪著看很累，所以第一個子分頁是整理過的短清單（`news_digest.py`）：

1. **合併**：不同媒體報導同一件事的算一則，比對標題的字元 2-gram 相似度。跨來源
   門檻 0.22（不同媒體用字差很多），同來源要 0.9 —— 同一家的兩則幾乎不會是同一件事，
   但例行稿格式一模一樣（「胡連8月營收月減0.1%」對「立積8月營收月增0.7%」），
   鬆門檻會把它們錯併成一則。
2. **評分**：命中關注主題加分（半導體／AI 4 分、台股與總體經濟 3 分、公司營運與
   能源太空 2 分），多一家媒體報導 +4，越新越加分；個股營收流水帳 −5、盤中盤後
   例行稿 −3、公司自己發的公告 −6。
3. **摘要**：取內文第一段的前 90 字；跟標題講一樣的話就不重複顯示。

關注主題寫在 `news_digest.py` 的 `TOPICS`，想改看什麼直接改那份清單即可。
沒有用語言模型 —— 規則看得懂也改得動，而且不必把金鑰放進排程；代價是摘要
只是原文開頭，不是真的重寫。
