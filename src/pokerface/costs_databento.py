"""Measured opening half-spreads from Databento bbo-1m, for per-trade cost calibration.

For each event row (ticker, entry_date) we pull the 1-minute sampled best bid/offer of the stock's
primary listing venue from 09:30 to 09:40 ET on the entry date (our fills are at the open) and return
the median quoted half-spread in basis points.

    half_spread_bps = (ask - bid) / 2 / mid * 1e4,   mid = (ask + bid) / 2

Design rules
- Cost check first. Every uncached (dataset, date) request is priced with
  `metadata.get_cost` (free) before anything is fetched. If the total exceeds `max_usd`
  (default $DBN_MAX_USD or $5) nothing is fetched and a CostLimitExceeded lists the breakdown.
- On-disk cache in data/cache/databento/ (gitignored; raw licensed data is never committed).
  Cached windows need no key, so a rerun is free and offline. Empty windows are cached too.
- One request per (dataset, date), with all of that day's symbols, so 600 events cost about as
  many HTTP calls as there are distinct entry dates.
- Prices from Databento are raw (unadjusted). A half-spread is a same-minute ratio, so splits
  and dividends do not matter here.

Caveats (write these into the note)
- XNAS.ITCH / ARCX.PILLAR / XNYS.PILLAR quotes are the BBO of one venue, not the consolidated
  NBBO. A venue BBO is never tighter than the NBBO, so these half-spreads are an upper bound
  on the NBBO half-spread (conservative for costs).
- Coverage: XNAS.ITCH and ARCX.PILLAR from 2018-05-01, XNYS.PILLAR from 2023-03-28 (Databento
  dataset pages). Events earlier than that get NaN and note="before_coverage"; use the flat
  cost assumption for them. Confirm starts with `metadata.get_dataset_range` (free).
- Sample timestamps: bbo-1m records are indexed by ts_recv (the sample time). We keep samples
  with 09:30 < ts <= 09:40 ET, i.e. strictly after the opening cross.

Usage (needs DATABENTO_API_KEY; do not run in the backtest loop):
    from pokerface.costs_databento import quoted_spreads
    out = quoted_spreads(events[["ticker", "entry_date"]], key=os.environ["DATABENTO_API_KEY"])
    est = quoted_spreads(events, key, estimate_only=True)   # price the pull, fetch nothing
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "cache" / "databento"
ET = "America/New_York"
SCHEMA = "bbo-1m"

# Primary listing venue. The opening cross and the deepest book are there.
NYSE_ARCA = {"SPY", "XLK", "XLF", "XLE", "XLV", "XLY", "XLI", "XLP", "XLU", "IWM", "DIA"}
NYSE = {"JPM", "BAC", "GS", "DIS", "GM", "F", "UBER", "CRM"}
# Listing moved from NYSE to Nasdaq (UNVERIFIED date: PLTR transfer effective 2024-11-26).
LISTING_SWITCH = {"PLTR": ("XNYS.PILLAR", "2024-11-26", "XNAS.ITCH")}
DATASET_START = {"XNAS.ITCH": "2018-05-01", "ARCX.PILLAR": "2018-05-01", "XNYS.PILLAR": "2023-03-28"}


class CostLimitExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Window:
    start: str = "09:30"
    end: str = "09:40"


def venue_for(ticker: str, day: pd.Timestamp) -> tuple[str, str]:
    """(dataset, note). NYSE names before XNYS.PILLAR coverage fall back to Nasdaq-venue quotes."""
    t = ticker.upper()
    if t in LISTING_SWITCH:
        old, switch, new = LISTING_SWITCH[t]
        ds = old if day < pd.Timestamp(switch) else new
    elif t in NYSE_ARCA:
        ds = "ARCX.PILLAR"
    elif t in NYSE:
        ds = "XNYS.PILLAR"
    else:
        ds = "XNAS.ITCH"
    note = "primary_venue_bbo"
    if ds == "XNYS.PILLAR" and day < pd.Timestamp(DATASET_START["XNYS.PILLAR"]):
        ds, note = "XNAS.ITCH", "nasdaq_venue_bbo_not_primary"
    if day < pd.Timestamp(DATASET_START[ds]):
        note = "before_coverage"
    return ds, note


def _bounds(day: pd.Timestamp, w: Window) -> tuple[pd.Timestamp, pd.Timestamp]:
    d = day.strftime("%Y-%m-%d")
    t0 = pd.Timestamp(f"{d} {w.start}", tz=ET)
    t1 = pd.Timestamp(f"{d} {w.end}", tz=ET)
    return t0, t1


def _cache_path(cache_dir: Path, dataset: str, ticker: str, day: pd.Timestamp, w: Window) -> Path:
    tag = f"{w.start.replace(':', '')}-{w.end.replace(':', '')}"
    return cache_dir / SCHEMA / dataset / ticker.upper() / f"{day:%Y-%m-%d}_{tag}.parquet"


def _write_atomic(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp)
    tmp.replace(path)


def _log_spend(cache_dir: Path, rec: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / "_spend.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")


def _client(key: str | None, client: Any = None):
    if client is not None:
        return client
    key = key or os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError("DATABENTO_API_KEY missing and some windows are not cached")
    import databento as db

    return db.Historical(key=key)


def half_spread_stats(q: pd.DataFrame, t0: pd.Timestamp, t1: pd.Timestamp) -> dict:
    """Median / first-sample quoted half-spread (bps) from a bbo-1m frame indexed by ET time."""
    if q is None or len(q) == 0:
        return {"half_spread_bps_med": np.nan, "half_spread_bps_first": np.nan, "n_quotes": 0}
    q = q[(q.index > t0) & (q.index <= t1)]
    bid, ask = q["bid_px_00"].astype(float), q["ask_px_00"].astype(float)
    ok = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > bid)
    bid, ask = bid[ok], ask[ok]
    if len(bid) == 0:
        return {"half_spread_bps_med": np.nan, "half_spread_bps_first": np.nan, "n_quotes": 0}
    mid = (bid + ask) / 2.0
    hs = (ask - bid) / 2.0 / mid * 1e4
    return {"half_spread_bps_med": float(hs.median()), "half_spread_bps_first": float(hs.iloc[0]),
            "n_quotes": int(len(hs))}


def quoted_spreads(events_df: pd.DataFrame, key: str | None = None, *, max_usd: float | None = None,
                   window: Window = Window(), cache_dir: Path | str = CACHE_DIR,
                   estimate_only: bool = False, client: Any = None) -> pd.DataFrame:
    """Median quoted half-spread (bps) at the entry open for each (ticker, entry_date) row.

    Returns a frame aligned to events_df.index with columns:
    ticker, entry_date, dataset, half_spread_bps_med, half_spread_bps_first, n_quotes,
    cache_hit, note. With estimate_only=True returns the per-request cost table instead
    (columns dataset, date, symbols, usd) and fetches nothing.
    """
    if not {"ticker", "entry_date"} <= set(events_df.columns):
        raise ValueError("events_df needs columns 'ticker' and 'entry_date'")
    cache_dir = Path(cache_dir)
    max_usd = float(os.environ.get("DBN_MAX_USD", "5")) if max_usd is None else float(max_usd)

    ev = events_df[["ticker", "entry_date"]].copy()
    ev["ticker"] = ev["ticker"].astype(str).str.upper()
    ev["entry_date"] = pd.to_datetime(ev["entry_date"]).dt.tz_localize(None).dt.normalize()
    vn = [venue_for(t, d) for t, d in zip(ev["ticker"], ev["entry_date"])]
    ev["dataset"] = [v[0] for v in vn]
    ev["note"] = [v[1] for v in vn]

    # Which (dataset, date, ticker) windows still need fetching?
    need = ev[(ev["note"] != "before_coverage")].drop_duplicates(["dataset", "entry_date", "ticker"])
    need = need[[not _cache_path(cache_dir, r.dataset, r.ticker, r.entry_date, window).exists()
                 for r in need.itertuples()]]
    groups = (need.groupby(["dataset", "entry_date"])["ticker"].apply(lambda s: sorted(set(s)))
              .reset_index() if len(need) else pd.DataFrame(columns=["dataset", "entry_date", "ticker"]))

    # 1) price every uncached request before fetching anything
    c = _client(key, client) if len(groups) else None
    costs = []
    for g in groups.itertuples(index=False):
        t0, t1 = _bounds(g.entry_date, window)
        usd = float(c.metadata.get_cost(dataset=g.dataset, schema=SCHEMA, symbols=g.ticker,
                                        stype_in="raw_symbol", start=t0.tz_convert("UTC"),
                                        end=(t1 + pd.Timedelta(minutes=1)).tz_convert("UTC")))
        costs.append({"dataset": g.dataset, "date": g.entry_date, "symbols": g.ticker, "usd": usd})
    cost_df = pd.DataFrame(costs, columns=["dataset", "date", "symbols", "usd"])
    total = float(cost_df["usd"].sum()) if len(cost_df) else 0.0
    if estimate_only:
        cost_df.attrs["total_usd"] = total
        return cost_df
    if total > max_usd:
        raise CostLimitExceeded(f"estimated ${total:.2f} > cap ${max_usd:.2f} for {len(cost_df)} "
                                f"requests; raise max_usd / DBN_MAX_USD or shrink events.\n"
                                f"{cost_df.sort_values('usd', ascending=False).head(10)}")

    # 2) fetch, split by symbol, cache every window (empty ones too)
    for row in cost_df.itertuples(index=False):
        t0, t1 = _bounds(row.date, window)
        store = c.timeseries.get_range(dataset=row.dataset, schema=SCHEMA, symbols=row.symbols,
                                       stype_in="raw_symbol", start=t0.tz_convert("UTC"),
                                       end=(t1 + pd.Timedelta(minutes=1)).tz_convert("UTC"))
        df = store.to_df(tz=ET)
        keep = [k for k in ("symbol", "bid_px_00", "ask_px_00", "bid_sz_00", "ask_sz_00") if k in df.columns]
        df = df[keep] if len(df) else pd.DataFrame(columns=keep or ["symbol", "bid_px_00", "ask_px_00"])
        for sym in row.symbols:
            part = df[df["symbol"] == sym] if "symbol" in df.columns else df.iloc[0:0]
            _write_atomic(part, _cache_path(cache_dir, row.dataset, sym, row.date, window))
        _log_spend(cache_dir, {"ts": time.time(), "dataset": row.dataset, "date": f"{row.date:%Y-%m-%d}",
                               "symbols": row.symbols, "usd": row.usd, "rows": int(len(df))})

    # 3) per-event statistics from the cache
    fetched = {(r.dataset, s, r.date) for r in cost_df.itertuples(index=False) for s in r.symbols}
    out = []
    for idx, r in ev.iterrows():
        rec = {"ticker": r.ticker, "entry_date": r.entry_date, "dataset": r.dataset, "note": r.note,
               "cache_hit": False, "half_spread_bps_med": np.nan, "half_spread_bps_first": np.nan,
               "n_quotes": 0}
        if r.note != "before_coverage":
            p = _cache_path(cache_dir, r.dataset, r.ticker, r.entry_date, window)
            rec["cache_hit"] = (r.dataset, r.ticker, r.entry_date) not in fetched
            q = pd.read_parquet(p) if p.exists() else None
            t0, t1 = _bounds(r.entry_date, window)
            if q is not None and len(q):
                q.index = pd.DatetimeIndex(q.index).tz_convert(ET)
            rec.update(half_spread_stats(q, t0, t1))
            if rec["n_quotes"] == 0:
                rec["note"] = "no_quotes_in_window"
        out.append(pd.Series(rec, name=idx))
    res = pd.DataFrame(out)
    res.attrs["total_usd"] = total
    return res
