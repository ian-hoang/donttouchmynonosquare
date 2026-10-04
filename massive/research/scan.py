"""In-sample scan: every 8-K tag with enough events × the five strategies × the fixed horizons.

Question: after a given kind of 8-K, does any of the five option strategies do better than it does on
ordinary days for the same companies, and is it profitable after costs? Because we look at many tags,
strategies and horizons, some cells will look good by luck alone, so every tag is also compared with
hundreds of fake "tags" made of random ordinary days ("how good would the best cell look by chance?").

Only the in-sample window (2024-2025) is touched; `eightk` refuses the out-of-sample window.

Settings (one scan, all disclosed): 3-6m options, 5% OTM, entry at the close of the session after the
filing date (no after-the-bell look-ahead), costs = the notebook's 5% of premium each way (and 10%).

Run from massive/:   .venv/bin/python research/scan.py
Writes:              research/scan/cells.csv, research/scan/summary.csv (aggregates only);
                     per-event rows go to .massive_cache/derived/ (licensed-data derived, git-ignored)
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import eightk as K  # noqa: E402

OUT = HERE / "scan"
DERIVED = K.CACHE_DIR / "derived"
MIN_EVENTS = 20                       # in-sample top-100 events, from research/event_counts.csv
COMBOS = {                            # combined categories, written down before any results
    "combo:new_leadership": ["ceo_appointment", "cfo_appointment"],
    "combo:leadership_exit": ["ceo_departure", "cfo_departure"],
    "combo:debt_offering": ["debt_issuance", "underwriting_agreement"],
    "combo:deal_signed": ["acquisition_agreement", "merger_agreement"],
}
BUCKET = {"3-6m": K.EXPIRY_BUCKETS["3-6m"]}
OTM = 0.05
TIMING = "next_session"
POOL_PER_TICKER = 12                  # ordinary days per ticker in the shared placebo pool (half A, half B)
PLACEBO_GAP_DAYS = 30
N_FAKE = 400                          # fake tags per real tag for the luck benchmark
HORIZONS = [1, 2, 3, 5, 10, 21, 42, 63, "exp"]
STRATS = K.STRATEGIES[1:]             # the five strategies (the stock alone is reported, not tested)
CELLS = [(s, h) for s in STRATS for h in HORIZONS]


def build_pool(seed: int = 7) -> pd.DataFrame:
    """Random ordinary sessions per ticker, priced with the same timing rule as the events."""
    rng = np.random.default_rng(seed)
    sessions = K.CAL[(K.CAL >= pd.Timestamp(K.STUDY_START)) & (K.CAL <= pd.Timestamp(K.STUDY_END))]
    rows = []
    for t in K.TOP_100:
        for i, d in enumerate(sorted(rng.choice(sessions, POOL_PER_TICKER, replace=False))):
            d = pd.Timestamp(d)
            rows.append({"ticker": t, "event_date": d, "t_pre": K.session_before(d), "t_0": K.session_after(d),
                         "half": "A" if i % 2 == 0 else "B"})
    return pd.DataFrame(rows)


def wide_tables(res: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Gross P&L (key × cell), round-trip cost (key × strategy) and entry info (key)."""
    r = res[(res.entry == "post") & (res.otm == OTM) & (res.bucket == "3-6m")].copy()
    r["h"] = r["horizon"].astype(str)
    gross = r[r.horizon != 0].pivot_table(index=["ticker", "event_date"], columns="h", values=STRATS, aggfunc="first")
    gross = gross.reindex(columns=pd.MultiIndex.from_tuples([(s, str(h)) for s, h in CELLS]))
    r0 = r[r.horizon == 0].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])
    cost = pd.DataFrame({s: K.round_trip_cost(r0, s) for s in STRATS})
    info = r0[["t_0", "implied_move", "prem_CK", "prem_CU", "prem_PL", "vol_CK", "vol_CU", "vol_PL", "S_entry"]]
    return gross, cost, info


def week_ids(dates) -> np.ndarray:
    return pd.to_datetime(pd.Series(dates)).dt.to_period("W").astype(str).to_numpy()


