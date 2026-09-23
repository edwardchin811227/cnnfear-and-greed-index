from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

import pandas as pd
import requests


# CNN Business — Fear & Greed Index 歷史資料端點。
# 起始日期可任意指定；實測 CNN 只回溯約 6 年，更早已回 500。
API_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start}"
REPO = Path(__file__).resolve().parents[1]
DATA_FILE = REPO / "data" / "fng.csv"
JSON_FILE = REPO / "docs" / "fng_data.json"

CSV_COLUMNS = ["date", "timestamp", "value", "classification"]

# 一個美股交易年 ≈ 252 個交易日
WINDOW = 252
Z_LEVELS = (1, 2, 3)
HISTORY_DAYS = 2200          # 抓取回溯天數（略多於 6 年，取滿 CNN 全部歷史）
STATS_YEARS = 5              # KPI / 校準表使用的觀察年限
LOOKBACKS = [("1 年", 252), ("2 年", 504), ("3 年", 756), ("5 年", 1260)]

RATING_ZH = {
    "extreme fear": "極度恐懼",
    "fear": "恐懼",
    "neutral": "中性",
    "greed": "貪婪",
    "extreme greed": "極度貪婪",
}

# CNN 對 urllib / 預設 UA 會回 418，必須帶完整瀏覽器標頭。
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
    "Origin": "https://edition.cnn.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _fetch_payload(session: requests.Session, start_date: str) -> dict:
    response = session.get(API_URL.format(start=start_date), timeout=45)
    response.raise_for_status()
    # CNN 回傳帶 UTF-8 BOM
    return json.loads(response.content.decode("utf-8-sig"))


def _fetch_api_data() -> tuple[pd.DataFrame, dict]:
    """回傳 (日度定稿序列, 即時讀數)。

    CNN 的日度資料點時間戳固定落在 00:00 UTC（美東收盤後 3~5 小時），
    這是已定稿的值；序列末端另外掛了一個「即時尾巴點」，時間戳等於請求時刻，
    數值隨 VIX 盤中浮動。這裡只把 00:00 UTC 的定稿點寫進 CSV，
    尾巴點僅用來產生頁面上的即時讀數。
    """
    session = _session()
    start = (datetime.now(timezone.utc).date() - timedelta(days=HISTORY_DAYS)).isoformat()
    payload = _fetch_payload(session, start)

    rows = payload.get("fear_and_greed_historical", {}).get("data", [])
    if not rows:
        raise RuntimeError("CNN returned empty historical data")

    parsed: list[dict[str, object]] = []
    for row in rows:
        ts_raw = row.get("x")
        value_raw = row.get("y")
        if ts_raw is None or value_raw is None:
            continue

        ts = int(ts_raw // 1000)
        stamp = datetime.fromtimestamp(ts, tz=timezone.utc)
        if not (stamp.hour == 0 and stamp.minute < 10):
            continue                                   # 丟掉即時尾巴點

        value = pd.to_numeric(value_raw, errors="coerce")
        if pd.isna(value):
            continue

        parsed.append(
            {
                "date": stamp.date().isoformat(),
                "timestamp": ts,
                "value": float(value),
                "classification": str(row.get("rating", "")).strip(),
            }
        )

    if not parsed:
        raise RuntimeError("No settled daily rows parsed from CNN")

    df = pd.DataFrame(parsed)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["date", "timestamp", "value"]).copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df = df.sort_values(["date", "timestamp"]).drop_duplicates(subset=["date"], keep="last")

    live = payload.get("fear_and_greed", {}) or {}
    return df[CSV_COLUMNS].reset_index(drop=True), live


