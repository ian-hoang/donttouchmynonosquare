"""THE out-of-sample run of the frozen rule (hypotheses/FINAL_RULE.md). It runs once.

research/OOS_LOCK.json records the rule file and the code fingerprints taken at the freeze. This
script refuses to run if the lock says it already ran, or if any fingerprinted file has changed.

Run from massive/:   .venv/bin/python research/oos_deal.py
Writes:              research/oos/results.md (aggregates only) and the run record in OOS_LOCK.json
"""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from costs import last_quote  # noqa: E402
from ideas2 import OTM, all_filings, company_days, pick_peers  # noqa: E402
from scan import event_side  # noqa: E402

LOCK = HERE / "OOS_LOCK.json"
FINGERPRINTED = ["eightk.py", "research/oos_deal.py", "research/costs.py", "research/ideas2.py", "research/scan.py",
                 "hypotheses/FINAL_RULE.md"]
DEALS = ["acquisition_agreement", "merger_agreement"]
LEG = f"C_U{OTM}"
H = ["1", "2", "3", "5", "10", "21", "42", "63", "exp"]
PRIMARY = "10"


def sha(rel: str) -> str:
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def one_per_deal(ev: pd.DataFrame) -> pd.DataFrame:
    """Same logic as in-sample (round3.py / sharpe_deal.py): count a filing only if > 60 days after the last counted one."""
    ev = ev.sort_values(["ticker", "event_date"])
    keep, last = [], {}
    for i, r in ev.iterrows():
        if r.ticker not in last or (r.event_date - last[r.ticker]).days > 60:
            keep.append(i)
            last[r.ticker] = r.event_date
    return ev.loc[keep]


def filings_near(start: str, end: str) -> pd.DataFrame:
    """Every tagged 8-K by the top 100 between start and end (to pick quiet peers)."""
    frames = []
    for t in K.TOP_100:
        for q in ([t, t.replace(".", "/")] if "." in t else [t]):
            rows = K.api_get_all("/stocks/filings/8-K/vX/disclosures", {
                "tickers": q, "filing_date.gte": start, "filing_date.lte": end, "limit": 1000, "sort": "filing_date.asc"})
            if rows:
                frames.append(pd.DataFrame(rows).assign(ticker=t))
    raw = pd.concat(frames, ignore_index=True)
    raw["filing_date"] = pd.to_datetime(raw["filing_date"])
    return raw


def sold_call_tables(res: pd.DataFrame, half_spread: pd.Series):
    """Sold-call P&L net of measured costs, and the full covered call net, per $1 of stock: key × horizon."""
    r = res[(res.bucket == "3-6m") & (res.otm == OTM) & (res.entry == "post")].copy()
    r0 = r[r.horizon == 0].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])
    r = r[r.horizon != 0]
    r["h"] = r.horizon.astype(str)
    w = lambda c: r.pivot_table(index=["ticker", "event_date"], columns="h", values=c, aggfunc="first").reindex(columns=H)  # noqa: E731
    cost = (2 * half_spread.reindex(r0.index) / r0.S_entry)
    sold = (w("covered_call") - w("stock")).sub(cost.reindex(w("stock").index), axis=0)
    full = w("covered_call").sub(cost.reindex(w("stock").index) + 0.0002, axis=0)
    return sold, full


def entry_half_spreads(priced: dict) -> pd.Series:
    out = {}
    for pes in priced.values():
        for pe in pes:
            q = last_quote(pe.legs[LEG].ticker, pe.t_0)
            out[(pe.ticker, pe.event_date)] = (q["ask"] - q["bid"]) / 2 if q else np.nan
    s = pd.Series(out)
    s.index = pd.MultiIndex.from_tuples(s.index, names=["ticker", "event_date"])
    return s


def vs_peers(tab, ev, peers):
    E = tab.reindex(pd.MultiIndex.from_frame(ev[["ticker", "event_date"]])).to_numpy(dtype=float)
    P = tab.reindex(pd.MultiIndex.from_frame(peers[["ticker", "event_date"]])).copy()
    P.index = peers.event_date.to_numpy()
    pm = P.groupby(level=0).mean()
    return E, E - pm.reindex(ev.event_date.to_numpy()).to_numpy()


def insample_company_usual() -> pd.DataFrame:
    """Each company's average gap over the other peers on the in-sample quiet days it served as a peer."""
    counts = pd.read_csv(HERE / "event_counts.csv", index_col=0)
    raw = all_filings()
    cd = company_days(raw, set(counts.index[counts.primary_category == "financial_results"]))
    peers = pick_peers(cd, raw)
    res = pd.read_pickle(K.CACHE_DIR / "derived" / "ideas2_results.pkl")
    q = pd.read_pickle(K.CACHE_DIR / "derived" / "entry_quotes.pkl")
    hs = q[q.leg == LEG].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])["half_spread"]
    sold, _ = sold_call_tables(res, hs)
    P = sold.reindex(pd.MultiIndex.from_frame(peers[["ticker", "event_date"]])).to_numpy(dtype=float)
    d = peers.event_date.to_numpy()
    dfP = pd.DataFrame(P)
    dfP["d"] = d
    sums, cnt = dfP.groupby("d").sum(min_count=1), dfP.groupby("d").count()
    loo = (sums.reindex(d).to_numpy() - np.nan_to_num(P)) / (cnt.reindex(d).to_numpy() - (~np.isnan(P)))
    co = pd.DataFrame(P - loo, columns=H)
    co["ticker"] = peers.ticker.to_numpy()
    return co.groupby("ticker").mean()


