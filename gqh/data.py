"""Data: Databento downloads (cached, with a credit guard), session bars, roll-safe futures returns,
cost estimates, and synthetic test data."""
from __future__ import annotations

import hashlib
import json
import os
import time

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from gqh import CACHE, ROOT

load_dotenv(ROOT / ".env")


def _client():
    import databento as db

    return db.Historical()  # reads DATABENTO_API_KEY


def databento(dataset: str, symbols, schema: str, start, end, stype_in: str = "raw_symbol") -> pd.DataFrame:
    """Fetch once from Databento, then read from data/cache/.

    Checks the price first and refuses anything above GQH_MAX_COST_USD (default $5). Use a fixed `end`
    so judges download exactly the history you used.
    """
    import databento as db

    symbols = [symbols] if isinstance(symbols, str) else list(symbols)
    request = dict(dataset=dataset, symbols=symbols, schema=schema,
                   start=str(start), end=str(end), stype_in=stype_in)
    key = hashlib.sha1(json.dumps(request, sort_keys=True).encode()).hexdigest()[:12]
    path = CACHE / f"{dataset}_{schema}_{key}.dbn.zst"
    part = path.with_name(path.name + ".part")
    # Another process is downloading the same request: wait for it instead of paying twice
    while not path.exists() and part.exists() and time.time() - part.stat().st_mtime < 120:
        time.sleep(5)
    if not path.exists():
        client = _client()
        cost = client.metadata.get_cost(**request)
        limit = float(os.getenv("GQH_MAX_COST_USD", "5"))
        if cost > limit:
            raise RuntimeError(f"Request would cost ${cost:.2f}, above GQH_MAX_COST_USD=${limit:.2f}. "
                               "Narrow the symbols or dates, or raise the limit in .env if you mean it.")
        print(f"Downloading {dataset} {schema} {symbols} {start}..{end} (${cost:.2f})")
        CACHE.mkdir(parents=True, exist_ok=True)
        for attempt in range(4):
            try:
                part.unlink(missing_ok=True)  # stale partial from a failed stream; the client won't overwrite it
                client.timeseries.get_range(**request, path=part)
                break
            except Exception as e:  # server timeouts on long requests: wait and retry
                if attempt == 3:
                    raise
                print(f"Retrying {dataset} {schema} {start}..{end} after {type(e).__name__}", flush=True)
                time.sleep(15 * (attempt + 1))
        part.rename(path)
    return db.DBNStore.from_file(path).to_df()


def databento_chunked(dataset: str, symbols, schema: str, start, end, stype_in: str = "raw_symbol",
                      workers: int = 6) -> pd.DataFrame:
    """Same as databento(), split into calendar-year requests downloaded in parallel.

    Long histories download much faster this way; each year is cached (and guarded) separately.
    """
    from concurrent.futures import ThreadPoolExecutor

    edges = [pd.Timestamp(start)] + [pd.Timestamp(f"{y}-01-01") for y in
                                     range(pd.Timestamp(start).year + 1, pd.Timestamp(end).year + 1)]
    edges = [e for e in edges if e < pd.Timestamp(end)] + [pd.Timestamp(end)]
    chunks = [(a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")) for a, b in zip(edges[:-1], edges[1:])]
    with ThreadPoolExecutor(workers) as pool:
        frames = list(pool.map(lambda c: databento(dataset, symbols, schema, c[0], c[1], stype_in), chunks))
    return pd.concat([f for f in frames if len(f)]).sort_index()


def price(dataset: str, symbols, schema: str, start, end, stype_in: str = "raw_symbol") -> dict:
    """What a request would cost, without downloading it."""
    symbols = [symbols] if isinstance(symbols, str) else list(symbols)
    request = dict(dataset=dataset, symbols=symbols, schema=schema, start=str(start), end=str(end), stype_in=stype_in)
    client = _client()
    return {"usd": client.metadata.get_cost(**request), "gb": client.metadata.get_billable_size(**request) / 1e9}


def available(dataset: str) -> dict:
    """Date range and schemas a dataset offers (e.g. available("GLBX.MDP3"))."""
    client = _client()
    return {"range": client.metadata.get_dataset_range(dataset), "schemas": client.metadata.list_schemas(dataset)}


def instrument_symbols(dataset: str, parent: str, start, end) -> dict[int, str]:
    """instrument_id -> raw symbol for every contract under a parent (e.g. "CL.FUT").

    Uses Databento's symbology API (free), one year at a time, cached in data/cache/.
    """
    path = CACHE / f"symbols_{dataset}_{parent}_{start}_{end}.json"
    if path.exists():
        return {int(k): v for k, v in json.loads(path.read_text()).items()}
    client, out = _client(), {}
    for year in range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1):
        lo = max(pd.Timestamp(start), pd.Timestamp(f"{year}-01-01"))
        hi = min(pd.Timestamp(end), pd.Timestamp(f"{year + 1}-01-01"))
        if lo >= hi:
            continue
        r = client.symbology.resolve(dataset=dataset, symbols=[parent], stype_in="parent", stype_out="instrument_id",
                                     start_date=lo.date(), end_date=hi.date())
        for raw, intervals in r["result"].items():
            for iv in intervals:
                out[int(iv["s"])] = raw
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def panel(bars: pd.DataFrame, field: str = "close") -> pd.DataFrame:
    """Databento bars (one row per symbol per timestamp) -> one column per symbol."""
    return bars.reset_index().pivot_table(index="ts_event", columns="symbol", values=field)


def stamp_bar_end(bars: pd.DataFrame, bar: str) -> pd.DataFrame:
    """Re-index Databento bars by when they END ("1m", "1h", ...). ts_event marks the bar's start, so a 12:00
    hourly bar closes at 13:00; stamping by end time keeps event-time logic free of lookahead."""
    out = bars.copy()
    out.index = out.index + pd.Timedelta(bar.replace("m", "min"))
    return out


def session_daily(bars: pd.DataFrame, tz: str = "America/New_York", open_time: str = "09:30",
                  close_time: str = "16:00") -> pd.DataFrame:
    """Intraday bars (ohlcv-1m, or ohlcv-1h with on-the-hour times) -> one bar per symbol per session.

    Databento's ohlcv-1d uses UTC days, so for US stocks its "close" is the last after-hours trade
    (~8 PM ET) and for futures it's the price at midnight UTC. Use this when you need the real session
    close. Each row is stamped at the session close (in UTC): the moment the bar is complete.
    """
    def minutes(hhmm):
        h, m = map(int, hhmm.split(":"))
        return h * 60 + m

    lo, hi = minutes(open_time), minutes(close_time)
    df = bars.reset_index().sort_values("ts_event")
    local = df["ts_event"].dt.tz_convert(tz)
    tod = local.dt.hour * 60 + local.dt.minute  # bar start time; a 15:59 1m bar ends at 16:00
    keep = (tod >= lo) & (tod < hi)
    df = df[keep].assign(day=local[keep].dt.normalize())
    out = (df.groupby(["symbol", "day"])
             .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                  volume=("volume", "sum"), instrument_id=("instrument_id", "last"))
             .reset_index())
    out["ts_event"] = (out["day"] + pd.Timedelta(minutes=hi)).dt.tz_convert("UTC")
    return out.drop(columns="day").set_index("ts_event").sort_index()