def _load_existing_csv() -> pd.DataFrame:
    if not DATA_FILE.exists():
        return pd.DataFrame(columns=CSV_COLUMNS)

    raw = pd.read_csv(DATA_FILE)
    if raw.empty:
        return pd.DataFrame(columns=CSV_COLUMNS)

    df = raw.copy()
    if "date" not in df.columns:
        if "timestamp" in df.columns:
            ts_dt = pd.to_datetime(pd.to_numeric(df["timestamp"], errors="coerce"), unit="s", utc=True)
            df["date"] = ts_dt.dt.strftime("%Y-%m-%d")
        else:
            raise ValueError("data/fng.csv must have either date or timestamp column")
    if "timestamp" not in df.columns:
        dt_col = pd.to_datetime(df["date"], errors="coerce", utc=True)
        df["timestamp"] = (dt_col.view("int64") // 1_000_000_000).astype("Int64")
    if "value" not in df.columns:
        raise ValueError("data/fng.csv missing value column")
    if "classification" not in df.columns:
        df["classification"] = ""

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["classification"] = df["classification"].fillna("").astype(str)
    df = df.dropna(subset=["date", "timestamp", "value"]).copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df = df.sort_values(["date", "timestamp"]).drop_duplicates(subset=["date"], keep="last")
    return df[CSV_COLUMNS].reset_index(drop=True)


def _merge_with_backfill(existing: pd.DataFrame, fresh: pd.DataFrame, backfill_days: int) -> pd.DataFrame:
    """最近 N 天以 API 為準（CNN 會修訂），更早的保留本機既有的 —— 這樣
    本專案的 archive 會逐年比 CNN 本身（僅 6 年）更完整。"""
    if existing.empty:
        return fresh.copy()
    if fresh.empty:
        return existing.copy()

    fresh_dates = pd.to_datetime(fresh["date"], errors="coerce")
    cutoff_date = fresh_dates.max().date() - timedelta(days=max(backfill_days, 0))

    existing_dates = pd.to_datetime(existing["date"], errors="coerce").dt.date
    fresh_dates_only = fresh_dates.dt.date

    existing_old = existing.loc[existing_dates < cutoff_date].copy()
    fresh_recent = fresh.loc[fresh_dates_only >= cutoff_date].copy()
    fresh_old_fill = fresh.loc[
        (fresh_dates_only < cutoff_date) & (~fresh["date"].isin(existing_old["date"]))
    ].copy()

    merged = pd.concat([existing_old, fresh_old_fill, fresh_recent], ignore_index=True)
    merged["date"] = pd.to_datetime(merged["date"], errors="coerce")
    merged["timestamp"] = pd.to_numeric(merged["timestamp"], errors="coerce")
    merged["value"] = pd.to_numeric(merged["value"], errors="coerce")
    merged["classification"] = merged["classification"].fillna("").astype(str)
    merged = merged.dropna(subset=["date", "timestamp", "value"])
    merged["date"] = merged["date"].dt.strftime("%Y-%m-%d")
    merged = merged.sort_values(["date", "timestamp"]).drop_duplicates(subset=["date"], keep="last")
    return merged[CSV_COLUMNS].reset_index(drop=True)


def _value_or_none(value: object, *, digits: int = 6) -> float | int | None:
    if value is None or pd.isna(value):
        return None
    num = float(value)
    if not math.isfinite(num):
        return None
    rounded = round(num, digits)
    return int(rounded) if float(rounded).is_integer() else rounded


def _build_enriched_rows(df: pd.DataFrame) -> pd.DataFrame:
    calc = df.copy()
    calc["value"] = pd.to_numeric(calc["value"], errors="coerce")
    calc = calc.sort_values("date").reset_index(drop=True)

    calc["mean"] = calc["value"].rolling(window=WINDOW, min_periods=WINDOW).mean()
    calc["std"] = calc["value"].rolling(window=WINDOW, min_periods=WINDOW).std(ddof=1)
    for n in Z_LEVELS:
        calc[f"upper{n}"] = calc["mean"] + n * calc["std"]
        calc[f"lower{n}"] = calc["mean"] - n * calc["std"]
    return calc


def _build_json_rows(calc: pd.DataFrame) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for _, row in calc.iterrows():
        item: dict[str, object] = {
            "date": str(row["date"]),
            "value": _value_or_none(row["value"], digits=4),
            "classification": str(row.get("classification", "")),
            "mean": _value_or_none(row["mean"], digits=6),
            "std": _value_or_none(row["std"], digits=6),
        }
        for n in Z_LEVELS:
            item[f"upper{n}"] = _value_or_none(row[f"upper{n}"], digits=6)
            item[f"lower{n}"] = _value_or_none(row[f"lower{n}"], digits=6)
        out.append(item)
    return out


def _build_stats(calc: pd.DataFrame, live: dict) -> dict[str, object]:
    # 約 5 個交易年（5 × 252）
    recent = calc.tail(STATS_YEARS * 252)
    vals = pd.to_numeric(recent["value"], errors="coerce").dropna()

    live_score = live.get("score")
    cur = float(live_score) if live_score is not None else float(vals.iloc[-1])
    mean, sd = float(vals.mean()), float(vals.std(ddof=1))
    z_full = (cur - mean) / sd if sd else 0.0

    lookbacks = []
    for label, win in LOOKBACKS:
        w = vals.tail(win)
        m, s = float(w.mean()), float(w.std(ddof=1))
        lookbacks.append(
            {
                "label": label,
                "n": int(len(w)),
                "mean": round(m, 2),
                "sd": round(s, 2),
                "lower1": round(m - s, 1),
                "upper1": round(m + s, 1),
                "lower2": round(m - 2 * s, 1),
                "upper2": round(m + 2 * s, 1),
                "z": round((cur - m) / s, 2) if s else 0.0,
                "percentile": round(100.0 * float((w < cur).mean()), 1),
            }
        )

    tail = calc.iloc[-1]
    return {
        "n": int(len(vals)),
        "first": str(recent["date"].iloc[0]),
        "last": str(recent["date"].iloc[-1]),
        "mean": round(mean, 2),
        "sd": round(sd, 2),
        "median": round(float(vals.median()), 1),
        "min": round(float(vals.min()), 1),
        "max": round(float(vals.max()), 1),
        "z": round(z_full, 2),
        "percentile": round(100.0 * float((vals < cur).mean()), 1),
        "settled_value": _value_or_none(tail["value"], digits=2),
        "settled_date": str(tail["date"]),
        "settled_classification": str(tail["classification"]),
        "settled_z": _value_or_none(
            (float(tail["value"]) - float(tail["mean"])) / float(tail["std"])
            if pd.notna(tail["mean"]) and float(tail["std"]) else None,
            digits=2,
        ),
        "lookbacks": lookbacks,
    }


def _build_live(live: dict, stats: dict) -> dict[str, object]:
    score = live.get("score")
    rating = str(live.get("rating", "")).strip()
    if score is None:
        score = stats["settled_value"]
        rating = stats["settled_classification"]
    block = {
        "value": _value_or_none(score, digits=2),
        "classification": rating,
        "classification_zh": RATING_ZH.get(rating, rating),
        # 刻意用「已定稿的資料日期」而不是 CNN 回傳的請求時間戳 ——
        # 後者每次呼叫都不同，會讓 JSON 每天都產生無意義的變動。
        "as_of": stats["settled_date"],
    }
    for src, dst in (
        ("previous_close", "previous_close"),
        ("previous_1_week", "previous_1_week"),
        ("previous_1_month", "previous_1_month"),
        ("previous_1_year", "previous_1_year"),
    ):
        block[dst] = _value_or_none(live.get(src), digits=2)
    return block


def _to_csv_text(df: pd.DataFrame) -> str:
    out = df.copy()
    out = out[CSV_COLUMNS].sort_values("date").reset_index(drop=True)
    out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce").astype("Int64")
    out["value"] = pd.to_numeric(out["value"], errors="coerce").round(6)
    buffer = StringIO()
    out.to_csv(buffer, index=False, lineterminator="\n")
    return buffer.getvalue()


def _to_json_text(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _write_if_changed(path: Path, content: str) -> bool:
    """只在內容變動時寫檔，並固定用 LF —— 讓 Windows 與 Docker(Linux) 兩邊
    寫出的檔案逐位元一致，不會因為換行符互相觸發無意義的 commit。"""
    existing = None
    if path.exists():
        with open(path, "r", encoding="utf-8", newline="") as fh:
            existing = fh.read()
    if existing == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and process CNN Fear & Greed Index data")
    parser.add_argument("--backfill-days", type=int, default=10,
                        help="Reconcile last N days with fresh API data")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.backfill_days < 0:
        raise ValueError("--backfill-days must be >= 0")

    existing = _load_existing_csv()
    fresh, live_raw = _fetch_api_data()
    merged = _merge_with_backfill(existing, fresh, args.backfill_days)

    if merged.empty:
        raise RuntimeError("Merged dataset is empty after processing")

    calc = _build_enriched_rows(merged)
    stats = _build_stats(calc, live_raw)
    live = _build_live(live_raw, stats)
    target_date = str(merged["date"].iloc[-1])

    lookbacks = stats.pop("lookbacks")
    payload = {
        "updated": target_date,
        "source": "CNN Business — Fear & Greed Index",
        "window": WINDOW,
        "z_levels": list(Z_LEVELS),
        "live": live,
        "stats": stats,
        "lookbacks": lookbacks,
        "rows": _build_json_rows(calc),
    }

    csv_changed = _write_if_changed(DATA_FILE, _to_csv_text(merged))
    json_changed = _write_if_changed(JSON_FILE, _to_json_text(payload))

    print(f"target_date={target_date}")
    print(
        f"rows: existing={len(existing)} fresh={len(fresh)} merged={len(merged)} "
        f"| backfill_days={args.backfill_days}"
    )
    print(f"changed: csv={csv_changed} json={json_changed}")
    print(
        f"live: value={live['value']} ({live['classification']}) "
        f"z={stats['z']} percentile={stats['percentile']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
