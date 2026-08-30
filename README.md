# Local_Dashboard — DRAM 現貨報價走勢

TrendForce DRAM 現貨報價的歷史走勢圖，資料每日自動更新。

**線上瀏覽：** https://chrisho0317.github.io/Local_Dashboard/

---

## 為什麼有兩個版本

GitHub Pages 只能託管靜態檔案，無法執行 Dash 的伺服器端 callback，因此本專案提供兩種呈現方式，兩者共用同一份資料與同一個 `chart.build_figure()`：

| 版本 | 進入點 | 說明 |
|------|--------|------|
| 本地 Dash | `app.py` | 在自己電腦跑，`http://localhost:8051` |
| 靜態頁面 | `build_static.py` → `docs/index.html` | GitHub Pages 對外瀏覽 |

靜態版把淺色 / 深色兩份圖表 JSON 內嵌進頁面，由前端 `Plotly.react` 切換。hover、框選縮放等 Plotly 原生互動都保留。

## 圖表操作

- **時間軸縮圖**：圖表下方的橫向縮圖顯示完整區間，拖曳兩端可縮放，主圖同步顯示選取範圍。
- **快速區間**：左上角 `1月` / `3月` / `6月` / `全部` 按鈕。
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
圖示會顯示 DRAM 模組與上升折線，名稱為「DRAM 報價」，開啟後為獨立視窗（無瀏覽器網址列）。

---

## 檔案說明

| 檔案 | 用途 |
|------|------|
| `dram_data.py` | 讀寫 `data/dram_prices.csv`，以 `(item, price_date)` 去重 |
| `chart.py` | `build_figure(df, dark)` — 唯一的圖表定義來源 |
| `docs/` | 發佈目錄：`index.html`（產生）+ 圖示與 `manifest.webmanifest`（靜態） |
| `scraper.py` | TrendForce DRAM Spot Price 爬蟲 |
| `update_data.py` | 爬蟲 → 合併 CSV → 重建靜態頁 |
| `build_static.py` | 產生 `docs/index.html` |
| `app.py` | 本地 Dash 版 |
| `export_from_sqlite.py` | 自本機 SQLite 匯出初始 CSV |
| `make_icons.py` | 產生 `docs/` 底下的網站圖示（需 Pillow） |
| `version.py` | 版本號，顯示於頁尾與本地 Dash 標頭 |

## 資料格式

`data/dram_prices.csv`

| 欄位 | 說明 |
|------|------|
| `item` | 型號，如 `DDR5 16Gb (2Gx8) 4800/5600` |
| `price_date` | 報價日期 `YYYY-MM-DD` |
| `avg_price` | 盤平均（USD） |

---

## 自動更新

`.github/workflows/update.yml` 每日 UTC 01:00（台灣 09:00）執行 `update_data.py`，有新報價才 commit。也可在 Actions 分頁手動觸發。

> GitHub Actions 使用資料中心 IP，TrendForce 的 Cloudflare 有可能擋下請求。`update_data.py` 在抓不到資料時只印警告並正常結束，不會讓 workflow 變紅，也不會覆寫既有 CSV。若長期無法在雲端爬取，可改於本機排程執行 `update_data.py` 後推送。

## 設定（首次部署）

- **Settings → Pages** → Source: `Deploy from a branch` → `main` / `/docs`
- **Settings → Actions → General → Workflow permissions** → `Read and write permissions`

---

## 版本

目前 **v0.1.000**，顯示在頁面右下角與本地 Dash 的標題旁 —— GitHub Pages 與瀏覽器都會快取，用版本號比對才能確定手機上看到的是不是最新版。

格式 `vMAJOR.MINOR.PATCH`（PATCH 補零至三位）：修 bug 或調版面遞增 PATCH、新增功能遞增 MINOR、架構改版遞增 MAJOR。改 `version.py` 後重跑 `build_static.py` 即可。

每日自動更新報價**不算**版本變更，workflow 不會動到 `version.py`。

---

資料來源：[TrendForce 集邦科技](https://www.trendforce.com.tw/price/dram/dram_spot)
