"""Deep dive on one category × one strategy, in-sample only: is the scan's result robust?

Reprices the category and the shared placebo pool on every expiry bucket and OTM level, under both
entry-timing rules, then reports for the chosen strategy:
  1. the decay curve: event vs ordinary days at every fixed horizon (gross and net of costs);
  2. the sensitivity grid: bucket × OTM × timing × entry session;
  3. stability: 2024 vs 2025, and leave-one-ticker-out;
  4. the earnings confound: events within 5 sessions of an earnings-family 8-K for the same filer;
  5. capacity inputs: option volume in the traded legs on the entry session.

Run from massive/:   .venv/bin/python research/deepdive.py <category> <strategy>
                     e.g. research/deepdive.py combo:debt_offering cash_secured_put
Writes:              research/deepdive/<category>__<strategy>.md (aggregates only)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from scan import COMBOS, HORIZONS, build_pool, event_side, placebo_side, placebo_weights, week_ids  # noqa: E402

OUT = HERE / "deepdive"
EARNINGS_WINDOW = 5      # sessions


def tags_for(category: str) -> list[str]:
    return COMBOS.get(category, [category])


def priced_results(keys, timing_label):
    priced, _ = K.price_many(keys, K.EXPIRY_BUCKETS, K.OTM_GRID, workers=16, label=f"deepdive {timing_label}")
    return K.evaluate([pe for v in priced.values() for pe in v], K.OTM_GRID)


def stats(res_ev, res_pool, pool_keys, ev, strategy, bucket, otm, entry, net=False, haircut=K.COST_HAIRCUT):
    """Per-horizon event mean, placebo mean, gap and t (cluster-robust by week)."""
    def wide(r):
        r = r[(r.bucket == bucket) & (r.otm == otm) & (r.entry == entry) & (r.horizon != 0)].copy()
        v = r[strategy] - (K.round_trip_cost(r, strategy, haircut) if net else 0.0)
        r = r.assign(v=v, h=r.horizon.astype(str))
        return r.pivot_table(index=["ticker", "event_date"], columns="h", values="v", aggfunc="first") \
                .reindex(columns=[str(h) for h in HORIZONS])
    E, P = wide(res_ev), wide(res_pool)
    idx = pd.MultiIndex.from_frame(ev[["ticker", "event_date"]]).intersection(E.index)
    pidx = pd.MultiIndex.from_frame(pool_keys[["ticker", "event_date"]]).intersection(P.index)
    if len(idx) < 5:
        return None
    evp = ev.set_index(["ticker", "event_date"]).loc[idx].reset_index()
    pk = pool_keys.set_index(["ticker", "event_date"]).loc[pidx].reset_index()
    m_e, se_e, n = event_side(E.loc[idx].to_numpy(), week_ids(evp.t_0))
    m_p, se_p, _ = placebo_side(P.loc[pidx].to_numpy(), placebo_weights(pk, evp))
    gap = m_e - m_p
    return pd.DataFrame({"n": n, "event": m_e, "placebo": m_p, "gap": gap, "t": gap / np.sqrt(se_e ** 2 + se_p ** 2),
                         "t_event": m_e / se_e}, index=[str(h) for h in HORIZONS])


def pct(v):
    return "" if pd.isna(v) else f"{v * 100:+.2f}%"


def main(category: str, strategy: str):
    OUT.mkdir(exist_ok=True)
    pool = build_pool()
    lines = [f"# Deep dive: {category} × {K.STRATEGY_LABEL[strategy]} (in-sample 2024-2025 only)\n"]
    by_timing = {}
    for timing in ("next_session", "filing_day"):
        ev = K.build_events(tags_for(category), K.STUDY_START, K.STUDY_END, timing=timing)
        pk = pool.copy()
        if timing == "filing_day":            # the pool's fake filing session is then d itself
            pk["t_0"] = pk["event_date"]
        keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in ev.itertuples()} |
                      {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in pk.itertuples()}, key=lambda k: (k[0], k[3]))
        res = priced_results(keys, timing)
        ev_idx = pd.MultiIndex.from_frame(ev[["ticker", "event_date"]])
        in_ev = pd.MultiIndex.from_frame(res[["ticker", "event_date"]]).isin(ev_idx)
        in_pool = pd.MultiIndex.from_frame(res[["ticker", "event_date"]]).isin(pd.MultiIndex.from_frame(pk[["ticker", "event_date"]]))
        by_timing[timing] = (ev, res[in_ev], res[in_pool], pk)

    ev, r_ev, r_pool, pk = by_timing["next_session"]
    lines.append(f"{len(ev)} events, {ev.ticker.nunique()} tickers. Entry = close of the session after the filing date "
                 "unless stated. Gap = event mean − ordinary-day mean (same ticker mix). t is cluster-robust by week.\n")

    lines.append("## 1 · Decay curve (3-6m, 5% OTM)\n")
    for net in (False, True):
        s = stats(r_ev, r_pool, pk, ev, strategy, "3-6m", 0.05, "post", net=net)
        lines.append(f"**{'Net of costs (5% of premium each way)' if net else 'Gross'}**\n")
        lines.append("| horizon | n | event | ordinary days | gap | t (gap) | t (event alone) |\n|---|---|---|---|---|---|---|")
        for h, row in s.iterrows():
            lines.append(f"| {h} | {int(row.n)} | {pct(row.event)} | {pct(row.placebo)} | {pct(row.gap)} | {row.t:+.2f} | {row.t_event:+.2f} |")
        lines.append("")

    lines.append("## 2 · Sensitivity: gap (t) at h=21 / h=42 / expiry, gross\n")
    lines.append("| timing | entry | bucket | OTM | h=21 | h=42 | expiry |\n|---|---|---|---|---|---|---|")
    for timing, (ev_t, re_t, rp_t, pk_t) in by_timing.items():
        for entry in ("post", "pre"):
            if entry == "pre" and timing == "filing_day":
                continue                       # identical to next_session pre (same t_pre)
            for bucket in K.EXPIRY_BUCKETS:
                for otm in K.OTM_GRID:
                    s = stats(re_t, rp_t, pk_t, ev_t, strategy, bucket, otm, entry)
                    if s is None:
                        continue
                    cells = [f"{pct(s.loc[h, 'gap'])} ({s.loc[h, 't']:+.1f})" if pd.notna(s.loc[h, "gap"]) else "" for h in ("21", "42", "exp")]
                    lines.append(f"| {timing} | {entry} | {bucket} | {otm:.0%} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## 3 · Stability (3-6m, 5% OTM, gross gap at h=21 / 42 / expiry)\n")
    lines.append("| subset | n | h=21 | h=42 | expiry |\n|---|---|---|---|---|")
    subsets = {"all": ev, "2024 only": ev[ev.event_date.dt.year == 2024], "2025 only": ev[ev.event_date.dt.year == 2025]}
    top = ev.ticker.value_counts()
    for t in top.index[:5]:
        subsets[f"without {t} ({top[t]} events)"] = ev[ev.ticker != t]
    for name, sub in subsets.items():
        s = stats(r_ev, r_pool, pk, sub, strategy, "3-6m", 0.05, "post")
        if s is None:
            continue
        lines.append(f"| {name} | {int(s.n.max())} | " + " | ".join(f"{pct(s.loc[h, 'gap'])} ({s.loc[h, 't']:+.1f})" for h in ("21", "42", "exp")) + " |")
    lines.append("")

    # Earnings confound: earnings-family 8-Ks for the same filer within EARNINGS_WINDOW sessions.
    counts = pd.read_csv(HERE / "event_counts.csv", index_col=0)
    earn_tags = list(counts.index[(counts.primary_category == "financial_results") & (counts.in_sample_events > 0)])
    earn = K.build_events(earn_tags, K.STUDY_START, K.STUDY_END, timing="filing_day")
    near = []
    for r in ev.itertuples():
        d = earn.loc[earn.ticker == r.ticker, "t_0"]
        near.append(bool(len(d)) and min(abs(K.sessions_between(min(x, r.t_0), max(x, r.t_0))) for x in d) <= EARNINGS_WINDOW)
    ev_far = ev[~np.array(near, dtype=bool)]
    s = stats(r_ev, r_pool, pk, ev_far, strategy, "3-6m", 0.05, "post")
    lines.append(f"## 4 · Earnings confound\n\n{np.mean(near):.0%} of events are within {EARNINGS_WINDOW} sessions of an "
                 f"earnings-family 8-K by the same filer (a partial earnings calendar: coverage of those tags is thin).\n")
    if s is not None:
        lines.append(f"Excluding them (n={int(s.n.max())}): gap at h=21 / 42 / expiry = " +
                     " / ".join(f"{pct(s.loc[h, 'gap'])} (t {s.loc[h, 't']:+.1f})" for h in ("21", "42", "exp")) + "\n")

    r0 = r_ev[(r_ev.bucket == "3-6m") & (r_ev.otm == 0.05) & (r_ev.entry == "post") & (r_ev.horizon == 0)]
    vol_col = {"long_call": ["vol_CK"], "covered_call": ["vol_CU"], "protective_put": ["vol_PL"],
               "collar": ["vol_CU", "vol_PL"], "cash_secured_put": ["vol_PL"]}[strategy]
    v = r0[vol_col].min(axis=1)
    lines.append(f"## 5 · Capacity inputs\n\nContracts traded in the thinnest leg on the entry session: median {v.median():,.0f}, "
                 f"25th percentile {v.quantile(.25):,.0f}. Median underlying price ${r0.S_entry.median():,.0f} "
                 f"(one contract = 100 shares, so ≈ ${r0.S_entry.median() * 100:,.0f} notional per contract).\n")

    path = OUT / f"{category.replace(':', '_')}__{strategy}.md"
    path.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
