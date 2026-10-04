"""Measured trading costs: the last bid/ask before the close for every leg we trade at entry.

For each priced company-day and quiet peer from ideas2.py (3-6m bucket, 5% OTM), read the last option
quote at or before 16:00 ET on the entry session for the four legs the strategies use (ATM call, ATM
put, 5% OTM call, 5% OTM put). Half the bid-ask spread is what crossing costs, one way.

Run from massive/:   .venv/bin/python research/costs.py
Writes:              .massive_cache/derived/entry_quotes.pkl (licensed-data derived, git-ignored)
                     research/costs_summary.md (aggregates only)
"""
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from ideas2 import OTM, all_filings, company_days, pick_peers  # noqa: E402

LEGS = {"C_K": "ATM call", "P_K": "ATM put", f"C_U{OTM}": "5% OTM call", f"P_L{OTM}": "5% OTM put"}


def last_quote(opt_ticker: str, day: pd.Timestamp) -> dict | None:
    """Last NBBO quote at or before 16:00 ET on `day`; None if missing, stale (another day) or broken."""
    close_utc = (pd.Timestamp(day).tz_localize("America/New_York") + pd.Timedelta(hours=16)).tz_convert("UTC")
    payload = K.api_get(f"/v3/quotes/{opt_ticker}", {"timestamp.lte": close_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                    "order": "desc", "sort": "timestamp", "limit": 1})
    rows = payload.get("results") or []
    if not rows:
        return None
    q = rows[0]
    ts = pd.Timestamp(q["sip_timestamp"], unit="ns", tz="UTC").tz_convert("America/New_York")
    bid, ask = q.get("bid_price"), q.get("ask_price")
    if ts.tz_localize(None).normalize() != pd.Timestamp(day) or not ask or ask <= 0 or bid is None or bid < 0 or ask < bid:
        return None
    return {"bid": float(bid), "ask": float(ask)}


def main():
    counts = pd.read_csv(HERE / "event_counts.csv", index_col=0)
    raw = all_filings()
    cd = company_days(raw, set(counts.index[counts.primary_category == "financial_results"]))
    peers = pick_peers(cd, raw)
    keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in cd.itertuples()} |
                  {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in peers.itertuples()}, key=lambda k: (k[0], k[3]))
    priced, _ = K.price_many(keys, {"3-6m": K.EXPIRY_BUCKETS["3-6m"]}, [OTM], workers=16, label="reprice (cached)")
    jobs = []
    for pes in priced.values():
        for pe in pes:
            for leg in LEGS:
                jobs.append((pe.ticker, pe.event_date, pe.t_0, leg, pe.legs[leg].ticker, pe.legs[leg].mark(pe.t_0)))
    print(f"{len(jobs):,} entry quotes to read", flush=True)
    with ThreadPoolExecutor(16) as pool:
        quotes = list(pool.map(lambda j: last_quote(j[4], j[2]), jobs))
    rows = []
    for j, q in zip(jobs, quotes):
        rows.append({"ticker": j[0], "event_date": j[1], "t_0": j[2], "leg": j[3], "contract": j[4], "mark": j[5],
                     "bid": q["bid"] if q else np.nan, "ask": q["ask"] if q else np.nan})
    qt = pd.DataFrame(rows)
    qt["half_spread"] = (qt.ask - qt.bid) / 2
    qt["mid"] = (qt.ask + qt.bid) / 2
    qt["half_spread_pct_of_mid"] = qt.half_spread / qt.mid
    qt.to_pickle(K.CACHE_DIR / "derived" / "entry_quotes.pkl")

    lines = ["# Measured option spreads at entry (top 100, 2024-2025, 3-6m expiry)\n",
             f"{qt.bid.notna().mean():.0%} of {len(qt):,} legs have a same-day quote before the close.\n",
             "| leg | median half-spread, % of option price | 75th pct | median half-spread, $ | notebook assumption |",
             "|---|---|---|---|---|"]
    for leg, lab in LEGS.items():
        x = qt[(qt.leg == leg) & qt.half_spread.notna()]
        lines.append(f"| {lab} | {x.half_spread_pct_of_mid.median():.2%} | {x.half_spread_pct_of_mid.quantile(.75):.2%} | "
                     f"${x.half_spread.median():.3f} | 5.00% |")
    text = "\n".join(lines)
    (HERE / "costs_summary.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