def main():
    lock = json.loads(LOCK.read_text())
    if lock.get("run_at"):
        raise SystemExit(f"The out-of-sample test already ran at {lock['run_at']}. It runs once.")
    changed = [f for f in FINGERPRINTED if sha(f) != lock["code_sha256"].get(f)]
    if changed:
        raise SystemExit(f"Files changed since the freeze: {changed}. Not running.")

    # Events: the one-per-deal sequence runs continuously from 2024 (as in-sample), then keep 2026.
    ev_all = K.build_events(DEALS, K.STUDY_START, K.OOS_END, timing="next_session", allow_oos=True)
    ev = one_per_deal(ev_all)
    ev = ev[(ev.event_date >= pd.Timestamp(K.OOS_START)) & (ev.event_date <= pd.Timestamp(K.OOS_END))].reset_index(drop=True)
    raw = filings_near("2025-12-15", "2026-09-15")
    peers = pick_peers(ev, raw)
    keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in ev.itertuples()} |
                  {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in peers.itertuples()}, key=lambda k: (k[0], k[3]))
    priced, drops = K.price_many(keys, {"3-6m": K.EXPIRY_BUCKETS["3-6m"]}, [OTM], workers=16, label="OOS")
    res = K.evaluate([pe for v in priced.values() for pe in v], [OTM])
    hs = entry_half_spreads(priced)
    sold, full = sold_call_tables(res, hs)
    E, D = vs_peers(sold, ev, peers)
    Ef, Df = vs_peers(full, ev, peers)
    usual = insample_company_usual()
    DD = D - usual.reindex(ev.ticker.to_numpy()).to_numpy()
    cl = ev.ticker.to_numpy()

    def row(lab, X):
        m, se, n = event_side(X, cl)
        cells = [("" if (np.isnan(a) or k == 0) else f"{a * 100:+.2f}% ({a / s:+.1f}, n={k})") for a, s, k in zip(m, se, n)]
        return f"| {lab} | " + " | ".join(cells) + " |"

    j = H.index(PRIMARY)
    x, g = E[:, j], D[:, j]
    ok = ~np.isnan(x)
    m_abs, m_gap = np.nanmean(x), np.nanmean(g)
    passed = bool(m_abs > 0 and m_gap > 0)
    lines = ["# Out-of-sample result: the frozen rule on 2026-01-01..2026-08-31 (run once)\n",
             f"Run at {datetime.now().isoformat(timespec='seconds')}. Rule: `hypotheses/FINAL_RULE.md`.\n",
             f"Deal-signing filings in the window (one per deal): {len(ev)} from {ev.ticker.nunique()} companies: "
             + ", ".join(f"{r.ticker} {r.filing_date.date()}" for r in ev.itertuples()) + ".",
             f"Trades with valid prices at the {PRIMARY}-session exit: {int(ok.sum())}. Peers: {len(peers)} rows on {peers.event_date.nunique()} dates.\n",
             f"## Primary (h={PRIMARY}): **{'PASS' if passed else 'FAIL'}** (rule: both positive)\n",
             f"- Sold call, net of measured costs: **{m_abs * 100:+.2f}%** per trade; winners {np.mean(x[ok] > 0):.0%}; "
             f"per-trade Sharpe {m_abs / np.nanstd(x, ddof=1):+.2f}",
             f"- Gap over quiet same-day peers: **{m_gap * 100:+.2f}%**",
             f"- Gap after removing each company's usual (in-sample) gap: {np.nanmean(DD[:, j]) * 100:+.2f}%\n",
             "## Every horizon that has resolved (mean, t clustered by company, n)\n",
             "| | " + " | ".join(f"h={h}" for h in H) + " |", "|---|" + "---|" * len(H),
             row("sold call, P&L net", E), row("sold call, vs peers", D), row("sold call, vs peers and company's usual", DD),
             row("full covered call (stock + call), net", Ef), row("full covered call, vs peers", Df),
             "\n## Per trade at h=10\n", "| company | filing date | sold call net | vs peers |", "|---|---|---|---|"]
    for i, r in ev.iterrows():
        lines.append(f"| {r.ticker} | {r.filing_date.date()} | {'' if np.isnan(E[i, j]) else f'{E[i, j] * 100:+.2f}%'} | "
                     f"{'' if np.isnan(D[i, j]) else f'{D[i, j] * 100:+.2f}%'} |")
    text = "\n".join(lines)
    (HERE / "oos").mkdir(exist_ok=True)
    (HERE / "oos" / "results.md").write_text(text + "\n")
    lock.update({"run_at": datetime.now().isoformat(timespec="seconds"), "passed": passed,
                 "primary": {"horizon": PRIMARY, "sold_call_net_mean": m_abs, "gap_vs_peers_mean": m_gap, "n": int(ok.sum())}})
    LOCK.write_text(json.dumps(lock, indent=2))
    print(text)


if __name__ == "__main__":
    main()
