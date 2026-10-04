"""Risk numbers for the deal-signed sold-call candidate (FINDINGS.md section 7). In-sample 2024-2025 only.

For each deal (first deal-signing 8-K per company per 60 days), the sold 3-6m 5% OTM call's daily P&L
per $1 of stock from entry (close of the session after the filing) to exit 10 sessions later, net of
the measured half-spread at entry and at exit. Also the same trade on the quiet same-day peers.

Reports:
  - per-trade mean, volatility, win rate, worst trade, and per-trade Sharpe;
  - a daily strategy: equal weight across open positions, flat when none. Annualized return,
    volatility, Sharpe, max drawdown, share of days invested;
  - the S&P 500 ETF (SPY) over the same dates, for scale.

Run from massive/:   .venv/bin/python research/sharpe_deal.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from ideas2 import OTM, all_filings, company_days, pick_peers  # noqa: E402
from round3 import DEALS  # noqa: E402

HOLD = 10
LEG = f"C_U{OTM}"


def one_per_deal(cd: pd.DataFrame) -> pd.DataFrame:
    d = cd[cd.tags.map(lambda s: bool(s & set(DEALS)))].sort_values(["ticker", "event_date"])
    keep, last = [], {}
    for i, r in d.iterrows():
        if r.ticker not in last or (r.event_date - last[r.ticker]).days > 60:
            keep.append(i)
            last[r.ticker] = r.event_date
    return d.loc[keep]


def paths(rows: pd.DataFrame, half_spread: pd.Series) -> dict:
    """(ticker, event_date) -> Series of cumulative sold-call P&L per $1 stock, indexed by session."""
    keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in rows.itertuples()}, key=lambda k: (k[0], k[3]))
    priced, _ = K.price_many(keys, {"3-6m": K.EXPIRY_BUCKETS["3-6m"]}, [OTM], workers=16, label="paths (cached)")
    out = {}
    for pes in priced.values():
        for pe in pes:
            leg = pe.legs[LEG]
            m0 = pe.marks(pe.t_0)
            S0 = pe.synthetic_spot(pe.t_0, m0)
            c0 = leg.mark(pe.t_0)
            hs = half_spread.get((pe.ticker, pe.event_date), np.nan)
            if np.isnan(c0) or np.isnan(S0) or np.isnan(hs):
                continue
            i0 = K.CAL.get_loc(pe.t_0)
            days = K.CAL[i0: i0 + HOLD + 1]
            if days[-1] > min(pe.expiry_session, K.LAST_SESSION):
                continue
            c = pd.Series([leg.mark(d) for d in days], index=days)
            S_exit = pe.synthetic_spot(days[-1])
            if np.isnan(c.iloc[-1]) or np.isnan(S_exit):            # same rule as the notebook: no stale exit marks
                continue
            c = c.ffill()
            pnl = -(c - c0) / S0 - hs / S0                          # sold call gains as it cheapens; half-spread to sell
            pnl.iloc[-1] -= hs / S0                                 # and half again to buy it back at exit
            out[(pe.ticker, pe.event_date)] = pnl
    return out


def per_trade(p: dict) -> pd.Series:
    return pd.Series({k: v.iloc[-1] for k, v in p.items()})


def daily_strategy(p: dict) -> pd.Series:
    """Equal weight across open positions; flat (0) on sessions with none."""
    incs = [v.diff().fillna(v.iloc[0]) for v in p.values()]           # daily P&L; the entry day carries the entry cost
    sessions = K.CAL[(K.CAL >= pd.Timestamp(K.STUDY_START)) & (K.CAL <= min(pd.Timestamp("2026-01-31"), K.LAST_SESSION))]
    rows = []
    for d in sessions:
        vals = [x for x in (v.get(d, np.nan) for v in incs) if not np.isnan(x)]
        rows.append(np.mean(vals) if vals else 0.0)
    return pd.Series(rows, index=sessions)


def stats_daily(r: pd.Series) -> dict:
    eq = r.cumsum()
    return {"ann_return": r.mean() * 252, "ann_vol": r.std() * np.sqrt(252), "sharpe": r.mean() / r.std() * np.sqrt(252),
            "max_drawdown": (eq - eq.cummax()).min(), "days_invested": (r != 0).mean()}


def main():
    counts = pd.read_csv(HERE / "event_counts.csv", index_col=0)
    raw = all_filings()
    cd = company_days(raw, set(counts.index[counts.primary_category == "financial_results"]))
    peers = pick_peers(cd, raw)
    quotes = pd.read_pickle(K.CACHE_DIR / "derived" / "entry_quotes.pkl")
    hs = quotes[quotes.leg == LEG].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])["half_spread"]
    deals = one_per_deal(cd)
    p_deal = paths(deals, hs)
    p_peer = paths(peers[peers.event_date.isin(deals.event_date)], hs)
    t_deal, t_peer = per_trade(p_deal), per_trade(p_peer)

    def show_trades(lab, t):
        sr = t.mean() / t.std()
        print(f"{lab:36s} n={len(t):3d}  mean {t.mean():+.2%}  vol {t.std():.2%}  win {(t > 0).mean():.0%}  "
              f"worst {t.min():+.2%}  best {t.max():+.2%}  per-trade Sharpe {sr:+.2f}")
        return sr
    print(f"Sold 3-6m 5% OTM call, held {HOLD} sessions, net of measured costs, per $1 of stock\n")
    sr = show_trades("after deal-signing 8-Ks", t_deal)
    show_trades("same dates, quiet companies", t_peer)
    n_years = 2.0
    per_year = len(t_deal) / n_years
    se = np.sqrt((1 + sr ** 2 / 2) / len(t_deal))
    print(f"\n{per_year:.0f} deals a year → annualized Sharpe ≈ per-trade × √{per_year:.0f} = {sr * np.sqrt(per_year):.2f} "
          f"(95% range ≈ {(sr - 2 * se) * np.sqrt(per_year):.2f} .. {(sr + 2 * se) * np.sqrt(per_year):.2f})")

    d = daily_strategy(p_deal)
    s = stats_daily(d)
    print(f"\nDaily strategy (equal weight across open deals, flat otherwise): ann. return {s['ann_return']:+.2%}, "
          f"ann. vol {s['ann_vol']:.2%}, Sharpe {s['sharpe']:.2f}, max drawdown {s['max_drawdown']:+.2%}, "
          f"invested {s['days_invested']:.0%} of days")
    for y in (2024, 2025):
        dy = d[d.index.year == y]
        print(f"   {y}: return {dy.sum():+.2%}, Sharpe {dy.mean() / dy.std() * np.sqrt(252):.2f}")

    spy = K.api_get_all(f"/v2/aggs/ticker/SPY/range/1/day/{K.STUDY_START}/2025-12-31", {"adjusted": "true", "sort": "asc", "limit": 50000})
    px = pd.Series([b["c"] for b in spy], index=pd.to_datetime([b["t"] for b in spy], unit="ms"))
    rs = px.pct_change().dropna()
    print(f"\nS&P 500 ETF (SPY), same two years, buy and hold: ann. return {rs.mean() * 252:+.2%}, ann. vol {rs.std() * np.sqrt(252):.2%}, "
          f"Sharpe {rs.mean() / rs.std() * np.sqrt(252):.2f} (before subtracting the ~4-5% cash rate)")


if __name__ == "__main__":
    main()