def roll_safe_returns(bars: pd.DataFrame, field: str = "close") -> pd.DataFrame:
    """Returns for continuous futures symbols (e.g. ES.c.0) that don't jump at contract rolls.

    On a roll day, today's contract is compared with its own price the day before, looked up across
    every symbol in `bars`. Fetch the next rank too (ES.c.0 and ES.c.1) so that price is available;
    otherwise the roll-day return is NaN.
    """
    px = bars.reset_index()[["ts_event", "instrument_id", "symbol", field]]
    lookup = (px[["instrument_id", "ts_event", field]]
              .drop_duplicates(["instrument_id", "ts_event"])
              .rename(columns={"ts_event": "prev_ts", field: "prev_px"}))
    out = {}
    for sym, g in px.groupby("symbol"):
        g = g.sort_values("ts_event").assign(prev_ts=lambda d: d["ts_event"].shift(1))
        g = g.merge(lookup, on=["instrument_id", "prev_ts"], how="left")
        out[sym] = pd.Series((g[field] / g["prev_px"] - 1).to_numpy(), index=g["ts_event"].to_numpy())
    result = pd.DataFrame(out)
    result.index.name = "ts_event"
    return result


def futures_cost_bps(price: float, tick_size: float, multiplier: float, fee_per_contract: float = 2.5,
                     slippage_ticks: float = 0.5) -> float:
    """Per-side trading cost in bps of notional, for justifying `cost_bps` in the note.

    Half the spread of a one-tick-wide market (0.5 tick) + slippage + exchange/broker fees.
    Tick size and multiplier come from the exchange contract specs (or Databento's `definition` schema).
    """
    per_contract = (0.5 + slippage_ticks) * tick_size * multiplier + fee_per_contract
    return per_contract / (price * multiplier) * 1e4


def synthetic_prices(n_assets: int = 5, start="2012-01-02", end="2026-10-01", seed: int = 7) -> pd.DataFrame:
    """Daily prices with a slow-moving drift, for testing the pipeline without an API key."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, end)
    drift = np.zeros((len(index), n_assets))
    for t in range(1, len(index)):
        drift[t] = 0.995 * drift[t - 1] + rng.normal(0, 0.00006, n_assets)
    returns = drift + rng.normal(0, 0.01, (len(index), n_assets))
    prices = 100 * np.exp(np.cumsum(returns, axis=0))
    return pd.DataFrame(prices, index=index, columns=[f"ASSET{i + 1}" for i in range(n_assets)])
