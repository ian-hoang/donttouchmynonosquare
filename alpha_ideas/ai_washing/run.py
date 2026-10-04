"""Step 4 — the pre-registered AI-washing test (PREREGISTRATION.md). Run ONCE, from the repo root:

    uv run python alpha_ideas/ai_washing/run.py

Inputs come from build_universe.py, fetch_sec.py and features.py (all cached under data/cache/ai_washing/).
Writes events.csv, monthly_*.csv, cumulative.png and run_output.txt in this folder.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from common import CACHE, HERE, ROOT

SEC = CACHE / "sec"
WINDOW_END, WINDOW_1M = 63, 21
JUMP_ABS, JUMP_MIN = 3, 3
G_CUT = 0.10
PRIMARY = ("2023-01-01", "2026-06-30")
PLACEBO = ("2021-07-01", "2022-11-29")
MONTHS = ("2023-02", "2026-09")
MIN_HELD = 10
COST_EVENT, BORROW_YR = 0.0040, 0.01
CORE_TECH = [(3570, 3579), (3670, 3679), (7370, 7379)]
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
         "PaymentsForCapitalImprovements"]
RND = ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"]


# =========================================================================================== loading
def load():
    # One timestamp precision everywhere (parquet round-trips can give [ms]; joins on mixed units silently miss).
    cal = pd.DatetimeIndex(pd.to_datetime(pd.read_parquet(CACHE / "calendar.parquet")["date"])).astype("datetime64[ns]")
    uni = pd.read_parquet(CACHE / "universe.parquet")
    uni["month_end"] = pd.to_datetime(uni["month_end"]).astype("datetime64[ns]")
    comp = pd.read_parquet(SEC / "companies.parquet")
    comp["sic"] = pd.to_numeric(comp["sic"], errors="coerce")
    rel = pd.read_parquet(SEC / "earnings_8k.parquet")
    feats = pd.read_parquet(CACHE / "ai_features.parquet")
    feats = feats[~feats["junk"]]  # encoded junk / empty exhibits count as "no press-release text"
    tenk = pd.read_parquet(SEC / "tenk_filings.parquet")
    tenk["filingDate"] = pd.to_datetime(tenk["filingDate"])
    px = pd.read_parquet(CACHE / "prices.parquet", columns=["date", "cik", "ticker", "ret"])
    px["date"] = pd.to_datetime(px["date"]).astype("datetime64[ns]")
    rel["accepted_et"] = pd.to_datetime(rel["accepted_et"]).astype("datetime64[ns]")
    return cal, uni, comp, rel, feats, tenk, px


def day0_of(accepted_et: pd.Series, cal: pd.DatetimeIndex) -> np.ndarray:
    """Trading-day index of day 0: the acceptance day if it is a trading day and acceptance <= 16:00 ET, else the
    next trading day."""
    d = accepted_et.dt.normalize().to_numpy()
    pos = np.searchsorted(cal.to_numpy(), d, side="left")
    is_td = (pos < len(cal)) & (cal.to_numpy()[np.minimum(pos, len(cal) - 1)] == d)
    late = (accepted_et - accepted_et.dt.normalize()) > pd.Timedelta(hours=16)
    return np.where(is_td & late.to_numpy(), pos + 1, pos)


# =========================================================================================== investment
def load_facts(cik: str) -> pd.DataFrame:
    rows = json.loads((SEC / "facts" / f"CIK{cik}.json").read_text()) if (SEC / "facts" / f"CIK{cik}.json").exists() else []
    f = pd.DataFrame(rows)
    if f.empty:
        return f
    f = f[f["start"].notna() & f["end"].notna()].copy()
    f["start"], f["end"] = pd.to_datetime(f["start"]), pd.to_datetime(f["end"])
    f["dur"] = (f["end"] - f["start"]).dt.days
    return f[(f["dur"] >= 330) & (f["dur"] <= 400)]


def annual_pair(fa: pd.DataFrame, concept: str):
    x = fa[fa["concept"] == concept]
    if x.empty:
        return None
    fy_end = x["end"].max()
    cur = x.loc[x["end"] == fy_end, "val"]
    prior = x[(x["end"] >= fy_end - pd.Timedelta(days=400)) & (x["end"] <= fy_end - pd.Timedelta(days=330))]
    if cur.empty or prior.empty:
        return None
    prior = prior.sort_values("end").iloc[-1]
    return float(cur.iloc[0]), float(prior["val"]), fy_end


def investment_growth(ev: pd.DataFrame, tenk: pd.DataFrame) -> pd.DataFrame:
    out = []
    tk_by = {c: g.sort_values(["filingDate", "accessionNumber"]) for c, g in tenk.groupby("cik")}
    for cik, g in ev.groupby("cik"):
        facts = load_facts(cik)
        tks = tk_by.get(cik)
        for i, d0 in zip(g.index, g["day0"]):
            res = {"idx": i, "tenk_acc": None, "tenk_filed": pd.NaT, "capex_cur": np.nan, "capex_prior": np.nan,
                   "rd_cur": 0.0, "rd_prior": 0.0, "g": np.nan, "fy_end": pd.NaT}
            if tks is not None and not facts.empty:
                prior_tk = tks[tks["filingDate"] < d0]
                if len(prior_tk):
                    acc, filed = prior_tk.iloc[-1][["accessionNumber", "filingDate"]]
                    res.update(tenk_acc=acc, tenk_filed=filed)
                    fa = facts[facts["accn"] == acc]
                    cap = next((p for p in (annual_pair(fa, c) for c in CAPEX) if p), None)
                    rd = next((p for p in (annual_pair(fa, c) for c in RND) if p), None)
                    if cap:
                        res.update(capex_cur=cap[0], capex_prior=cap[1], fy_end=cap[2])
                        if rd:
                            res.update(rd_cur=rd[0], rd_prior=rd[1])
                        denom = res["capex_prior"] + res["rd_prior"]
                        if denom > 0:
                            res["g"] = (res["capex_cur"] + res["rd_cur"]) / denom - 1
            out.append(res)
    return pd.DataFrame(out).set_index("idx")


# =========================================================================================== events
def build_events(cal, uni, comp, rel, feats, tenk) -> pd.DataFrame:
    rel = rel.copy()
    rel["cik"] = rel["cik"].astype(str).str.zfill(10)
    rel["accepted_et"] = pd.to_datetime(rel["accepted_et"])
    rel["i0"] = day0_of(rel["accepted_et"], cal)
    rel = rel[rel["i0"] < len(cal)]
    # Every earnings filing (with or without text) marks the firm's next announcement, for window truncation.
    all_i0 = rel.groupby("cik")["i0"].apply(lambda s: np.unique(s.to_numpy()))

    r = rel.merge(feats, left_on="accessionNumber", right_on="acc", how="inner")
    # Two text releases of one firm on the same day 0: keep the longer one (the full press release).
    r = r.sort_values(["cik", "i0", "n_words"], ascending=[True, True, False]).drop_duplicates(["cik", "i0"])
    r = r.sort_values(["cik", "accepted_et"]).reset_index(drop=True)

    # Baseline: previous up-to-4 text releases accepted within the prior 15 months; need >= 3.
    base, base_rate, base_strict, n_prior = [], [], [], []
    for _, g in r.groupby("cik", sort=False):
        t = g["accepted_et"].to_numpy()
        ai, strict = g["ai_full"].to_numpy(float), g["ai_strict"].to_numpy(float)
        rate = ai / np.maximum(g["n_words"].to_numpy(float), 1) * 1000
        for k in range(len(g)):
            lo = pd.Timestamp(t[k]) - pd.DateOffset(months=15)
            js = [j for j in range(k) if pd.Timestamp(t[j]) >= lo][-4:]
            n_prior.append(len(js))
            ok = len(js) >= 3
            base.append(ai[js].mean() if ok else np.nan)
            base_strict.append(strict[js].mean() if ok else np.nan)
            base_rate.append(rate[js].mean() if ok else np.nan)
    r["n_prior"], r["baseline"], r["baseline_strict"], r["baseline_rate"] = n_prior, base, base_strict, base_rate
    r["d_ai"] = r["ai_full"] - r["baseline"]
    r["d_ai_strict"] = r["ai_strict"] - r["baseline_strict"]
    r["rate"] = r["ai_full"] / np.maximum(r["n_words"], 1) * 1000
    r["d_rate"] = r["rate"] - r["baseline_rate"]

    r["day0"] = cal[r["i0"].to_numpy()]
    # Formation month-end: the last universe month-end strictly before day 0.
    mes = np.sort(uni["month_end"].unique())
    pos = np.searchsorted(mes, r["day0"].to_numpy(), side="left") - 1
    r["month_end"] = pd.to_datetime(np.where(pos >= 0, mes[np.maximum(pos, 0)], np.datetime64("NaT"))).astype("datetime64[ns]")
    r = r.merge(uni[["month_end", "cik", "tercile", "rank"]], on=["month_end", "cik"], how="left")
    r["in_universe"] = r["tercile"].notna()
    r = r.merge(comp[["cik", "sic"]], on="cik", how="left")
    r["sic2"] = (r["sic"] // 100).astype("Int64")

    # Windows (trading-day indices), truncated at the next announcement's day +1 and the data end.
    last = len(cal) - 1
    nxt = []
    for cik, i0 in zip(r["cik"], r["i0"]):
        arr = all_i0[cik]
        k = np.searchsorted(arr, i0, side="right")
        nxt.append(arr[k] if k < len(arr) else 10**9)
    r["next_i0"] = nxt
    r["w_start"] = r["i0"] + 2
    r["w_end"] = np.minimum.reduce([r["i0"] + WINDOW_END, r["next_i0"] + 1, np.full(len(r), last)])
    r["w_end_1m"] = np.minimum.reduce([r["i0"] + WINDOW_1M, r["next_i0"] + 1, np.full(len(r), last)])

    inv = investment_growth(r[r["in_universe"] & r["baseline"].notna()], tenk)
    r = r.join(inv)
    r["jump"] = (r["d_ai"] >= JUMP_ABS) & (r["ai_full"] >= JUMP_MIN)
    r["washer"] = r["jump"] & (r["g"] < G_CUT)
    r["investor"] = r["jump"] & (r["g"] >= G_CUT)
    r["jump_strict"] = (r["d_ai_strict"] >= JUMP_ABS) & (r["ai_strict"] >= JUMP_MIN)
    r["washer_strict"] = r["jump_strict"] & (r["g"] < G_CUT)
    r["jump_rate"] = (r["d_rate"] >= 1.0) & (r["ai_full"] >= JUMP_MIN)
    r["washer_rate"] = r["jump_rate"] & (r["g"] < G_CUT)
    r["core_tech"] = r["sic"].apply(lambda s: any(a <= s <= b for a, b in CORE_TECH) if pd.notna(s) else False)
    r["eligible"] = r["in_universe"] & r["baseline"].notna() & (r["w_end"] >= r["w_start"])
    return r


# =========================================================================================== abnormal returns
def abnormal_returns(ev: pd.DataFrame, uni: pd.DataFrame, px: pd.DataFrame, cal: pd.DatetimeIndex):
    ciks = sorted(set(uni["cik"]))
    R = (px[px["cik"].isin(ciks)].pivot(index="date", columns="cik", values="ret").reindex(index=cal, columns=ciks)
           .to_numpy(dtype=float))
    col = {c: j for j, c in enumerate(ciks)}
    peers_level, n_peers, ar, ar_1m, ar_ann, n_self_missing, n_bench_missing = [], [], [], [], [], 0, 0
    groups = {}
    for me, g in uni.merge(pd.DataFrame({"cik": ciks}), on="cik").groupby("month_end"):
        sic = g["cik"].map(SIC2)
        groups[me] = {"cik": g["cik"].to_numpy(), "sic2": sic.to_numpy(), "ter": g["tercile"].to_numpy()}
    for e in ev.itertuples():
        gm = groups[e.month_end]
        not_self = gm["cik"] != e.cik
        cand = [("sic2_tercile", not_self & (gm["sic2"] == e.sic2) & (gm["ter"] == e.tercile)),
                ("sic2", not_self & (gm["sic2"] == e.sic2)),
                ("tercile", not_self & (gm["ter"] == e.tercile))]
        # Unknown SIC (coded -1) never forms an "industry": go straight to the size-tercile peers.
        usable = [(lv, m) for lv, m in cand if (e.sic2 >= 0 or lv == "tercile")]
        level, mask = next(((lv, m) for lv, m in usable if m.sum() >= 10), usable[-1])
        pcols = [col[c] for c in gm["cik"][mask]]
        peers_level.append(level)
        n_peers.append(len(pcols))
        out = []
        for a, b in [(e.w_start, e.w_end), (e.w_start, e.w_end_1m), (e.i0, min(e.i0 + 1, len(cal) - 1))]:
            rows = np.arange(a, b + 1)
            own = R[rows, col[e.cik]]
            with np.errstate(all="ignore"):
                bench = np.nanmean(R[np.ix_(rows, pcols)], axis=1) if len(rows) else np.array([])
            x = own - bench
            n_self_missing += int(np.isnan(own).sum())
            n_bench_missing += int((~np.isnan(own) & np.isnan(bench)).sum())
            out.append(np.where(np.isnan(x), 0.0, x))
        ar.append(out[0]); ar_1m.append(out[1]); ar_ann.append(out[2])
    ev = ev.copy()
    ev["peers_level"], ev["n_peers"] = peers_level, n_peers
    ev["ar"], ev["ar_1m"], ev["ar_ann"] = ar, ar_1m, ar_ann
    ev["car"] = [x.sum() for x in ar]
    ev["car_1m"] = [x.sum() for x in ar_1m]
    ev["car_ann"] = [x.sum() for x in ar_ann]
    print(f"AR days set to 0: own return missing {n_self_missing:,}; benchmark missing {n_bench_missing:,}")
    return ev


SIC2: dict = {}


# =========================================================================================== statistics
def nw_mean(x, lags: int):
    x = pd.Series(x).dropna()
    if len(x) < 3:
        return np.nan, np.nan, len(x)
    res = sm.OLS(x.to_numpy(), np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(res.params[0]), float(res.tvalues[0]), len(x)


def calendar_time(ev: pd.DataFrame, cal: pd.DatetimeIndex, start_col="w_start", ar_col="ar",
                  months=MONTHS, min_held=MIN_HELD) -> pd.DataFrame:
    tot, cnt = np.zeros(len(cal)), np.zeros(len(cal))
    entries = np.zeros(len(cal))
    for a, x in zip(ev[start_col], ev[ar_col]):
        if len(x) == 0:
            continue
        tot[a:a + len(x)] += x
        cnt[a:a + len(x)] += 1
        entries[a] += 1
    d = pd.DataFrame({"tot": tot, "cnt": cnt, "entries": entries}, index=cal)
    d["ar"] = np.where(d["cnt"] > 0, d["tot"] / np.maximum(d["cnt"], 1), np.nan)
    m = d.groupby(d.index.to_period("M")).agg(ar=("ar", lambda s: s.sum(min_count=1)), held=("cnt", "mean"),
                                              entries=("entries", "sum"))
    m["cost"] = m["entries"] * COST_EVENT / m["held"].where(m["held"] > 0) + BORROW_YR / 12
    m = m.loc[pd.Period(months[0]):pd.Period(months[1])]
    m["keep"] = m["held"] >= min_held
    return m, d


def summarize(m: pd.DataFrame, label: str) -> dict:
    k = m[m["keep"]]
    mean, t, n = nw_mean(k["ar"], 3)
    net = (-k["ar"] - k["cost"])
    nmean, nt, _ = nw_mean(net, 3)
    return {"label": label, "months": n, "mean_monthly_AR_%": mean * 100, "t_NW3": t,
            "avg_held": k["held"].mean(), "mean_cost_%": k["cost"].mean() * 100,
            "short_net_%/mo": nmean * 100, "short_net_t": nt}


def ff_factors() -> pd.DataFrame:
    def read(path, cols):
        z = zipfile.ZipFile(path)
        lines = z.read(z.namelist()[0]).decode("latin-1").splitlines()
        rows = [l.split(",") for l in lines if l[:8].strip().isdigit() and len(l.strip()) > 8]
        df = pd.DataFrame([[r[0].strip()] + [float(v) for v in r[1:1 + len(cols)]] for r in rows if len(r) >= 1 + len(cols)],
                          columns=["date"] + cols)
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        return df.set_index("date") / 100
    ff3 = read(ROOT / "data/cache/F-F_Research_Data_Factors_daily_CSV.zip", ["MktRF", "SMB", "HML", "RF"])
    mom = read(ROOT / "data/cache/F-F_Momentum_Factor_daily_CSV.zip", ["Mom"])
    return ff3.join(mom, how="inner")


# =========================================================================================== main
def main():
    out_lines = []

    def say(s=""):
        print(s)
        out_lines.append(str(s))

    cal, uni, comp, rel, feats, tenk, px = load()
    comp["cik"] = comp["cik"].astype(str).str.zfill(10)
    SIC2.update({c: (int(s) // 100 if pd.notna(s) else -1) for c, s in zip(comp["cik"], comp["sic"])})
    ev = build_events(cal, uni, comp, rel, feats, tenk)
    ev["sic2"] = ev["sic2"].fillna(-1).astype(int)

    # ------------------------------------------------------------------ data audit (no returns yet)
    say("=== DATA ===")
    say(f"earnings 8-K filings: {rel['accessionNumber'].nunique():,}; with press-release text: {len(feats):,}")
    say(f"text releases of universe firms: {len(ev):,}; with baseline: {ev['baseline'].notna().sum():,}; "
        f"eligible (in universe at formation, baseline, window): {ev['eligible'].sum():,}")
    el = ev[ev["eligible"]]
    q = el.groupby(el["day0"].dt.to_period("Q")).agg(events=("cik", "size"), jumps=("jump", "sum"),
                                                     washers=("washer", "sum"), investors=("investor", "sum"),
                                                     inv_unknown=("g", lambda s: s.isna().sum()),
                                                     mean_ai=("ai_full", "mean"))
    say(q.to_string())
    prim = el[(el["day0"] >= PRIMARY[0]) & (el["day0"] <= PRIMARY[1])]
    say(f"\nprimary window {PRIMARY}: eligible {len(prim):,}, AI jumps {prim['jump'].sum():,}, washers "
        f"{prim['washer'].sum():,}, investors {prim['investor'].sum():,}, jumps with unknown investment "
        f"{(prim['jump'] & prim['g'].isna()).sum():,}")
    say(f"investment growth g (eligible, primary): median {prim['g'].median():.3f}, share < 10%: "
        f"{(prim['g'] < G_CUT).mean():.2f}, unknown {prim['g'].isna().mean():.2f}")
    # look-ahead guards
    assert (el["month_end"] < el["day0"]).all(), "formation month-end must precede day 0"
    assert (el["tenk_filed"].isna() | (el["tenk_filed"] < el["day0"])).all(), "10-K must be filed before day 0"
    assert (el["w_start"] == el["i0"] + 2).all() and (el["w_end"] >= el["w_start"]).all()
    tick = px.sort_values("date").groupby("cik")["ticker"].last()
    smp = prim[prim["washer"]].sample(min(15, int(prim["washer"].sum())), random_state=1)
    say("\nrandom washer events:")
    for e in smp.itertuples():
        say(f"  {tick.get(e.cik, '?'):6s} {e.accepted_et:%Y-%m-%d %H:%M} day0 {e.day0:%Y-%m-%d} AI {e.ai_full:>3.0f} "
            f"(baseline {e.baseline:4.1f}, {e.n_prior} prior)  g {e.g:+.1%}  10-K filed {e.tenk_filed:%Y-%m-%d}  "
            f"window {e.w_end - e.w_start + 1}d  acc {e.accessionNumber}")

    # ------------------------------------------------------------------ returns
    ev_el = abnormal_returns(el, uni, px, cal)
    say(f"peer benchmark level (eligible events): {ev_el['peers_level'].value_counts().to_dict()}; "
        f"median peers {ev_el['n_peers'].median():.0f}")
    P = ev_el[(ev_el["day0"] >= PRIMARY[0]) & (ev_el["day0"] <= PRIMARY[1])]

    say("\n=== PRIMARY TEST: washers, calendar-time monthly abnormal return (prediction < 0) ===")
    W = P[P["washer"]]
    m_w, d_w = calendar_time(W, cal)
    s = summarize(m_w, "washers")
    say(f"washer events: {len(W):,}  ({W['cik'].nunique():,} firms)")
    say(pd.Series(s).to_string())
    verdict = ("INCONCLUSIVE (<100 washer events)" if len(W) < 100 else
               "PASS" if (s["t_NW3"] <= -2.0 and s["short_net_%/mo"] > 0) else "FAIL")
    if verdict == "PASS" and s["t_NW3"] <= -3:
        verdict = "PASS (convincing, t <= -3)"
    say(f"VERDICT: {verdict}")
    m_w.to_csv(HERE / "monthly_washers.csv")

    # ------------------------------------------------------------------ robustness
    say("\n=== ROBUSTNESS (reported only) ===")
    rows = [s]
    sets = {"1 all AI jumps": P[P["jump"]], "2 investors": P[P["investor"]],
            "4 washers, strict dictionary": P[P["washer_strict"]],
            "5 washers, length-normalised jump": P[P["washer_rate"]],
            "8 washers excl. core tech": P[P["washer"] & ~P["core_tech"]]}
    monthly = {"washers": m_w}
    for k, sub in sets.items():
        m, _ = calendar_time(sub, cal)
        monthly[k] = m
        r = summarize(m, k)
        r["events"] = len(sub)
        rows.append(r)
    m1, _ = calendar_time(W, cal, ar_col="ar_1m")
    r = summarize(m1, "7 washers, 1-month hold")
    r["events"] = len(W)
    rows.append(r)
    rows[0]["events"] = len(W)
    say(pd.DataFrame(rows).set_index("label").round(3).to_string())

    both = monthly["washers"][["ar", "keep"]].join(monthly["2 investors"][["ar", "keep"]], rsuffix="_inv")
    both = both[both["keep"] & both["keep_inv"]]
    dm, dt, dn = nw_mean(both["ar"] - both["ar_inv"], 3)
    say(f"\n2b washers minus investors: {dm * 100:+.3f}%/month, t {dt:+.2f}, months {dn} (prediction < 0)")

    reg = P.copy()
    lo, hi = reg["d_ai"].quantile([0.01, 0.99])
    reg["d_ai_w"] = reg["d_ai"].clip(lo, hi)
    reg["q"] = reg["day0"].dt.to_period("Q").astype(str)
    reg["mon"] = reg["day0"].dt.to_period("M").astype(str)
    fit = smf.ols("car ~ d_ai_w + C(q) + C(sic2)", data=reg).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(reg["mon"])[0]})
    say(f"3 event regression CAR on dAI (winsorised), FE quarter+SIC2, cluster month: slope "
        f"{fit.params['d_ai_w'] * 100:+.4f}% per mention, t {fit.tvalues['d_ai_w']:+.2f}, N {int(fit.nobs):,}")

    ff = ff_factors()
    dd = d_w[d_w["cnt"] > 0][["ar"]].join(ff, how="inner")
    dd = dd[(dd.index >= pd.Timestamp(MONTHS[0] + "-01"))]
    X = sm.add_constant(dd[["MktRF", "SMB", "HML", "Mom"]])
    f6 = sm.OLS(dd["ar"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    say(f"6 washers daily AR on FF3+Mom: alpha {f6.params['const'] * 21 * 100:+.3f}%/month, t "
        f"{f6.tvalues['const']:+.2f}, days {int(f6.nobs)} (factors end {ff.index.max():%Y-%m-%d}); loadings "
        + ", ".join(f"{k} {v:+.2f}" for k, v in f6.params.drop("const").items()))

    others = P[~P["jump"]]
    say(f"9 announcement reaction (days 0..+1): washers {W['car_ann'].mean() * 100:+.2f}% (n {len(W)}), "
        f"non-jump events {others['car_ann'].mean() * 100:+.2f}% (n {len(others)}); Welch t of the difference "
        f"{_welch(W['car_ann'], others['car_ann']):+.2f}")

    PL = ev_el[(ev_el["day0"] >= PLACEBO[0]) & (ev_el["day0"] <= PLACEBO[1]) & ev_el["washer"]]
    if len(PL) >= 30:
        mp, _ = calendar_time(PL, cal, months=("2021-08", "2023-02"))
        r = summarize(mp, "10 placebo washers 2021-07..2022-11")
        say(f"10 pre-ChatGPT placebo: {len(PL)} events, " + ", ".join(f"{k} {v:.3f}" if isinstance(v, float) else f"{k} {v}" for k, v in r.items()))
    else:
        say(f"10 pre-ChatGPT placebo: only {len(PL)} washer events (< 30), not tested")

    # ------------------------------------------------------------------ outputs
    keep_cols = ["cik", "accessionNumber", "accepted_et", "day0", "month_end", "tercile", "sic", "ai_full",
                 "ai_strict", "n_words", "n_prior", "baseline", "d_ai", "g", "tenk_acc", "tenk_filed", "jump",
                 "washer", "investor", "peers_level", "n_peers", "w_start", "w_end", "car", "car_1m", "car_ann"]
    o = ev_el[keep_cols].copy()
    o.insert(1, "ticker", o["cik"].map(tick))
    o.to_csv(HERE / "events.csv", index=False)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 4.5))
        for k, lab in [("washers", "Washers (AI jump, capex+R&D growth < 10%)"),
                       ("2 investors", "Investors (AI jump, growth ≥ 10%)"), ("1 all AI jumps", "All AI jumps")]:
            mm = monthly[k]
            ser = mm["ar"].where(mm["keep"]).fillna(0).cumsum() * 100
            ax.plot(ser.index.to_timestamp(), ser.to_numpy(), label=lab)
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_ylabel("Cumulative abnormal return vs peers (%)")
        ax.set_title("Calendar-time abnormal returns after AI-talk jumps in earnings releases")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(HERE / "cumulative.png", dpi=130)
    except Exception as exc:  # the chart is cosmetic
        say(f"(chart skipped: {exc})")
    (HERE / "run_output.txt").write_text("\n".join(out_lines) + "\n")


def _welch(a, b) -> float:
    a, b = pd.Series(a).dropna(), pd.Series(b).dropna()
    return float((a.mean() - b.mean()) / np.sqrt(a.var() / len(a) + b.var() / len(b)))


if __name__ == "__main__":
    main()