def event_side(X: np.ndarray, clusters: np.ndarray):
    """Column means and cluster-robust standard errors (clusters = calendar weeks). NaN-aware."""
    ok = ~np.isnan(X)
    n = ok.sum(0)
    mean = np.where(n > 0, np.nansum(X, 0) / np.maximum(n, 1), np.nan)
    resid = np.where(ok, X - mean, 0.0)
    _, g = np.unique(clusters, return_inverse=True)
    G = np.zeros((g.max() + 1, X.shape[1]))
    np.add.at(G, g, resid)
    n_g = len(np.unique(g))
    se = np.sqrt((G ** 2).sum(0) * n_g / max(n_g - 1, 1)) / np.maximum(n, 1)
    return mean, se, n


def placebo_side(P: np.ndarray, w: np.ndarray):
    """Weighted column means and standard errors (effective sample size). NaN-aware."""
    ok = ~np.isnan(P)
    W = np.where(ok, w[:, None], 0.0)
    sw = W.sum(0)
    mean = np.where(sw > 0, np.nansum(np.where(ok, P, 0) * W, 0) / np.where(sw > 0, sw, 1), np.nan)
    var = (np.where(ok, (P - mean) ** 2, 0) * W).sum(0) / np.where(sw > 0, sw, 1)
    n_eff = sw ** 2 / np.maximum((W ** 2).sum(0), 1e-12)
    return mean, np.sqrt(var / np.maximum(n_eff, 1)), n_eff


def placebo_weights(pool_keys: pd.DataFrame, ev: pd.DataFrame, exclude: bool = True) -> np.ndarray:
    """Weight pool rows so the placebo has the tag's ticker mix; drop rows near the tag's own events."""
    share = ev.ticker.value_counts(normalize=True)
    w = np.array(pool_keys.ticker.map(share).fillna(0.0), dtype=float)
    if exclude:
        ev_days = ev.groupby("ticker")["event_date"].apply(lambda s: s.to_numpy(dtype="datetime64[D]"))
        for i, (t, d) in enumerate(zip(pool_keys.ticker, pool_keys.event_date)):
            if w[i] and np.any(np.abs((ev_days[t] - np.datetime64(d, "D")).astype(int)) <= PLACEBO_GAP_DAYS):
                w[i] = 0.0
    cnt = pd.Series(w > 0).groupby(pool_keys.ticker.to_numpy()).transform("sum").to_numpy()
    w = np.where(w > 0, w / np.maximum(cnt, 1), 0.0)
    return w / w.sum() if w.sum() else w


