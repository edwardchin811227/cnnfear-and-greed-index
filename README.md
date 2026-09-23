# CNN Fear & Greed Index · 252MA ±σ

每天自動抓取 CNN Business 的 Fear & Greed Index，計算 252 個交易日（≈1 年）移動平均與 ±1/±2/±3 標準差區間，輸出成 GitHub Pages 靜態圖表。

與 [`cryptofear-and-greed-index`](https://github.com/edwardchin811227/cryptofear-and-greed-index)、[`usmarket`](https://github.com/edwardchin811227/usmarket)、[`hsi-dashboard`](https://github.com/edwardchin811227/hsi-dashboard) 同一套架構，只把資料源換成 CNN（美股）。

**更新方式：NAS（UGREEN DH4300PLUS，`192.168.31.237`）上的 Docker 容器 `cnnfng` 每日自動更新並推回本 repo，不需要本機開機。**

---

## 專案結構

```text
cnnfear-and-greed-index/
├── data/
│   └── fng.csv                 # 逐日累積存檔（date,timestamp,value,classification）
├── docs/
│   ├── index.html              # GitHub Pages 頁面
│   └── fng_data.json           # 頁面資料（含 252MA 與 ±σ 帶）
├── scripts/
│   ├── fetch_and_process.py    # 抓取 + 存檔 + 產生 JSON
│   ├── publish_data.ps1        # 本機用：git add/commit/push
│   ├── run_daily.ps1           # 本機用：更新 + 發布
│   └── install_daily_task.ps1  # 本機用：安裝 Windows 每日排程
├── README.md
└── requirements.txt
```

Docker 部署檔不在本 repo，放在 NAS 的 `/volume2/yoliaccessories/cnnfng-docker/`（見下方）。

---

## 安裝與手動更新

```powershell
python -m pip install -r requirements.txt
python scripts/fetch_and_process.py --backfill-days 10
```

會更新 `data/fng.csv` 與 `docs/fng_data.json`。

`--backfill-days 10` 表示最近 10 天的數值以 CNN 回傳為準（CNN 會修訂），更早的保留本機既有資料 —— 這樣本專案的存檔會逐年比 CNN 本身（只回溯約 6 年）更完整。

---

## 資料更新時間（實測）

**CNN 的日度資料點時間戳固定落在 `00:00 UTC`。**

以 2026-09 的資料實測，近 80 個資料點中有 79 個時間戳正好是 00:00 UTC，換算美東時間為 **19:00～20:00 ET**（收盤後 3～5 小時，隨夏令時間變動）。

各成分指標的結算時刻（美東 ET）：

| 成分指標 | 結算時刻 |
| --- | --- |
| 避險需求 Safe Haven Demand | 15:59 |
| S&P 500 動量 Market Momentum | 16:36 |
| Put/Call 期權比率 | 16:42 |
| 垃圾債需求 Junk Bond Demand | 20:00 |
| 股價強度 / 廣度 Stock Price Strength / Breadth | 20:59 |

另外，API 序列末端會掛一個「**即時尾巴點**」，時間戳等於請求當下，數值隨 VIX 盤中浮動。本專案只把 00:00 UTC 的定稿點寫進 `data/fng.csv`，尾巴點僅用於頁面上的即時讀數。

**結論：要拿到當日已定稿的值，最穩是 00:00 UTC 之後。**

| 時區 | 更新時間 |
| --- | --- |
| UTC | 00:10 |
| 香港 / 台北 / 上海 (UTC+8) | **08:10** |
| 美東（夏令 EDT） | 20:10 前一日 |
| 美東（冬令 EST） | 19:10 前一日 |

> 註：週末與美股假期沒有資料點。資料點的時間戳日期對應的是「前一個美股交易日」的收盤值。

---

## 自動更新：NAS Docker（主要方式）

容器 `cnnfng` 在啟動時 clone 本 repo 到 `/app/cnnfear-and-greed-index`，
之後由容器內 cron 每日執行 `run_update.sh`（`git pull` → 抓 CNN → `git commit` → `git push`）。

### 部署檔位置

| 檔案 | 路徑 |
| --- | --- |
| 部署目錄 | `/volume2/yoliaccessories/cnnfng-docker/` |
| 鏡像 | `cnnfng-docker-cnnfng` |
| 容器 | `cnnfng`（`restart: always`） |
| 資料卷 | `cnnfng-docker_cnnfng_data` → `/app` |
| SSH key | `/volume2/yoliaccessories/cnnfng-docker/id_rsa` → `/root/.ssh/id_rsa:ro` |

### 部署 / 更新指令

```bash
# 首次部署或改 Dockerfile／cron 後重建
ssh ugreen 'cd /volume2/yoliaccessories/cnnfng-docker && docker compose up -d --build'

# 看狀態
ssh ugreen 'docker ps --filter name=cnnfng'

# 看即時日誌
ssh ugreen 'docker logs -f --tail 100 cnnfng'

# 看更新紀錄檔
ssh ugreen 'docker exec cnnfng tail -40 /app/logs/daily_update.log'

# 手動立刻跑一次（測試用）
ssh ugreen 'docker exec cnnfng /bin/bash /app/run_update.sh'
```

### 容器內 cron

```cron
PATH=/usr/local/bin:/usr/bin:/bin
10 8 * * * root /bin/bash /app/run_update.sh > /proc/1/fd/1 2>/proc/1/fd/2
40 8 * * * root /bin/bash /app/run_update.sh > /proc/1/fd/1 2>/proc/1/fd/2
```

`TZ=Asia/Shanghai`，所以 08:10 = 00:10 UTC（CNN 定稿後 10 分鐘）。08:40 那次是保險重試，資料沒變就不會產生 commit。

### 網路

容器透過 NAS 上的 mihomo 代理連外：

```yaml
environment:
  - HTTPS_PROXY=http://192.168.31.237:7890
  - HTTP_PROXY=http://192.168.31.237:7890
  - NO_PROXY=localhost,127.0.0.1,.local
```

實測 CNN API 直連與走代理皆可（HTTP 200），代理主要是為了 GitHub。

---

## 備選方式

### A) 本機 Windows 排程（比照 usmarket / cryptofear）

```powershell
powershell scripts/install_daily_task.ps1 -RunAt 08:10   # 安裝
powershell scripts/run_daily.ps1 -Push                   # 手動跑一次並推送
Unregister-ScheduledTask -TaskName "cnnfng-auto-sync" -Confirm:$false   # 移除
```

### B) GitHub Actions（目前未啟用）

本 repo 原本附 `.github/workflows/update.yml`，但**已移除** —— 它與 NAS 容器都是寫入方，且都排在 08:10，會互相 push 衝突。

若日後不再使用 NAS 容器，可自行加回：

```yaml
name: 每日更新 CNN Fear & Greed
on:
  schedule:
    - cron: "10 0 * * *"
    - cron: "40 0 * * *"
  workflow_dispatch:
permissions:
  contents: write
jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: python -m pip install -r requirements.txt
      - run: python scripts/fetch_and_process.py --backfill-days 10
      - run: |
          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/fng.csv docs/fng_data.json
          git diff --cached --quiet && exit 0
          git commit -m "data: update fng $(date -u +'%Y-%m-%d %H:%M') UTC"
          git push
```

> ⚠️ **只能選一個寫入方**：NAS 容器或 GitHub Actions，不要同時開。

---

## GitHub Pages

- `Settings -> Pages`
- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

部署網址：

```text
https://edwardchin811227.github.io/cnnfear-and-greed-index/
```

---

## 圖表怎麼讀

| 元素 | 含義 |
| --- | --- |
| 黑線 | CNN Fear & Greed Index 每日值（0 = 極度恐懼，100 = 極度貪婪） |
| 藍虛線 | 252 個交易日移動平均，情緒的「基準線」 |
| 綠色帶 | 均值 +1σ / +2σ / +3σ |
| 紅色帶 | 均值 −1σ / −2σ / −3σ |
| 下圖柱狀 | Z-Score ＝（今日值 − 252日均值）÷ 252日標準差 |

**關鍵解讀陷阱**：指數 35 分、標籤寫「恐懼」，**不代表統計上極端**。要同時看 Z-Score —— Z 只有 −0.5σ 的話那只是溫和偏離，離 −2σ 的統計極端還很遠。這是用標準差而不是用絕對分數去看的價值所在。

---

## 已知限制

1. **CNN 只回溯約 6 年**（實測起點 ≈ 2020-09），更早的起始日會回 HTTP 500。本專案靠 `data/fng.csv` 逐日累積突破此限制。
2. **必須帶完整瀏覽器標頭**（`User-Agent`、`Referer`、`Origin` 等），否則 CNN 會回 **HTTP 418**；用 `urllib` 預設 UA 一定失敗。
3. CNN 回傳的 JSON **帶 UTF-8 BOM**，需以 `utf-8-sig` 解碼。
4. 資料檔一律以 **LF** 寫出（`newline=""`），避免 Windows 與 Docker 兩邊因 CRLF 互相產生無意義 commit。
5. 指數本身有界（0–100），Z-Score 不會像股價那樣跑到 ±4σ 以上，頁面 Z 圖固定顯示 ±3.5σ。
6. 滾動窗口有滞后：252 日均值要一年才完全更新，急跌初期 Z 的反應會慢半拍。

---

## 資料來源

CNN Business — Fear & Greed Index
`https://production.dataviz.cnn.io/index/fearandgreed/graphdata/<YYYY-MM-DD>`

資料版權屬 CNN Business 所有。本專案僅作個人研究與視覺化用途，不構成任何投資建議。
