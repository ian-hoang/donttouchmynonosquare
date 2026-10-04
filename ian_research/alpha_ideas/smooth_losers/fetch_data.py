"""Fetch the raw data for Idea 4 (smooth losers) from the Massive API.

Writes (all under the gitignored data/cache/massive_grouped/):
  grouped_YYYY.parquet  one row per (date, ticker): close/volume/vwap from adjusted=true bars and close_raw from
                        adjusted=false bars (the raw close is used only for the $5 price screen).
  tickers_cs.parquet    Massive reference tickers of type CS, active=true and active=false.

Run:  uv run python alpha_ideas/smooth_losers/fetch_data.py
Re-running skips years that are already on disk. The API key comes from massive/eightk.load_api_key (read-only).
"""
from __future__ import annotations

import datetime as dt
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "massive"))
from eightk import load_api_key  # noqa: E402  (read-only import of the key loader)

BASE = "https://api.massive.com"
CACHE = ROOT / "data" / "cache" / "massive_grouped"
START, END = dt.date(2005, 1, 1), dt.date(2026, 9, 30)
THREADS = 8

_local = threading.local()


def _session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {load_api_key()}"
        _local.s = s
    return s


def get_json(url: str, params: dict | None = None, tries: int = 8) -> dict:
    """GET with exponential backoff on 429 / 5xx / network errors."""
    wait = 1.0
    for attempt in range(tries):
        try:
            r = _session().get(url, params=params, timeout=90)
            if r.status_code == 200:
                return r.json()
            if r.status_code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {r.status_code} for {url}: {r.text[:200]}")
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(wait)
        wait = min(wait * 2, 60)
    raise RuntimeError(f"giving up on {url} after {tries} tries")


def fetch_day(day: dt.date) -> pd.DataFrame | None:
    url = f"{BASE}/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}"
    adj = get_json(url, {"adjusted": "true"}).get("results") or []
    if not adj:
        return None  # weekend / holiday / no data
    raw = get_json(url, {"adjusted": "false"}).get("results") or []
    a = pd.DataFrame(adj)
    a = a.rename(columns={"T": "ticker", "c": "close", "v": "volume", "vw": "vwap"})
    a = a[["ticker", "close", "volume", "vwap"]].drop_duplicates("ticker")
    if raw:
        r = pd.DataFrame(raw).rename(columns={"T": "ticker", "c": "close_raw"})[["ticker", "close_raw"]]
        a = a.merge(r.drop_duplicates("ticker"), on="ticker", how="left")
    else:
        a["close_raw"] = float("nan")
    a.insert(0, "date", pd.Timestamp(day))
    return a


def fetch_year(year: int) -> None:
    out = CACHE / f"grouped_{year}.parquet"
    if out.exists():
        print(f"{year}: already on disk, skipping")
        return
    days = [d for d in pd.date_range(max(START, dt.date(year, 1, 1)), min(END, dt.date(year, 12, 31))).date
            if d.weekday() < 5]
    t0 = time.time()
    with ThreadPoolExecutor(THREADS) as ex:
        frames = [f for f in ex.map(fetch_day, days) if f is not None]
    df = pd.concat(frames, ignore_index=True)
    df["ticker"] = df["ticker"].astype("string")
    df = df.sort_values(["date", "ticker"]).reset_index(drop=True)
    tmp = out.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(out)
    print(f"{year}: {len(frames)} trading days, {len(df):,} rows, {time.time() - t0:.0f}s")


def fetch_tickers() -> None:
    out = CACHE / "tickers_cs.parquet"
    if out.exists():
        print("tickers_cs.parquet already on disk, skipping")
        return
    rows = []
    for active in ("true", "false"):
        url, params, pages = f"{BASE}/v3/reference/tickers", {"market": "stocks", "type": "CS", "active": active,
                                                               "limit": 1000}, 0
        while url:
            j = get_json(url, params)
            rows += j.get("results") or []
            url, params, pages = j.get("next_url"), None, pages + 1
        print(f"tickers active={active}: {pages} pages")
    df = pd.DataFrame(rows)
    keep = [c for c in ["ticker", "name", "active", "primary_exchange", "type", "cik", "composite_figi",
                        "share_class_figi", "delisted_utc", "last_updated_utc"] if c in df.columns]
    df = df[keep]
    df.to_parquet(out, index=False)
    print(f"tickers: {len(df):,} rows, {df['ticker'].nunique():,} unique tickers "
          f"({int(df['active'].sum()):,} active rows)")


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    fetch_tickers()
    for year in range(START.year, END.year + 1):
        fetch_year(year)


if __name__ == "__main__":
    main()
