"""Was it the drift or overpriced options? Profit attribution for the frozen deal-signed sold call.

For every trade of the frozen rule (hypotheses/FINAL_RULE.md), split the change in the sold call's
price over the 10-session hold into three causes with Black-Scholes (r = 0.04, no dividends,
consistent with the parity spot):
  stock    the stock's move (delta and curvature together)
  vol      the change in the call's own implied volatility (options getting cheaper or dearer)
  time     the passage of 10 sessions (time decay)
Each cause's share is its Shapley value: the average of its marginal effect over all 6 orders of
applying the three changes, so the split does not depend on an arbitrary order. The three add up
exactly to the call's price change. Trading costs (measured half-spreads) are a fourth line.

Also: the call's implied volatility on t_pre (before the filing), at entry and at exit, to see
whether options got pricier when the deal hit and whether that faded.

Comparison group: every quiet top-100 company (no 8-K within ±5 days) on the same dates, with the
same contract rule, entry and exit. That removes the noise of a random 6-company draw.

This is descriptive. It explains trades that already happened (including the 2026 trades from the
one-time out-of-sample run) and changes nothing in the rule.

Run from massive/:   .venv/bin/python research/attribution.py
Writes:              research/attribution/results.md (aggregates only)
"""
import sys
from itertools import permutations
from math import erf, exp, log, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from costs import last_quote  # noqa: E402
from ideas2 import OTM, all_filings  # noqa: E402
from oos_deal import DEALS, filings_near, one_per_deal  # noqa: E402
from scan import event_side  # noqa: E402

OUT = HERE / "attribution"
HOLD, R, QUIET_DAYS = 10, K.RISK_FREE, 5
LEG = f"C_U{OTM}"


def ncdf(x):
    return 0.5 * (1 + erf(x / sqrt(2)))


def bs_call(S, Kx, T, sig):
    if T <= 0 or sig <= 0:
        return max(S - Kx * exp(-R * T), 0.0)
    d1 = (log(S / Kx) + (R + 0.5 * sig * sig) * T) / (sig * sqrt(T))
    return S * ncdf(d1) - Kx * exp(-R * T) * ncdf(d1 - sig * sqrt(T))


def implied_vol(C, S, Kx, T):
    """Bisection; None if the price is outside the no-arbitrage range."""
    lo_px, hi_px = max(S - Kx * exp(-R * T), 0.0), S
    if not (lo_px + 1e-6 < C < hi_px) or T <= 0:
        return None
    lo, hi = 1e-4, 5.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if bs_call(S, Kx, T, mid) > C:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def shapley(F):
    """F(time, stock, vol) with each argument 0 (entry) or 1 (exit). Returns each factor's Shapley value."""
    names = ["time", "stock", "vol"]
    out = dict.fromkeys(names, 0.0)
    for order in permutations(range(3)):
        state = [0, 0, 0]
        for i in order:
            before = F(*state)
            state[i] = 1
            out[names[i]] += (F(*state) - before) / 6
    return out


def trade_rows(priced: dict, hs_lookup) -> pd.DataFrame:
    rows = []
    for pes in priced.values():
        for pe in pes:
            i0 = K.CAL.get_loc(pe.t_0)
            if i0 + HOLD >= len(K.CAL):
                continue
            x = K.CAL[i0 + HOLD]
            if x > pe.expiry_session or x > K.LAST_SESSION:
                continue
            leg = pe.legs[LEG]
            m0, m1, mp = pe.marks(pe.t_0), pe.marks(x), pe.marks(pe.t_pre)
            S0, S1, Sp = pe.synthetic_spot(pe.t_0, m0), pe.synthetic_spot(x, m1), pe.synthetic_spot(pe.t_pre, mp)
            C0, C1, Cp = m0[LEG], m1[LEG], mp[LEG]
            if any(np.isnan(v) for v in (S0, S1, C0, C1)):
                continue                                           # the rule's validity filter
            hs = hs_lookup(pe)
            if hs is None or np.isnan(hs):
                continue
            Kx = leg.strike
            T0, T1 = (pe.expiry - pe.t_0).days / 365, (pe.expiry - x).days / 365
            v0, v1 = implied_vol(C0, S0, Kx, T0), implied_vol(C1, S1, Kx, T1)
            vp = implied_vol(Cp, Sp, Kx, (pe.expiry - pe.t_pre).days / 365) if not (np.isnan(Cp) or np.isnan(Sp)) else None
            row = {"ticker": pe.ticker, "event_date": pe.event_date, "S0": S0, "strike_pct": Kx / S0 - 1,
                   "premium": C0 / S0, "iv_pre": vp, "iv_entry": v0, "iv_exit": v1,
                   "pnl_gross": -(C1 - C0) / S0, "cost": -2 * hs / S0}
            if v0 is None:
                row.update(time=np.nan, stock=np.nan, vol=np.nan, residual=np.nan)
            else:
                v1_used = v1 if v1 is not None else v0            # if exit IV can't be solved, the gap goes to residual
                F = lambda a, b, c: bs_call(S1 if b else S0, Kx, T1 if a else T0, v1_used if c else v0)  # noqa: E731
                sh = shapley(F)
                resid = (C1 - C0) - sum(sh.values())             # 0 when both IVs solve
                row.update({k: -v / S0 for k, v in sh.items()}, residual=-resid / S0)  # sold call: P&L = −Δprice
            rows.append(row)
    return pd.DataFrame(rows)


