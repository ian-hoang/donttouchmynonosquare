"""Download (once) and cache every raw input for Idea 5 — Kalshi CPI crowd vs. Cleveland Fed nowcast.

Everything lands in alpha_ideas/kalshi_cpi/raw/. A file that already exists is never re-downloaded, so a rerun
reads the frozen copy. Only public, unauthenticated GET endpoints are used (no orders, no keys).

Sources
- Kalshi public API (market data only): events, markets (live + historical), trades (live + historical).
- Cleveland Fed inflation nowcast JSON (`nowcast_month.json`).
- BLS public API v1, CPI-U SA all items (only to document that October 2025 was never published).

Python's urllib fails on this machine with an SSL certificate error, so `requests` is used.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
NOWCAST_URL = ("https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting/"
               "nowcast_month.json?sc_lang=en")
NOWCAST_FALLBACK = Path("/private/tmp/claude-501/-Users-hqdatt-Documents-GQH/"
                        "e68a08f4-a100-43a4-a0f2-28504ddb4714/scratchpad/nowcast_month.json")
BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/CUSR0000SA0"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
ET = "America/New_York"
SERIES = ["KXCPI", "KXCPICORE"]  # headline (incl. legacy CPI-* events) and core (incl. legacy CPICORE-* events)
CUTOFF = "07:55"  # crowd snapshot time on release day (ET)

# The one release whose BLS publication date differs from the market's close date: September 2025 CPI was
# scheduled for 2025-10-15 (Kalshi markets closed then) but the 2025 shutdown pushed BLS to 2025-10-24 (matches
# the markets' settlement_ts). November 2025 markets already had their close moved to the actual date (2025-12-18).
# October 2025 CPI was never published by BLS (see raw/bls_CUSR0000SA0.json) -> no release day at all.
DELAYED_RELEASE_DAY = {"KXCPI-25SEP": "2025-10-24", "KXCPICORE-25SEP": "2025-10-24"}
NEVER_RELEASED = {"KXCPI-25OCT", "KXCPICORE-25OCT"}
SHUTDOWN_AFFECTED = {"25SEP", "25OCT", "25NOV"}  # event-ticker month codes delayed/disrupted by the 2025 shutdown


def _get(url: str, params: dict | None = None, headers: dict | None = None, tries: int = 6) -> requests.Response:
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r
        except Exception as e:  # rate limit / transient server error: back off and retry
            if attempt == tries - 1:
                raise
            print(f"  retry {url} {params} after {e}", flush=True)
            time.sleep(2 * (attempt + 1))
    raise AssertionError


def _cached_json(path: Path, fetch):
    if path.exists():
        return json.loads(path.read_text())
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def _all_pages(endpoint: str, params: dict, key: str) -> list:
    out, cursor = [], None
    while True:
        p = dict(params, **({"cursor": cursor} if cursor else {}))
        d = _get(KALSHI + endpoint, p).json()
        out += d.get(key, [])
        cursor = d.get("cursor")
        if not cursor:
            return out
        time.sleep(0.1)


def events(series: str) -> list:
    return _cached_json(RAW / f"events_{series}.json",
                        lambda: _all_pages("/events", {"series_ticker": series, "limit": 200}, "events"))


def markets(series: str) -> list:
    """Every market of the series: historical (archived, older) endpoint + live endpoint, de-duplicated."""
    hist = _cached_json(RAW / f"markets_historical_{series}.json",
                        lambda: _all_pages("/historical/markets", {"series_ticker": series, "limit": 1000}, "markets"))
    live = _cached_json(RAW / f"markets_live_{series}.json",
                        lambda: _all_pages("/markets", {"series_ticker": series, "limit": 1000}, "markets"))
    seen, out = set(), []
    for m in live + hist:  # live copy wins if a market appears in both
        if m["ticker"] not in seen:
            seen.add(m["ticker"])
            out.append(m)
    return out


def release_day(event_ticker: str, ms: list) -> pd.Timestamp | None:
    """BLS release date (ET calendar day) for an event, or None if BLS never published it.

    2022+ markets close at 08:25/08:29 ET on the scheduled release day. The 2021 markets closed the evening
    before release; their expiration_time falls on the release day (checked against the BLS calendar:
    2021-07-13, 08-11, 09-14, 10-13, 11-10, 12-10, 2022-01-12). Shutdown exceptions are listed above.
    """
    if event_ticker in NEVER_RELEASED:
        return None
    if event_ticker in DELAYED_RELEASE_DAY:
        return pd.Timestamp(DELAYED_RELEASE_DAY[event_ticker])
    close = pd.Series([pd.Timestamp(m["close_time"]) for m in ms]).dt.tz_convert(ET)
    close = close.min()
    if close.hour == 8:
        return close.normalize().tz_localize(None)
    exp = pd.Series([pd.Timestamp(m["expiration_time"]) for m in ms]).dt.tz_convert(ET).min()
    return exp.normalize().tz_localize(None)


def cutoff_ts(day: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(f"{day:%Y-%m-%d} {CUTOFF}", tz=ET)


def trades_before(ticker: str, cutoff: pd.Timestamp) -> dict:
    """The most recent (up to 200) trades at or before `cutoff`, from both the live and the historical trade
    endpoints (Kalshi archives older trades; a market's history can be split across the two)."""
    path = RAW / "trades" / f"{ticker}.json"

    def fetch():
        out = {"ticker": ticker, "max_ts": int(cutoff.timestamp()), "cutoff_et": str(cutoff)}
        for name, ep in [("live", "/markets/trades"), ("historical", "/historical/trades")]:
            d = _get(KALSHI + ep, {"ticker": ticker, "limit": 200, "max_ts": int(cutoff.timestamp())}).json()
            out[name] = d.get("trades", [])
            time.sleep(0.05)
        return out

    return _cached_json(path, fetch)


def nowcast() -> list:
    path = RAW / "nowcast_month.json"
    if not path.exists():
        try:
            data = _get(NOWCAST_URL, headers=UA).json()
            path.write_text(json.dumps(data))
        except Exception as e:  # fall back to the copy saved earlier in this session
            print(f"nowcast download failed ({e}); copying {NOWCAST_FALLBACK}")
            shutil.copy(NOWCAST_FALLBACK, path)
    return json.loads(path.read_text())


def bls() -> dict:
    return _cached_json(RAW / "bls_CUSR0000SA0.json", lambda: _get(BLS_URL).json())


def fetch_all(today: str = "2026-10-03") -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    nowcast()
    bls()
    for series in SERIES:
        events(series)
        ms = markets(series)
        by_event: dict[str, list] = {}
        for m in ms:
            by_event.setdefault(m["event_ticker"], []).append(m)
        n = 0
        for ev, group in sorted(by_event.items()):
            day = release_day(ev, group)
            # only released events whose markets have settled; NEVER_RELEASED events have no release day
            if day is None or day >= pd.Timestamp(today) or not all(m.get("expiration_value") for m in group):
                continue
            for m in group:
                trades_before(m["ticker"], cutoff_ts(day))
                n += 1
        print(f"{series}: {len(by_event)} events, trade snapshots cached for {n} markets", flush=True)


if __name__ == "__main__":
    fetch_all(*sys.argv[1:])
