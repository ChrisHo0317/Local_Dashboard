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

靜態版把淺色 / 深色兩份圖表 JSON 內嵌進頁面，由前端 `Plotly.react` 切換。hover、點 legend 隱藏型號、框選縮放等 Plotly 原生互動都保留。

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

`export_from_sqlite.py` 是初始化用的一次性工具，從本機 AI Cowork 的 `cowork.db` 匯出資料；一般使用不會用到。

---

## 檔案說明

| 檔案 | 用途 |
|------|------|
| `dram_data.py` | 讀寫 `data/dram_prices.csv`，以 `(item, price_date)` 去重 |
| `chart.py` | `build_figure(df, dark)` — 唯一的圖表定義來源 |
| `scraper.py` | TrendForce DRAM Spot Price 爬蟲 |
| `update_data.py` | 爬蟲 → 合併 CSV → 重建靜態頁 |
| `build_static.py` | 產生 `docs/index.html` |
| `app.py` | 本地 Dash 版 |
| `export_from_sqlite.py` | 自本機 SQLite 匯出初始 CSV |

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

資料來源：[TrendForce 集邦科技](https://www.trendforce.com.tw/price/dram/dram_spot)