def quiet_peers(ev: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    days = raw.groupby("ticker")["filing_date"].apply(lambda s: np.unique(s.to_numpy(dtype="datetime64[D]"))).to_dict()
    rows = []
    for d, g in ev.groupby("filing_date"):
        d64 = np.datetime64(d, "D")
        for t in K.TOP_100:
            if t not in days or np.all(np.abs((days[t] - d64).astype(int)) > QUIET_DAYS):
                rows.append({"ticker": t, "event_date": d, "t_pre": g.t_pre.iloc[0], "t_0": g.t_0.iloc[0]})
    return pd.DataFrame(rows)


def analyse(label: str, ev: pd.DataFrame, raw: pd.DataFrame, quote_table=None) -> list[str]:
    peers = quiet_peers(ev, raw)
    keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in ev.itertuples()} |
                  {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in peers.itertuples()}, key=lambda k: (k[0], k[3]))
    priced, _ = K.price_many(keys, {"3-6m": K.EXPIRY_BUCKETS["3-6m"]}, [OTM], workers=16, label=f"attribution {label}")

    def hs_lookup(pe):
        if quote_table is not None and (pe.ticker, pe.event_date) in quote_table.index:
            return float(quote_table.loc[(pe.ticker, pe.event_date)])
        q = last_quote(pe.legs[LEG].ticker, pe.t_0)
        return (q["ask"] - q["bid"]) / 2 if q else np.nan

    tr = trade_rows(priced, hs_lookup)
    tr["pnl_net"] = tr.pnl_gross + tr.cost
    tr["iv_jump"] = tr.iv_entry - tr.iv_pre                       # around the filing: t_pre -> entry
    tr["iv_fade"] = tr.iv_exit - tr.iv_entry                      # over the hold: entry -> exit
    key = lambda df: list(zip(df.ticker, df.event_date))  # noqa: E731
    is_ev = pd.Series(key(tr)).isin(set(key(ev))).to_numpy()
    E, P = tr[is_ev].copy(), tr[~is_ev].copy()
    cols = ["pnl_net", "stock", "vol", "time", "residual", "cost", "iv_jump", "iv_fade"]
    pm = P.groupby("event_date")[cols].mean()
    G = E[cols].to_numpy() - pm.reindex(E.event_date.to_numpy()).to_numpy()
    cl = E.ticker.to_numpy()

    def ms(X):
        m, se, n = event_side(np.asarray(X, dtype=float), cl)
        return m, m / se, n

    mE, tE, nE = ms(E[cols])
    mG, tG, _ = ms(G)
    pP = P[cols].mean().to_numpy()
    names = {"pnl_net": "**Total, net of costs**", "stock": "Stock move", "vol": "Implied volatility change",
             "time": "Time decay", "residual": "Residual (unsolvable IVs)", "cost": "Trading costs",
             "iv_jump": "IV change around the filing (t_pre → entry), vol points", "iv_fade": "IV change over the hold (entry → exit), vol points"}
    lines = [f"### {label}: {len(E)} trades from {E.ticker.nunique()} companies; comparison: {len(P)} quiet-company trades "
             f"on the same {P.event_date.nunique()} dates\n",
             "Sold-call P&L per $1 of stock over the 10-session hold (mean; t clustered by company).\n",
             "| | after deal filings | quiet companies, same dates | difference (t) |", "|---|---|---|---|"]
    for j, c in enumerate(cols):
        if c in ("iv_jump", "iv_fade"):
            continue
        lines.append(f"| {names[c]} | {mE[j] * 100:+.2f}% | {pP[j] * 100:+.2f}% | {mG[j] * 100:+.2f}% ({tG[j]:+.1f}) |")
    lines += ["", "| Implied volatility of the sold call | after deal filings | quiet companies | difference (t) |", "|---|---|---|---|",
              f"| level on t_pre (before the filing), median | {E.iv_pre.median():.1%} | {P.iv_pre.median():.1%} | |",
              f"| level at entry, median | {E.iv_entry.median():.1%} | {P.iv_entry.median():.1%} | |"]
    for j, c in enumerate(cols):
        if c in ("iv_jump", "iv_fade"):
            lines.append(f"| {names[c]}, mean | {mE[j] * 100:+.2f} | {pP[j] * 100:+.2f} | {mG[j] * 100:+.2f} ({tG[j]:+.1f}) |")
    unsolved = int(E.iv_entry.isna().sum() + E.iv_exit.isna().sum())
    lines.append(f"\nCalls: median strike {E.strike_pct.median():+.1%} above the stock at entry, median premium "
                 f"{E.premium.median():.2%} of the stock price. Unsolvable implied vols among deal trades: {unsolved}.\n")
    return lines


def main():
    OUT.mkdir(exist_ok=True)
    ins = one_per_deal(K.build_events(DEALS, K.STUDY_START, K.STUDY_END, timing="next_session")).reset_index(drop=True)
    q = pd.read_pickle(K.CACHE_DIR / "derived" / "entry_quotes.pkl")
    qt = q[q.leg == LEG].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])["half_spread"]
    lines = ["# Was it the drift or overpriced options? (attribution of the frozen rule's trades)\n",
             "Black-Scholes, r = 4%, no dividends; Shapley split over the stock move, the change in the call's implied "
             "volatility, and 10 sessions of time. Positive = made money for the call seller.\n"]
    lines += analyse("In-sample 2024-25", ins, all_filings(), qt)
    allev = one_per_deal(K.build_events(DEALS, K.STUDY_START, K.OOS_END, timing="next_session", allow_oos=True))
    oos = allev[(allev.event_date >= pd.Timestamp(K.OOS_START)) & (allev.event_date <= pd.Timestamp(K.OOS_END))].reset_index(drop=True)
    lines += analyse("2026 (the trades from the one-time out-of-sample run, explained, not re-tested)", oos,
                     filings_near("2025-12-15", "2026-09-15"))
    text = "\n".join(lines)
    (OUT / "results.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
