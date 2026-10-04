"""Sample-size survey: how many top-100 events does each of the 119 8-K tags have?

Counts only. No option prices, no returns, nothing from the out-of-sample window (2026), so this
can run before any hypothesis is fixed without touching results.

For every tag it reports events per window (one event per filer per filing date, as the notebook
collapses them), how many distinct tickers they come from, and how often the event shares its filing
date with an earnings release (the main confound the challenge has no calendar for).

Run from massive/:   .venv/bin/python research/count_events.py
Writes:              research/event_counts.csv, research/taxonomy.csv
"""
import hashlib
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # massive/
BASE_URL = "https://api.massive.com"
CACHE_DIR = ROOT / ".massive_cache"     # shared with the notebook, so nothing is fetched twice

# The notebook's TOP_100, unchanged.
TOP_100 = """
AAPL ABBV ABT ACN ADBE AIG AMD AMGN AMT AMZN AVGO AXP BA BAC BK BKNG BLK BMY BRK.B C
CAT CHTR CL CMCSA COF COP COST CRM CSCO CVS CVX DE DHR DIS DUK EMR FDX GD GE GILD
GM GOOGL GS HD HON IBM INTC INTU ISRG JNJ JPM KO LIN LLY LMT LOW MA MCD MDLZ MDT
MET META MMM MO MRK MS MSFT NEE NFLX NKE NOW NVDA ORCL PEP PFE PG PLTR PM PYPL QCOM
RTX SBUX SCHW SO T TGT TMO TMUS TSLA TXN UBER UNH UNP UPS USB V VZ WFC WMT XOM
""".split()

# Windows we may count. 2026 (the out-of-sample window) is deliberately absent.
WINDOWS = {
    "pre_2024": ("2022-01-01", "2023-12-31"),     # no options history on contestant keys; a likely sealed-window region
    "in_sample": ("2024-01-01", "2025-12-31"),
}


def load_api_key(name: str = "MASSIVE_API_KEY") -> str:
    key = (os.environ.get(name) or "").strip()
    env_file = ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key or key == "your-key-here":
        raise SystemExit(f"No {name}: put it in {env_file} (see .env.example).")
    return key


SESSION = requests.Session()


def api_get(path_or_url: str, params: dict | None = None) -> dict:
    """Same caching scheme as the notebook: one file per full URL in .massive_cache/."""
    url = path_or_url if path_or_url.startswith("http") else BASE_URL + path_or_url
    full_url = requests.Request("GET", url, params=params).prepare().url
    cache_file = CACHE_DIR / (hashlib.sha1(full_url.encode()).hexdigest() + ".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    for attempt in range(10):
        resp = SESSION.get(full_url, timeout=60)
        if resp.status_code in (429, 500, 502, 503, 504):
            retry_after = resp.headers.get("Retry-After", "")
            time.sleep(float(retry_after) if retry_after.isdigit() else min(2 ** attempt, 20))
            continue
        break
    resp.raise_for_status()
    payload = resp.json()
    cache_file.write_text(json.dumps(payload))
    return payload


def api_get_all(path: str, params: dict | None = None, max_pages: int = 500) -> list[dict]:
    payload = api_get(path, params)
    rows = list(payload.get("results") or [])
    pages = 1
    while payload.get("next_url") and pages < max_pages:
        payload = api_get(payload["next_url"])
        rows.extend(payload.get("results") or [])
        pages += 1
    return rows


def normalize_ticker(t) -> str | None:
    if not isinstance(t, str) or not t.strip():
        return None
    return t.strip().upper().replace("/", ".")


def main():
    SESSION.headers["Authorization"] = f"Bearer {load_api_key()}"
    CACHE_DIR.mkdir(exist_ok=True)

    taxonomy = pd.DataFrame(api_get_all("/stocks/taxonomies/vX/disclosures", {"limit": 1000}))
    taxonomy.to_csv(HERE / "taxonomy.csv", index=False)
    print(f"taxonomy: {len(taxonomy)} tertiary tags, {taxonomy.secondary_category.nunique()} secondary, "
          f"{taxonomy.primary_category.nunique()} primary; versions {sorted(taxonomy.taxonomy.unique())}")

    start, end = min(w[0] for w in WINDOWS.values()), max(w[1] for w in WINDOWS.values())
    frames = []
    for i, t in enumerate(TOP_100, 1):
        for query_ticker in ([t, t.replace(".", "/")] if "." in t else [t]):
            rows = api_get_all("/stocks/filings/8-K/vX/disclosures", {
                "tickers": query_ticker, "filing_date.gte": start, "filing_date.lte": end,
                "limit": 1000, "sort": "filing_date.asc",
            })
            if rows:
                frames.append(pd.DataFrame(rows).assign(universe_ticker=t))
        if i % 20 == 0:
            print(f"  {i}/100 tickers")
    raw = pd.concat(frames, ignore_index=True)
    raw["filing_date"] = pd.to_datetime(raw["filing_date"])
    raw = raw.drop_duplicates(["accession_number", "tertiary_category", "supporting_text"])
    print(f"{len(raw):,} tagged disclosures for the top 100, {start}..{end}; "
          f"{raw.universe_ticker.nunique()} tickers have at least one")

    # One event per (filer, filing date, tag), as the notebook's build_events collapses them.
    ev = raw.drop_duplicates(["cik", "filing_date", "tertiary_category"]).copy()
    ev["window"] = None
    for name, (a, b) in WINDOWS.items():
        ev.loc[(ev.filing_date >= a) & (ev.filing_date <= b), "window"] = name

    # Earnings confound: does the same filer file an earnings-family tag on the same date?
    earnings_tags = set(taxonomy.loc[taxonomy.primary_category == "financial_results", "tertiary_category"])
    earn_days = set(map(tuple, ev.loc[ev.tertiary_category.isin(earnings_tags), ["cik", "filing_date"]].to_numpy()))
    ev["same_day_as_earnings"] = [(c, d) in earn_days for c, d in zip(ev.cik, ev.filing_date)]

    ins = ev[ev.window == "in_sample"]
    counts = (ins.groupby("tertiary_category")
                 .agg(in_sample_events=("cik", "size"), in_sample_tickers=("universe_ticker", "nunique"),
                      share_same_day_as_earnings=("same_day_as_earnings", "mean"))
                 .join(ev[ev.window == "pre_2024"].groupby("tertiary_category").size().rename("pre_2024_events"))
                 .fillna({"pre_2024_events": 0}))
    counts["expected_oos_events"] = (counts.in_sample_events * 8 / 24).round(1)    # OOS is 8 months; a rate estimate, not a count
    counts = (taxonomy.set_index("tertiary_category")[["primary_category", "secondary_category", "description"]]
                      .join(counts, how="left").fillna({"in_sample_events": 0, "in_sample_tickers": 0, "pre_2024_events": 0})
                      .sort_values("in_sample_events", ascending=False))
    counts.to_csv(HERE / "event_counts.csv")
    print(f"earnings-family tags: {sorted(earnings_tags)}")
    print(f"earnings-family filing days in-sample (proxy earnings calendar): "
          f"{ins[ins.tertiary_category.isin(earnings_tags)].drop_duplicates(['cik', 'filing_date']).shape[0]} "
          f"(a full calendar would be ~800 for 100 names over 8 quarters)")
    with pd.option_context("display.max_rows", 200, "display.width", 200, "display.max_colwidth", 60):
        print(counts.drop(columns="description"))


if __name__ == "__main__":
    main()
