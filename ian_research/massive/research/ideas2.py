"""Round-2 ideas (hypotheses/BRAINSTORM2.md): contrasts between groups of 8-Ks, each event measured
against quiet same-day peers. In-sample (2024-2025) only.

Event unit: one company-day (all 8-K tags a top-100 company filed that day). Peers: for every filing
date, 6 top-100 companies with no 8-K of any kind within ±5 days, entered and exited on the same
sessions. Every metric is "event minus the mean of that day's peers", so whatever the whole market
did cancels. t-stats are clustered by company.

Run from massive/:   .venv/bin/python research/ideas2.py
Writes:              research/ideas2/results.md (aggregates only)
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import eightk as K  # noqa: E402
from scan import event_side  # noqa: E402

OUT = HERE / "ideas2"
H = [1, 2, 3, 5, 10, 21, 42, 63, "exp"]
HS = [str(h) for h in H]
OTM = 0.05
N_PEERS, QUIET_DAYS, INTENSITY_DAYS = 6, 5, 60

RESOLVED = ["acquisition_completion", "merger_completion", "divestiture_completion", "spinoff_completion",
            "deal_termination", "settlement_agreement", "regulatory_decision"]
CREATED = ["ceo_departure", "cfo_departure", "strategic_initiative", "restructuring_plan", "workforce_reduction",
           "business_line_exit", "regulatory_investigation", "material_litigation", "cybersecurity_incident",
           "asset_impairment", "goodwill_impairment"]
DEPARTURES = ["ceo_departure", "cfo_departure", "executive_officer_departure"]
DEALS = ["acquisition_agreement", "merger_agreement"]
DEBT = ["debt_issuance", "underwriting_agreement"]
SCHEDULED = ["quarterly_earnings", "annual_earnings", "preliminary_results", "guidance_issuance_or_update",
             "annual_meeting_results", "shareholder_proposal_outcome", "dividend_declaration", "investor_presentation"]
FINANCIALS = set("AIG AXP BAC BK BLK BRK.B C COF GS JPM MET MS SCHW USB WFC".split())

SUDDEN_RE = re.compile(r"effective immediately|immediate effect|terminat|for cause|mutual|no longer serv|"
                       r"cease[ds]? (?:to )?serv|good reason", re.I)
RETIRE_RE = re.compile(r"retir", re.I)
STOCK_RE = re.compile(r"exchange ratio|shares of [^.]{0,80}common stock|stock consideration|all-stock|in stock|"
                      r"newly issued shares|shares of (?:the )?(?:company|acquirer|parent)", re.I)
CASH_RE = re.compile(r"in cash|cash consideration|all-cash|per share in cash", re.I)
DATE_RE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)"
                     r"\s+(\d{1,2}),\s+(\d{4})")


def all_filings() -> pd.DataFrame:
    """Every tagged 8-K disclosure for the top 100, 2022-2025 (same queries as count_events.py, so cached)."""
    frames = []
    for t in K.TOP_100:
        for q in ([t, t.replace(".", "/")] if "." in t else [t]):
            rows = K.api_get_all("/stocks/filings/8-K/vX/disclosures", {
                "tickers": q, "filing_date.gte": "2022-01-01", "filing_date.lte": "2025-12-31",
                "limit": 1000, "sort": "filing_date.asc"})
            if rows:
                frames.append(pd.DataFrame(rows).assign(ticker=t))
    raw = pd.concat(frames, ignore_index=True)
    raw["filing_date"] = pd.to_datetime(raw["filing_date"])
    return raw.drop_duplicates(["accession_number", "tertiary_category", "supporting_text"])


def first_text_date(text: str):
    m = DATE_RE.search(text or "")
    if not m:
        return pd.NaT
    try:
        return pd.Timestamp(f"{m.group(1)} {m.group(2)} {m.group(3)}")
    except ValueError:
        return pd.NaT


def company_days(raw: pd.DataFrame, earn_tags: set) -> pd.DataFrame:
    ins = raw[(raw.filing_date >= K.STUDY_START) & (raw.filing_date <= K.STUDY_END)]
    cd = (ins.groupby(["ticker", "filing_date"])
             .agg(tags=("tertiary_category", lambda s: frozenset(s)),
                  text=("supporting_text", lambda s: " || ".join(s.astype(str))),
                  n_filings=("accession_number", "nunique"))
             .reset_index())
    fs = cd.filing_date.map(K.session_on_or_after)
    cd["t_pre"], cd["t_0"], cd["event_date"] = fs.map(K.session_before), fs.map(K.session_after), cd.filing_date
    cd["earnings"] = cd.tags.map(lambda s: bool(s & earn_tags))
    # Intensity: distinct non-earnings filings by the same company in the prior 60 days.
    ne = raw[~raw.tertiary_category.isin(earn_tags)].drop_duplicates(["ticker", "accession_number"])
    by_t = ne.groupby("ticker")["filing_date"].apply(lambda s: np.sort(s.to_numpy(dtype="datetime64[D]")))
    def intensity(t, d):
        a, d = by_t.get(t, np.array([], dtype="datetime64[D]")), np.datetime64(d, "D")
        return int(((a < d) & (a >= d - np.timedelta64(INTENSITY_DAYS, "D"))).sum())
    cd["intensity"] = [intensity(t, d) for t, d in zip(cd.ticker, cd.filing_date)]
    # Filing lag from the first date in the excerpt (business days, weekends only).
    td = cd.text.map(first_text_date)
    ok = td.notna() & (td <= cd.filing_date)
    cd["lag"] = np.nan
    cd.loc[ok, "lag"] = np.busday_count(td[ok].to_numpy(dtype="datetime64[D]"), cd.loc[ok, "filing_date"].to_numpy(dtype="datetime64[D]"))
    cd["weekday"] = cd.filing_date.dt.weekday
    return cd


def pick_peers(cd: pd.DataFrame, raw: pd.DataFrame, seed: int = 21) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = raw.groupby("ticker")["filing_date"].apply(lambda s: np.unique(s.to_numpy(dtype="datetime64[D]"))).to_dict()
    rows = []
    for d, g in cd.groupby("filing_date"):
        d64 = np.datetime64(d, "D")
        quiet = [t for t in K.TOP_100 if t not in days or np.all(np.abs((days[t] - d64).astype(int)) > QUIET_DAYS)]
        for t in rng.choice(quiet, min(N_PEERS, len(quiet)), replace=False):
            rows.append({"ticker": t, "event_date": d, "t_pre": g.t_pre.iloc[0], "t_0": g.t_0.iloc[0]})
    return pd.DataFrame(rows)


def metric_tables(res: pd.DataFrame, bucket: str = "3-6m") -> dict[str, pd.DataFrame]:
    r = res[(res.bucket == bucket) & (res.otm == OTM)].copy()
    post = r[(r.entry == "post") & (r.horizon != 0)].copy()
    post["h"] = post.horizon.astype(str)
    post["bought_put"] = post.protective_put - post.stock
    post["ratio"] = post.realized.abs() / post.implied_scaled
    tabs = {m: post.pivot_table(index=["ticker", "event_date"], columns="h", values=m, aggfunc="first").reindex(columns=HS)
            for m in ["stock", "long_call", "protective_put", "cash_secured_put", "bought_put", "ratio"]}
    pre0 = r[(r.entry == "pre") & (r.horizon == 0)].drop_duplicates(["ticker", "event_date"]).set_index(["ticker", "event_date"])
    tabs["_pre0"] = pre0[["realized", "implied_scaled", "implied_move"]]
    return tabs


def vs_peers(tab: pd.DataFrame, ev: pd.DataFrame, peers: pd.DataFrame) -> pd.DataFrame:
    pm = tab.reindex(pd.MultiIndex.from_frame(peers[["ticker", "event_date"]])).groupby(level="event_date").mean()
    E = tab.reindex(pd.MultiIndex.from_frame(ev[["ticker", "event_date"]])).to_numpy()
    return pd.DataFrame(E - pm.reindex(ev.event_date.to_numpy()).to_numpy(), columns=tab.columns, index=ev.index)


def summarize(X: pd.DataFrame, clusters) -> pd.DataFrame:
    m, se, n = event_side(X.to_numpy(dtype=float), np.asarray(clusters))
    return pd.DataFrame({"mean": m, "t": m / se, "n": n}, index=X.columns)


def contrast_table(XA, cA, XB, cB, la, lb, pct=True) -> str:
    a, b = summarize(XA, cA), summarize(XB, cB)
    _, seA, _ = event_side(XA.to_numpy(dtype=float), np.asarray(cA))
    _, seB, _ = event_side(XB.to_numpy(dtype=float), np.asarray(cB))
    d = a["mean"] - b["mean"]
    t = d / np.sqrt(seA ** 2 + seB ** 2)
    f = (lambda v: f"{v * 100:+.2f}%") if pct else (lambda v: f"{v:+.3f}")
    lines = [f"| horizon | {la} (n) | {lb} (n) | difference | t |", "|---|---|---|---|---|"]
    for h in HS:
        lines.append(f"| {h} | {f(a.loc[h, 'mean'])} ({int(a.loc[h, 'n'])}) | {f(b.loc[h, 'mean'])} ({int(b.loc[h, 'n'])}) | "
                     f"{f(d[h])} | {t[h]:+.1f} |")
    return "\n".join(lines)


def single_table(X, c, label, pct=True) -> str:
    s = summarize(X, c)
    f = (lambda v: f"{v * 100:+.2f}%") if pct else (lambda v: f"{v:+.3f}")
    lines = [f"| horizon | {label} | t | n |", "|---|---|---|---|"]
    lines += [f"| {h} | {f(s.loc[h, 'mean'])} | {s.loc[h, 't']:+.1f} | {int(s.loc[h, 'n'])} |" for h in HS]
    return "\n".join(lines)


def has_any(tags, wanted):
    return bool(tags & set(wanted))


def main():
    OUT.mkdir(exist_ok=True)
    counts = pd.read_csv(HERE / "event_counts.csv", index_col=0)
    earn_tags = set(counts.index[counts.primary_category == "financial_results"])
    raw = all_filings()
    cd = company_days(raw, earn_tags)
    peers = pick_peers(cd, raw)
    keys = sorted({(r.ticker, r.t_pre, r.t_0, r.event_date) for r in cd.itertuples()} |
                  {(r.ticker, r.t_pre, r.t_0, r.event_date) for r in peers.itertuples()}, key=lambda k: (k[0], k[3]))
    print(f"{len(cd):,} company-days with an 8-K (2024-2025), {cd.filing_date.nunique()} dates, "
          f"{len(peers):,} peer rows; {len(keys):,} keys to price", flush=True)
    priced, drops = K.price_many(keys, {"3-6m": K.EXPIRY_BUCKETS["3-6m"]}, [OTM], workers=16, label="ideas2")
    res = K.evaluate([pe for v in priced.values() for pe in v], [OTM])
    res.to_pickle(K.CACHE_DIR / "derived" / "ideas2_results.pkl")
    T = metric_tables(res)
    V = {m: vs_peers(T[m], cd, peers) for m in ["stock", "long_call", "protective_put", "cash_secured_put", "bought_put", "ratio"]}

    # Filing-window surprise z (event move minus peers' move, in units of the event's own implied move).
    pre0 = T["_pre0"]
    ev_pre = pre0.reindex(pd.MultiIndex.from_frame(cd[["ticker", "event_date"]]))
    peer_r0 = pre0["realized"].reindex(pd.MultiIndex.from_frame(peers[["ticker", "event_date"]])).groupby(level="event_date").mean()
    cd["z"] = (ev_pre["realized"].to_numpy() - peer_r0.reindex(cd.event_date.to_numpy()).to_numpy()) / ev_pre["implied_scaled"].to_numpy()
    cd["implied_pre"] = ev_pre["implied_move"].to_numpy()
    cl = cd.ticker.to_numpy()
    sec = []

    def add(title, body):
        sec.append(f"## {title}\n\n{body}\n")
        print(f"\n## {title}\n{body}", flush=True)

    # G · resolved vs created
    gA = cd.tags.map(lambda s: has_any(s, RESOLVED)) & ~cd.tags.map(lambda s: has_any(s, CREATED))
    gB = cd.tags.map(lambda s: has_any(s, CREATED)) & ~cd.tags.map(lambda s: has_any(s, RESOLVED))
    for m, lab in [("cash_secured_put", "Cash-secured put vs peers"), ("bought_put", "Bought put (protective put minus stock) vs peers"),
                   ("ratio", "|realized| ÷ implied vs peers")]:
        add(f"G · Resolved vs created · {lab}",
            contrast_table(V[m][gA], cl[gA], V[m][gB], cl[gB], "RESOLVED", "CREATED", pct=(m != "ratio")))

    # I · drift after a filing-window surprise (non-earnings company-days)
    ne = ~cd.earnings & cd.z.notna()
    big = ne & (cd.z.abs() > 1)
    signed = V["stock"].mul(np.sign(cd.z), axis=0)
    add("I · Signed drift after a filing-window surprise (|z| > 1, non-earnings), stock vs peers × sign(z)",
        single_table(signed[big], cl[big], "signed drift") +
        f"\n\nShare of non-earnings company-days with |z| > 1: {big.sum() / ne.sum():.0%} ({big.sum()} of {ne.sum()}).")
    for side, mask, m, lab in [("positive", big & (cd.z > 0), "long_call", "Long call vs peers"),
                               ("negative", big & (cd.z < 0), "bought_put", "Bought put vs peers")]:
        add(f"I · After a {side} surprise · {lab}", single_table(V[m][mask], cl[mask], lab))

    # J · Friday vs other days
    fri, rest = big & (cd.weekday == 4), big & (cd.weekday < 4)
    add("J · Signed drift: Friday filings vs Monday-Thursday filings",
        contrast_table(signed[fri], cl[fri], signed[rest], cl[rest], "Friday", "Mon-Thu"))

    # K · turmoil
    q80 = cd.loc[ne, "intensity"].quantile(0.8)
    busy, calm = ne & (cd.intensity > q80), ne & (cd.intensity <= q80)
    for m, lab in [("ratio", "|realized| ÷ implied vs peers"), ("bought_put", "Bought put vs peers")]:
        add(f"K · Busy (> {q80:.0f} non-earnings filings in prior 60 days) vs others · {lab}",
            contrast_table(V[m][busy], cl[busy], V[m][calm], cl[calm], "busy", "others", pct=(m != "ratio")))

    # L · sudden vs planned departures
    dep = cd.tags.map(lambda s: has_any(s, DEPARTURES))
    retire = cd.text.str.contains(RETIRE_RE)
    sudden = dep & cd.text.str.contains(SUDDEN_RE) & ~retire
    planned = dep & retire
    for m, lab in [("stock", "Stock vs peers"), ("bought_put", "Bought put vs peers")]:
        add(f"L · Sudden vs planned departures · {lab}",
            contrast_table(V[m][sudden], cl[sudden], V[m][planned], cl[planned], "SUDDEN", "PLANNED"))

    # M · stock vs cash deals
    deal = cd.tags.map(lambda s: has_any(s, DEALS))
    stock_deal = deal & cd.text.str.contains(STOCK_RE)
    cash_deal = deal & ~cd.text.str.contains(STOCK_RE) & cd.text.str.contains(CASH_RE)
    add("M · Deal signed: stock/mixed vs cash-only consideration · Stock vs peers",
        contrast_table(V["stock"][stock_deal], cl[stock_deal], V["stock"][cash_deal], cl[cash_deal], "STOCK/MIXED", "CASH") +
        f"\n\nUnclassified deal company-days: {int((deal & ~stock_deal & ~cash_deal).sum())} of {int(deal.sum())}. "
        f"STOCK/MIXED tickers: {', '.join(sorted(cd.loc[stock_deal, 'ticker'].unique()))}. "
        f"CASH tickers: {', '.join(sorted(cd.loc[cash_deal, 'ticker'].unique()))}.")

    # N · debt: non-financials vs financials
    debt = cd.tags.map(lambda s: has_any(s, DEBT))
    fin = cd.ticker.isin(FINANCIALS)
    add("N · Debt offerings: non-financial vs financial issuers · Cash-secured put vs peers",
        contrast_table(V["cash_secured_put"][debt & ~fin], cl[debt & ~fin], V["cash_secured_put"][debt & fin], cl[debt & fin],
                       "non-financial", "financial"))

    # E2 · fresh vs stale
    fresh, stale = ne & (cd.lag <= 1), ne & (cd.lag >= 2)
    absz = pd.DataFrame({h: cd.z.abs() for h in ["|z|"]})
    a, b = absz[fresh], absz[stale]
    add("E2 · Fresh vs stale filings (non-earnings)",
        f"Mean |z| (filing-window surprise, in implied-move units): FRESH {a['|z|'].mean():.2f} (n={len(a)}), "
        f"STALE {b['|z|'].mean():.2f} (n={len(b)}); no parsable date: {int((ne & cd.lag.isna()).sum())}.\n\n" +
        contrast_table(signed[fresh & big], cl[fresh & big], signed[stale & big], cl[stale & big], "FRESH signed drift", "STALE signed drift"))
    add("E2 · Deal lead split: fresh vs stale deal filings · Stock vs peers",
        contrast_table(V["stock"][deal & (cd.lag <= 1)], cl[deal & (cd.lag <= 1)], V["stock"][deal & (cd.lag >= 2)], cl[deal & (cd.lag >= 2)],
                       "FRESH", "STALE"))

    # H · was it priced in?
    pool = pd.read_pickle(K.CACHE_DIR / "derived" / "scan_results.pkl")
    norm = (pool[(pool.entry == "pre") & (pool.horizon == 0) & (pool.bucket == "3-6m")]
            .drop_duplicates(["ticker", "event_date"]).groupby("ticker")["implied_move"].median())
    cd["iv_elev"] = cd.implied_pre / cd.ticker.map(norm)
    sched = cd.tags.map(lambda s: has_any(s, SCHEDULED))
    rows = []
    for lab, mask in [("scheduled", sched), ("unscheduled", ~sched)]:
        x = cd.loc[mask & cd.iv_elev.notna(), "iv_elev"]
        zz = cd.loc[mask & cd.z.notna(), "z"].abs()
        rows.append(f"| {lab} | {x.median():.3f} | {(x > 1).mean():.0%} | {zz.mean():.2f} | {len(x)} |")
    add("H · Was it priced in? 3-6m implied move on t_pre ÷ the company's typical level",
        "| filings | median ratio | share above typical | mean abs surprise z | n |\n|---|---|---|---|---|\n" + "\n".join(rows) +
        "\n\n(The company's typical level is the median over the scan's 12 random pool days per ticker.)")

    (OUT / "results.md").write_text("# Round-2 ideas: results (in-sample 2024-2025, vs quiet same-day peers)\n\n" + "\n".join(sec))
    print(f"\nWrote {OUT / 'results.md'}")


if __name__ == "__main__":
    main()
