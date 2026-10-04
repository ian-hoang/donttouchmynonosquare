"""Profit search (hypotheses/PROFIT_SEARCH.md): which 8-K category × strategy × horizon makes money after
measured costs AND beats the same trade on quiet same-day peers? In-sample (2024-2025) only.

Uses the company-days and quiet peers priced by ideas2.py and the entry quotes from costs.py.
Cost per trade = 2 × measured half-spread (in $) of each option leg ÷ stock price, + 1 bp each way for
shares. Luck check: fake categories built from random quiet companies on the *same dates* as the real
events, so timing (good or bad markets) is matched exactly.

Run from massive/:   .venv/bin/python research/profit_search.py
Writes:              research/profit/summary.md, research/profit/cells.csv (aggregates only)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from ideas2 import CREATED, OTM, RESOLVED, all_filings, company_days, has_any, pick_peers  # noqa: E402
from scan import COMBOS, event_side  # noqa: E402

OUT = HERE / "profit"
H = [str(h) for h in [1, 2, 3, 5, 10, 21, 42, 63, "exp"]]
STRATS = ["long_call", "covered_call", "protective_put", "collar", "cash_secured_put"]
LEGS_USED = {"long_call": ["C_K"], "covered_call": [f"C_U{OTM}"], "protective_put": [f"P_L{OTM}"],
             "collar": [f"C_U{OTM}", f"P_L{OTM}"], "cash_secured_put": [f"P_L{OTM}"]}
OWNS_STOCK = {"covered_call", "protective_put", "collar"}
MIN_DAYS, N_FAKE = 15, 400
CELLS = [(s, h) for s in STRATS for h in H]


def net_tables(res, quotes, haircut=None):
    """Net P&L per $1 of stock: key × (strategy, horizon). Measured costs, or a flat haircut if given."""
    r = res[(res.bucket == "3-6m") & (res.otm == OTM) & (res.entry == "post")].copy()
    r0 = r[r.horizon == 0].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])
    r = r[r.horizon != 0]
    r["h"] = r.horizon.astype(str)
    hs = quotes.pivot_table(index=["ticker", "event_date"], columns="leg", values="half_spread", aggfunc="first")
    pct = (quotes.half_spread / quotes.mid).groupby(quotes.leg).median()
    marks = quotes.pivot_table(index=["ticker", "event_date"], columns="leg", values="mark", aggfunc="first")
    hs = hs.fillna(marks * pct)                                   # missing quote: median spread for that leg type
    hs = hs.reindex(r0.index)
    tabs = {}
    for s in STRATS:
        g = r.pivot_table(index=["ticker", "event_date"], columns="h", values=s, aggfunc="first").reindex(columns=H)
        if haircut is None:
            cost = sum(hs[leg] for leg in LEGS_USED[s]) * 2 / r0.S_entry
        else:
            prem = {"C_K": "prem_CK", f"C_U{OTM}": "prem_CU", f"P_L{OTM}": "prem_PL"}
            cost = sum(r0[prem[leg]].abs() for leg in LEGS_USED[s]) * 2 * haircut
        cost = cost + (0.0002 if s in OWNS_STOCK else 0.0)
        tabs[s] = g.sub(cost.reindex(g.index), axis=0)
    return pd.concat(tabs, axis=1)                                # columns (strategy, horizon)


def category_masks(cd, counts):
    tagcount = pd.Series([t for s in cd.tags for t in s]).value_counts()
    cats = {t: cd.tags.map(lambda s, t=t: t in s) for t in tagcount.index[tagcount >= MIN_DAYS]}
    for name, tt in COMBOS.items():
        cats[name] = cd.tags.map(lambda s, tt=tt: has_any(s, tt))
    cats["class:resolved"] = cd.tags.map(lambda s: has_any(s, RESOLVED))
    cats["class:created"] = cd.tags.map(lambda s: has_any(s, CREATED))
    cats["all non-earnings 8-Ks"] = ~cd.earnings
    return cats


def stats(A, D, clusters):
    """t of absolute net P&L and of the gap over peers, per cell (cluster-robust by company)."""
    ma, sa, n = event_side(A, clusters)
    md, sd, _ = event_side(D, clusters)
    return ma, ma / sa, md, md / sd, n


def main():
    OUT.mkdir(exist_ok=True)
    counts = pd.read_csv(HERE / "event_counts.csv", index_col=0)
    raw = all_filings()
    cd = company_days(raw, set(counts.index[counts.primary_category == "financial_results"]))
    peers = pick_peers(cd, raw)
    res = pd.read_pickle(K.CACHE_DIR / "derived" / "ideas2_results.pkl")
    quotes = pd.read_pickle(K.CACHE_DIR / "derived" / "entry_quotes.pkl")

    results = {}
    for label, haircut in [("measured", None), ("haircut5", 0.05)]:
        net = net_tables(res, quotes, haircut)
        cols = pd.MultiIndex.from_tuples(CELLS)
        E = net.reindex(pd.MultiIndex.from_frame(cd[["ticker", "event_date"]])).reindex(columns=cols).to_numpy()
        P = net.reindex(pd.MultiIndex.from_frame(peers[["ticker", "event_date"]])).reindex(columns=cols).to_numpy()
        pdates = peers.event_date.to_numpy()
        # Peer mean per date, and each peer's leave-one-out gap (for the fakes).
        dfP = pd.DataFrame(P)
        dfP["d"] = pdates
        sums = dfP.groupby("d").sum(min_count=1)
        cnts = dfP.groupby("d").count()
        mean_d = (sums / cnts)
        pm_for_events = mean_d.reindex(cd.event_date.to_numpy()).to_numpy()
        D_ev = E - pm_for_events
        loo = (sums.reindex(pdates).to_numpy() - np.nan_to_num(P)) / (cnts.reindex(pdates).to_numpy() - (~np.isnan(P)))
        D_peer = P - loo
        results[label] = (E, D_ev, P, D_peer, mean_d)

    E, D_ev, P, D_peer, mean_d = results["measured"]
    peer_rows_by_date = peers.groupby("event_date").indices
    pticker = peers.ticker.to_numpy()
    years = cd.event_date.dt.year.to_numpy()
    rng = np.random.default_rng(5)
    cats = category_masks(cd, counts)

    cell_rows, cat_rows = [], []
    for name, mask in cats.items():
        m = mask.to_numpy()
        n_ev = int(m.sum())
        cl = cd.ticker.to_numpy()[m]
        ma, ta, md, td, n = stats(E[m], D_ev[m], cl)
        y24 = np.nanmean(D_ev[m & (years == 2024)], 0) if (m & (years == 2024)).any() else np.full(len(CELLS), np.nan)
        y25 = np.nanmean(D_ev[m & (years == 2025)], 0) if (m & (years == 2025)).any() else np.full(len(CELLS), np.nan)
        _, ta5, _, td5, _ = stats(results["haircut5"][0][m], results["haircut5"][1][m], cl)
        score = np.fmin(ta, td)
        # Luck: same dates, random quiet companies (peer rows are contiguous per date).
        arrs = [peer_rows_by_date[d] for d in cd.event_date[mask]]
        starts, sizes = np.array([a[0] for a in arrs]), np.array([len(a) for a in arrs])
        picks = starts + (rng.random((N_FAKE, len(arrs))) * sizes).astype(int)
        fake_best = np.empty(N_FAKE)
        for b in range(N_FAKE):
            pick = picks[b]
            _, fa, _, fd, _ = stats(P[pick], D_peer[pick], pticker[pick])
            fake_best[b] = np.nanmax(np.fmin(fa, fd))
        best = int(np.nanargmax(score))
        for j, (s, h) in enumerate(CELLS):
            adj = [k for k in (j - 1, j + 1) if 0 <= k < len(CELLS) and CELLS[k][0] == s]
            passes = (ta[j] >= 2 and td[j] >= 2 and any(td[k] >= 1.5 for k in adj) and y24[j] > 0 and y25[j] > 0)
            cell_rows.append({"category": name, "strategy": s, "horizon": h, "n": int(n[j]),
                              "net_mean": ma[j], "t_net": ta[j], "vs_peers": md[j], "t_vs_peers": td[j],
                              "vs_peers_2024": y24[j], "vs_peers_2025": y25[j],
                              "t_net_haircut5": ta5[j], "t_vs_peers_haircut5": td5[j], "passes": passes})
        cat_rows.append({"category": name, "company_days": n_ev, "best_cell": f"{CELLS[best][0]} @ {CELLS[best][1]}",
                         "best_score": score[best], "luck_p": float((fake_best >= score[best]).mean()),
                         "fake_95": float(np.nanpercentile(fake_best, 95)),
                         "cells_passing": int(sum(r["passes"] for r in cell_rows[-len(CELLS):]))})
        print(f"  {name:40s} n={n_ev:4d} best {cat_rows[-1]['best_cell']:28s} min(t) {score[best]:+.2f} "
              f"luck p {cat_rows[-1]['luck_p']:.2f}  passing cells {cat_rows[-1]['cells_passing']}", flush=True)

    cells = pd.DataFrame(cell_rows)
    cats_df = pd.DataFrame(cat_rows).sort_values("luck_p")
    cells.to_csv(OUT / "cells.csv", index=False)
    cats_df.to_csv(OUT / "categories.csv", index=False)

    # Ordinary-day baseline: the same trades on quiet peers (absolute, measured costs).
    pm, pt, _ = event_side(P, pticker)
    base = pd.DataFrame({"net_mean": pm, "t": pm / pt}, index=pd.MultiIndex.from_tuples(CELLS))
    pct = lambda v: f"{v * 100:+.2f}%"  # noqa: E731
    lines = ["# Profit search results (in-sample 2024-2025; measured costs)\n",
             f"{len(cats)} categories × {len(CELLS)} cells = {len(cells):,} cells. "
             f"Cells passing all four rules: **{int(cells.passes.sum())}**.\n",
             "## Baseline: the same trades on ordinary (quiet) days, net of measured costs\n",
             "| strategy | " + " | ".join(f"h={h}" for h in H) + " |", "|---|" + "---|" * len(H)]
    for s in STRATS:
        lines.append(f"| {s} | " + " | ".join(f"{pct(base.loc[(s, h), 'net_mean'])}" for h in H) + " |")
    lines += ["\n## Categories ranked by the luck check (best cell = highest min(t_net, t_vs_peers))\n",
              "| category | company-days | best cell | min(t) | luck p | fakes' 95th pct | passing cells |", "|---|---|---|---|---|---|---|"]
    for r in cats_df.itertuples():
        lines.append(f"| {r.category} | {r.company_days} | {r.best_cell} | {r.best_score:+.2f} | {r.luck_p:.2f} | {r.fake_95:+.2f} | {r.cells_passing} |")
    lines += ["\n## Cells that pass all four rules\n"]
    ok = cells[cells.passes].sort_values("t_vs_peers", ascending=False)
    if ok.empty:
        lines.append("None.")
    else:
        lines += ["| category | strategy | h | n | net per trade (t) | vs peers (t) | 2024 / 2025 vs peers | with 5% haircut: t net / t vs peers |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in ok.itertuples():
            lines.append(f"| {r.category} | {r.strategy} | {r.horizon} | {r.n} | {pct(r.net_mean)} ({r.t_net:+.1f}) | "
                         f"{pct(r.vs_peers)} ({r.t_vs_peers:+.1f}) | {pct(r.vs_peers_2024)} / {pct(r.vs_peers_2025)} | "
                         f"{r.t_net_haircut5:+.1f} / {r.t_vs_peers_haircut5:+.1f} |")
    lines += ["\n## Most profitable cells in absolute terms (t_net), whatever the reason\n",
              "| category | strategy | h | n | net per trade (t) | vs peers (t) |", "|---|---|---|---|---|---|"]
    for r in cells.sort_values("t_net", ascending=False).head(12).itertuples():
        lines.append(f"| {r.category} | {r.strategy} | {r.horizon} | {r.n} | {pct(r.net_mean)} ({r.t_net:+.1f}) | {pct(r.vs_peers)} ({r.t_vs_peers:+.1f}) |")
    text = "\n".join(lines)
    (OUT / "summary.md").write_text(text + "\n")
    print("\n" + text)


if __name__ == "__main__":
    main()
