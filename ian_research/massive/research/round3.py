"""Round 3 (hypotheses/BRAINSTORM3.md): profits the filing itself causes. In-sample 2024-2025 only.

S          sell premium (cash-secured put, covered call) into a filing-driven option-price spike.
F-overlay  deal signed: the options a holder adds (sold call; collar = bought put + sold call).

"Because of the filing" = beats quiet same-day peers AND the company's usual result against peers
(its leave-one-out gap on the quiet days it served as a peer). Costs measured from quotes.

Run from massive/:   .venv/bin/python research/round3.py
Writes:              research/round3/results.md (aggregates only)
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
from profit_search import net_tables  # noqa: E402
from scan import event_side  # noqa: E402

OUT = HERE / "round3"
H = [str(h) for h in [1, 2, 3, 5, 10, 21, 42, 63, "exp"]]
DEALS = ["acquisition_agreement", "merger_agreement"]


def kidx(df):
    return pd.MultiIndex.from_frame(df[["ticker", "event_date"]])


def compare(tab: pd.DataFrame, ev: pd.DataFrame, peers: pd.DataFrame):
    """Event values, gap over same-day peers, and gap over (peers + the company's usual gap)."""
    E = tab.reindex(kidx(ev)).to_numpy(dtype=float)
    P = tab.reindex(kidx(peers)).to_numpy(dtype=float)
    d = peers.event_date.to_numpy()
    dfP = pd.DataFrame(P)
    dfP["d"] = d
    sums, cnt = dfP.groupby("d").sum(min_count=1), dfP.groupby("d").count()
    D = E - (sums / cnt).reindex(ev.event_date.to_numpy()).to_numpy()
    loo = (sums.reindex(d).to_numpy() - np.nan_to_num(P)) / (cnt.reindex(d).to_numpy() - (~np.isnan(P)))
    co = pd.DataFrame(P - loo)
    co["ticker"] = peers.ticker.to_numpy()
    usual = co.groupby("ticker").mean().reindex(ev.ticker.to_numpy()).to_numpy()
    return E, D, D - usual


def summ(X, clusters):
    m, se, n = event_side(X, np.asarray(clusters))
    return m, m / se, n


def table(rows: dict, clusters, pct=True) -> str:
    """rows: label -> matrix (events × horizons). One line per label: mean (t) at every horizon."""
    f = (lambda v: f"{v * 100:+.2f}%") if pct else (lambda v: f"{v:+.3f}")
    out = ["| | " + " | ".join(f"h={h}" for h in H) + " |", "|---|" + "---|" * len(H)]
    for lab, (X, cl) in rows.items():
        m, t, n = summ(X, cl)
        out.append(f"| {lab} (n≈{int(np.nanmax(n))}) | " + " | ".join("" if np.isnan(a) else f"{f(a)} ({b:+.1f})" for a, b in zip(m, t)) + " |")
    return "\n".join(out)


def main():
    OUT.mkdir(exist_ok=True)
    counts = pd.read_csv(HERE / "event_counts.csv", index_col=0)
    raw = all_filings()
    cd = company_days(raw, set(counts.index[counts.primary_category == "financial_results"]))
    peers = pick_peers(cd, raw)
    res = pd.read_pickle(K.CACHE_DIR / "derived" / "ideas2_results.pkl")
    quotes = pd.read_pickle(K.CACHE_DIR / "derived" / "entry_quotes.pkl")
    net = net_tables(res, quotes)
    sec = []

    # ---- S · option-price spike on the filing --------------------------------------------------
    r0 = res[(res.bucket == "3-6m") & (res.otm == OTM) & (res.horizon == 0)]
    pre = r0[r0.entry == "pre"].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])
    post = r0[r0.entry == "post"].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])
    tv_pre = 2 * np.minimum(pre.prem_CK, pre.prem_PK)
    tv_0 = 2 * np.minimum(post.prem_CK, post.prem_PK)
    spike = np.log(tv_0 / tv_pre.reindex(tv_0.index)).replace([np.inf, -np.inf], np.nan)
    sp_tab = pd.DataFrame({h: spike for h in H})
    _, sp_gap, _ = compare(sp_tab, cd, peers)
    cd["spike"] = sp_gap[:, 0]
    ne = (~cd.earnings) & cd.spike.notna()
    q80 = cd.loc[ne, "spike"].quantile(0.8)
    top, rest = (ne & (cd.spike > q80)).to_numpy(), (ne & (cd.spike <= q80)).to_numpy()
    cl = cd.ticker.to_numpy()
    lines = [f"Spike = log change in the 3-6m ATM straddle's time value from t_pre to entry, minus same-day peers'. "
             f"Top quintile (> {q80:+.3f}, i.e. time value up ≥ {np.expm1(q80):.0%} more than peers) vs the rest. "
             f"Non-earnings company-days: {int(ne.sum())}.\n"]
    for s, lab in [("cash_secured_put", "Cash-secured put"), ("covered_call", "Covered call")]:
        tab = net[s].reindex(columns=H)
        E, D, DD = compare(tab, cd, peers)
        lines += [f"**{lab}, net of measured costs**\n",
                  table({"spike group: P&L": (E[top], cl[top]), "spike group: vs peers": (D[top], cl[top]),
                         "spike group: vs peers and company's usual": (DD[top], cl[top]),
                         "others: vs peers and company's usual": (DD[rest], cl[rest])}, None) + "\n"]
    sec.append("## S · Sell into a filing-driven option-price spike\n\n" + "\n".join(lines))

    # Does the spike fade? Straddle time value at exit vs entry (repriced from cache).
    keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in cd[ne].itertuples()} |
                  {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in peers.itertuples()}, key=lambda k: (k[0], k[3]))
    priced, _ = K.price_many(keys, {"3-6m": K.EXPIRY_BUCKETS["3-6m"]}, [OTM], workers=16, label="S fade (cached)")
    fade = {}
    for k, pes in priced.items():
        for pe in pes:
            i0 = K.CAL.get_loc(pe.t_0)
            m0 = pe.marks(pe.t_0)
            S0 = pe.synthetic_spot(pe.t_0, m0)
            tv0 = 2 * np.minimum(m0["C_K"], m0["P_K"]) / S0
            row = {}
            for h in (1, 2, 3, 5, 10, 21):
                day = K.CAL[i0 + h]
                if day > pe.expiry_session or day > K.LAST_SESSION:
                    continue
                m = pe.marks(day)
                S = pe.synthetic_spot(day, m)
                row[str(h)] = np.log((2 * np.minimum(m["C_K"], m["P_K"]) / S) / tv0) if tv0 > 0 else np.nan
            fade[(pe.ticker, pe.event_date)] = row
    fade = pd.DataFrame.from_dict(fade, orient="index").reindex(columns=H)
    fade.index = pd.MultiIndex.from_tuples(fade.index, names=["ticker", "event_date"])
    _, Df, _ = compare(fade, cd, peers)
    sec.append("**Does the spike fade?** Log change in straddle time value after entry, minus peers' (negative = fades)\n\n" +
               table({"spike group": (Df[top], cl[top]), "others": (Df[rest], cl[rest])}, None, pct=False) + "\n")

    # ---- F-overlay · deal signed, options added by a holder ------------------------------------
    rr = res[(res.bucket == "3-6m") & (res.otm == OTM) & (res.entry == "post") & (res.horizon != 0)].copy()
    rr["h"] = rr.horizon.astype(str)
    wide = lambda c: rr.pivot_table(index=["ticker", "event_date"], columns="h", values=c, aggfunc="first").reindex(columns=H)  # noqa: E731
    stock, cc, col = wide("stock"), wide("covered_call"), wide("collar")
    hs = quotes.pivot_table(index=["ticker", "event_date"], columns="leg", values="half_spread", aggfunc="first")
    S0 = post["S_entry"]
    cost_cc = (2 * hs[f"C_U{OTM}"] / S0.reindex(hs.index))
    cost_col = (2 * (hs[f"C_U{OTM}"] + hs[f"P_L{OTM}"]) / S0.reindex(hs.index))
    ov_cc = (cc - stock).sub(cost_cc.reindex(cc.index), axis=0)
    ov_col = (col - stock).sub(cost_col.reindex(col.index), axis=0)

    deal_all = cd[cd.tags.map(lambda s: bool(s & set(DEALS)))].sort_values(["ticker", "event_date"])
    keep, last = [], {}
    for i, r in deal_all.iterrows():                      # first filing per company per 60 days = one per deal
        if r.ticker not in last or (r.event_date - last[r.ticker]).days > 60:
            keep.append(i)
            last[r.ticker] = r.event_date
    deals = deal_all.loc[keep]
    lines = [f"Deal-signed company-days: {len(deal_all)}; one per deal (first filing per company per 60 days): {len(deals)} "
             f"from {deals.ticker.nunique()} companies.\n"]
    for lab, tab in [("Sold call (the covered call's option part)", ov_cc), ("Collar's options (bought put + sold call)", ov_col),
                     ("Stock alone, for reference", stock)]:
        rows = {}
        for setlab, ev in [("one per deal", deals), ("all filings", deal_all)]:
            E, D, DD = compare(tab, ev, peers)
            c = ev.ticker.to_numpy()
            rows[f"{setlab}: P&L net"] = (E, c)
            rows[f"{setlab}: vs peers"] = (D, c)
            rows[f"{setlab}: vs peers and company's usual"] = (DD, c)
        lines += [f"**{lab}**\n", table(rows, None) + "\n"]
    # Stability of the collar's options at h=10 on one-per-deal: by year, leave-one-company-out.
    E, D, DD = compare(ov_col, deals, peers)
    j = H.index("10")
    y = deals.event_date.dt.year.to_numpy()
    loo = [np.nanmean(DD[deals.ticker.to_numpy() != t, j]) for t in deals.ticker.unique()]
    lines.append(f"Collar's options at h=10, one per deal, vs peers and company's usual: 2024 {np.nanmean(DD[y == 2024, j]) * 100:+.2f}% "
                 f"(n={int((y == 2024).sum())}), 2025 {np.nanmean(DD[y == 2025, j]) * 100:+.2f}% (n={int((y == 2025).sum())}); "
                 f"leave-one-company-out range {min(loo) * 100:+.2f}% .. {max(loo) * 100:+.2f}%; "
                 f"winners {np.mean(E[:, j][~np.isnan(E[:, j])] > 0):.0%} in absolute P&L.\n")
    sec.append("## F-overlay · Deal signed: the options a holder adds\n\n" + "\n".join(lines))

    text = "# Round 3 results (in-sample 2024-2025; measured costs)\n\nCells show mean (t, clustered by company).\n\n" + "\n".join(sec)
    (OUT / "results.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
