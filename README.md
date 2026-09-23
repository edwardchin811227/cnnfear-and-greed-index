# CNN Fear & Greed Index · 252MA ±σ

每天自動抓取 CNN Business 的 Fear & Greed Index，計算 252 個交易日（≈1 年）移動平均與 ±1/±2/±3 標準差區間，輸出成 GitHub Pages 靜態圖表。

與 [`cryptofear-and-greed-index`](../cryptofear-and-greed-index) 同一套架構，只把資料源換成 CNN（美股）。

## 專案結構

```text
cnnfear-and-greed-index/
├── .github/
│   └── workflows/
│       └── update.yml          # GitHub Actions：雲端每日自動更新
├── data/
│   └── fng.csv                 # 逐日累積存檔（date,timestamp,value,classification）
├── docs/
│   ├── index.html              # GitHub Pages 頁面
│   └── fng_data.json           # 頁面資料（含 252MA 與 ±σ 帶）
├── scripts/
│   ├── fetch_and_process.py
│   ├── publish_data.ps1
│   ├── run_daily.ps1
│   └── install_daily_task.ps1
├── README.md
└── requirements.txt
```

## 安裝

```powershell
python -m pip install -r requirements.txt
```

## 手動更新資料

```powershell
python scripts/fetch_and_process.py --backfill-days 10
```

會更新：

- `data/fng.csv`
- `docs/fng_data.json`

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

另外，API 序列末端會掛一個「**即時尾巴點**」，時間戳等於你請求的當下，數值隨 VIX 盤中浮動。本專案只把 00:00 UTC 的定稿點寫進 `data/fng.csv`，尾巴點僅用於頁面上的即時讀數。

**結論：要拿到當日已定稿的值，最穩是 00:00 UTC 之後。**

| 時區 | 更新時間 |
| --- | --- |
| UTC | 00:10 |
| 香港 / 台北 / 上海 (UTC+8) | **08:10** |
| 美東 (夏令 EDT) | 20:10 前一日 |
| 美東 (冬令 EST) | 19:10 前一日 |

> 註：週末與美股假期沒有資料點。資料點的時間戳日期對應的是「前一個美股交易日」的收盤值。

---

## 自動更新方式 A：GitHub Actions（雲端，推薦）

`.github/workflows/update.yml` 已設定好，推到 GitHub 後就會自動運作，**不需要電腦開機**。

排程：

| Cron (UTC) | 香港時間 | 用途 |
| --- | --- | --- |
| `10 0 * * *` | 08:10 | 主排程，CNN 定稿後 10 分鐘 |
| `40 0 * * *` | 08:40 | 保險重試 |
| `20 21 * * 1-5` | 05:20（隔日） | 美東收盤後先抓一次 |

也可以在 GitHub 網頁上 `Actions → 每日更新 CNN Fear & Greed → Run workflow` 手動觸發。

> ⚠️ GitHub 的 `schedule` 在尖峰時段可能延遲數分鐘至數十分鐘，這是平台限制，無法保證準點。若需要準時，改用下面的方式 B 或兩者並存（但**不要同時開**，會造成 push 衝突）。

---

## 自動更新方式 B：本機排程（比照 usmarket / cryptofear）

### 1) 一次執行更新 + 發布

```powershell
powershell scripts/run_daily.ps1
```

若要直接推送：

```powershell
powershell scripts/run_daily.ps1 -Push
```

### 2) 安裝每日排程（08:10）

```powershell
powershell scripts/install_daily_task.ps1 -RunAt 08:10
```

任務會執行：

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_daily.ps1 -Push -BackfillDays 10
```

移除排程：

```powershell
Unregister-ScheduledTask -TaskName "cnnfng-auto-sync" -Confirm:$false
```

> 若同時啟用 GitHub Actions，請擇一：要嘛停用 Action，要嘛 `Unregister-ScheduledTask`。

---

## GitHub Pages

在 GitHub repository 設定：

- `Settings -> Pages`
- Source: `Deploy from a branch`
- Branch: `main`
- Folder: `/docs`

部署網址：

```text
https://<username>.github.io/cnnfear-and-greed-index/
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

1. **CNN 只回溯約 6 年**（實測起點 2020-09-01），更早的起始日會回 HTTP 500。本專案靠 `data/fng.csv` 逐日累積突破此限制。
2. **必須帶完整瀏覽器標頭**，否則 CNN 會回 HTTP 418。
3. CNN 回傳的 JSON **帶 UTF-8 BOM**，需以 `utf-8-sig` 解碼。
4. 指數本身有界（0–100），Z-Score 不會像股價那樣跑到 ±4σ 以上，頁面上的 Z 圖固定顯示 ±3.5σ。
5. 滾動窗口有滞后：252 日均值要一年才完全更新，急跌初期 Z 的反應會慢半拍。

---

## 資料來源

CNN Business — Fear & Greed Index
`https://production.dataviz.cnn.io/index/fearandgreed/graphdata/<YYYY-MM-DD>`

資料版權屬 CNN Business 所有。本專案僅作個人研究與視覺化用途，不構成任何投資建議。