def main():
    OUT.mkdir(exist_ok=True)
    DERIVED.mkdir(exist_ok=True)
    counts = pd.read_csv(HERE / "event_counts.csv", index_col=0)
    tags = {t: [t] for t in counts.index[counts.in_sample_events >= MIN_EVENTS]}
    tags.update(COMBOS)
    earnings_family = set(counts.index[counts.primary_category == "financial_results"])

    print(f"building events for {len(tags)} categories ({TIMING} entry)…", flush=True)
    events = {name: K.build_events(tt, K.STUDY_START, K.STUDY_END, timing=TIMING) for name, tt in tags.items()}
    pool = build_pool()
    keys = {(r.ticker, r.t_pre, r.t_0, r.event_date) for ev in events.values() for r in ev.itertuples()}
    keys |= {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in pool.itertuples()}
    print(f"{sum(map(len, events.values())):,} category-events, {len(pool)} pool days, {len(keys):,} unique keys to price",
          flush=True)

    t0 = time.time()
    priced, drops = K.price_many(sorted(keys, key=lambda k: (k[0], k[3])), BUCKET, [OTM], workers=16, label="scan")
    res = K.evaluate([pe for v in priced.values() for pe in v], [OTM])
    res.to_pickle(DERIVED / "scan_results.pkl")
    print(f"priced in {time.time() - t0:.0f}s; drops: {drops.reason.str.split(':').str[0].value_counts().to_dict()}",
          flush=True)

    gross, cost, info = wide_tables(res)
    net = gross.copy()
    for s in STRATS:
        net[s] = gross[s].sub(cost[s].reindex(gross.index), axis=0)
    pool_idx = pd.MultiIndex.from_frame(pool[["ticker", "event_date"]]).intersection(gross.index)
    pool_keys = pool.set_index(["ticker", "event_date"]).loc[pool_idx].reset_index()
    P_all, P_net = gross.loc[pool_idx].to_numpy(), net.loc[pool_idx].to_numpy()
    half_A, half_B = (pool_keys.half == "A").to_numpy(), (pool_keys.half == "B").to_numpy()
    rng = np.random.default_rng(11)

    cell_rows, summary_rows = [], []
    for name, ev in events.items():
        idx = pd.MultiIndex.from_frame(ev[["ticker", "event_date"]]).intersection(gross.index)
        n_priced = len(idx)
        if n_priced < 10:
            continue
        evp = ev.set_index(["ticker", "event_date"]).loc[idx].reset_index()
        X, Xn = gross.loc[idx].to_numpy(), net.loc[idx].to_numpy()
        wk = week_ids(evp.t_0)
        w = placebo_weights(pool_keys, evp)
        m_e, se_e, n_e = event_side(X, wk)
        m_p, se_p, _ = placebo_side(P_all, w)
        gap, se_gap = m_e - m_p, np.sqrt(se_e ** 2 + se_p ** 2)
        t_gap = gap / se_gap
        mn_e, sen_e, _ = event_side(Xn, wk)
        mn_p, _, _ = placebo_side(P_net, w)
        X2 = X.copy()                                         # costs doubled: 10% of premium each way
        for j, (s, h) in enumerate(CELLS):
            X2[:, j] = X[:, j] - 2 * cost[s].reindex(idx).to_numpy()
        m2, _, _ = event_side(X2, wk)

        # Luck benchmark: fake tags of the same size and ticker mix, drawn from pool half B, compared with half A.
        wA = placebo_weights(pool_keys[half_A].reset_index(drop=True), evp, exclude=False)
        wB = placebo_weights(pool_keys[half_B].reset_index(drop=True), evp, exclude=False)
        PA, PB = P_all[half_A], P_all[half_B]
        mA, seA, _ = placebo_side(PA, wA)
        wkB = week_ids(pool_keys[half_B].t_0)
        fake_best = np.empty(N_FAKE)
        for b in range(N_FAKE):
            pick = rng.choice(len(PB), size=n_priced, replace=True, p=wB)
            mf, sef, _ = event_side(PB[pick], wkB[pick])
            fake_best[b] = np.nanmax(np.abs((mf - mA) / np.sqrt(sef ** 2 + seA ** 2)))
        best_j = int(np.nanargmax(np.abs(t_gap)))
        best_abs_t = float(np.abs(t_gap[best_j]))

        for j, (s, h) in enumerate(CELLS):
            cell_rows.append({"category": name, "strategy": s, "horizon": h, "n": int(n_e[j]),
                              "event_gross": m_e[j], "placebo_gross": m_p[j], "gap": gap[j], "t_gap": t_gap[j],
                              "event_net": mn_e[j], "t_event_net": mn_e[j] / sen_e[j] if sen_e[j] else np.nan,
                              "event_net_2x_cost": m2[j], "placebo_net": mn_p[j]})
        summary_rows.append({
            "category": name, "earnings_family": any(t in earnings_family for t in tags[name]),
            "events": len(ev), "priced": n_priced, "tickers": evp.ticker.nunique(), "weeks": len(set(wk)),
            "best_cell": f"{CELLS[best_j][0]} @ {CELLS[best_j][1]}", "best_gap": gap[best_j], "best_t": t_gap[best_j],
            "luck_p": float((fake_best >= best_abs_t).mean()),
            "fake_best_t_median": float(np.median(fake_best)), "fake_best_t_95": float(np.percentile(fake_best, 95)),
            "cells_abs_t_over_2": int(np.nansum(np.abs(t_gap) > 2)),
            "median_implied_move": float(info.loc[idx, "implied_move"].median()),
        })
        print(f"  {name:42s} n={n_priced:4d}  best {summary_rows[-1]['best_cell']:28s} t={t_gap[best_j]:+.2f}  "
              f"luck p={summary_rows[-1]['luck_p']:.2f}", flush=True)

    cells = pd.DataFrame(cell_rows)
    summary = pd.DataFrame(summary_rows).sort_values("luck_p")
    cells.to_csv(OUT / "cells.csv", index=False)
    summary.to_csv(OUT / "summary.csv", index=False)
    drops.to_csv(DERIVED / "scan_drops.csv", index=False)
    print(f"\n{len(summary)} categories × {len(CELLS)} cells = {len(cells):,} tests. Wrote {OUT}/summary.csv and cells.csv")


if __name__ == "__main__":
    main()
