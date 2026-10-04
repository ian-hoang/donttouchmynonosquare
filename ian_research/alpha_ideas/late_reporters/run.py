"""Step 2 — the pre-registered late-reporter test (PREREGISTRATION.md). Run ONCE from the repo root:

    uv run python alpha_ideas/late_reporters/run.py

Inputs: data/cache/late_reporters/ (build_events.py) and the AI-washing caches (prices, universe, SIC codes).
Writes events_out.csv, releases_out.csv and run_output.txt here.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
AIW = ROOT / "data" / "cache" / "ai_washing"
LR = ROOT / "data" / "cache" / "late_reporters"
COST_RT, BORROW = 0.0040, 0.01
REL_START, REL_END = "2021-07-01", "2026-06-30"


def clustered_mean(x, groups):
    x = pd.Series(np.asarray(x, dtype=float))
    g = pd.Series(np.asarray(groups))
    ok = x.notna().to_numpy()
    x, g = x[ok], g[ok]
    if len(x) < 3:
        return np.nan, np.nan, len(x)
    res = sm.OLS(x.to_numpy(), np.ones(len(x))).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(g)[0]})
    return float(res.params[0]), float(res.tvalues[0]), len(x)


def nw_mean(x, lags=3):
    x = pd.Series(x).dropna()
    res = sm.OLS(x.to_numpy(), np.ones(len(x))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(res.params[0]), float(res.tvalues[0]), len(x)


def main():
    lines = []

    def say(s=""):
        print(s)
        lines.append(str(s))

    cal = pd.DatetimeIndex(pd.to_datetime(pd.read_parquet(AIW / "calendar.parquet")["date"])).astype("datetime64[ns]")
    uni = pd.read_parquet(AIW / "universe.parquet")
    uni["month_end"] = pd.to_datetime(uni["month_end"]).astype("datetime64[ns]")
    comp = pd.read_parquet(AIW / "sec" / "companies.parquet")
    comp["cik"] = comp["cik"].astype(str).str.zfill(10)
    sic2 = {c: (int(s) // 100 if pd.notna(s) else -1)
            for c, s in zip(comp["cik"], pd.to_numeric(comp["sic"], errors="coerce"))}
    px = pd.read_parquet(AIW / "prices.parquet", columns=["date", "cik", "ticker", "ret"])
    px["date"] = pd.to_datetime(px["date"]).astype("datetime64[ns]")
    tick = px.sort_values("date").groupby("cik")["ticker"].last()
    ciks = sorted(set(uni["cik"]))
    R = px[px["cik"].isin(ciks)].pivot(index="date", columns="cik", values="ret").reindex(index=cal, columns=ciks).to_numpy(float)
    col = {c: j for j, c in enumerate(ciks)}
    mes = np.sort(uni["month_end"].unique())
    groups = {me: {"cik": g["cik"].to_numpy(), "sic2": g["cik"].map(sic2).to_numpy(), "ter": g["tercile"].to_numpy()}
              for me, g in uni.groupby("month_end")}
    member = set(zip(uni["month_end"], uni["cik"]))

    def formation(date):
        k = np.searchsorted(mes, np.datetime64(date), side="left") - 1
        return pd.Timestamp(mes[k]) if k >= 0 else None

    def peers(cik, me):
        gm = groups[me]
        row = gm["cik"] == cik
        ter = gm["ter"][row][0]
        s2 = sic2.get(cik, -1)
        not_self = ~row
        cand = [not_self & (gm["sic2"] == s2) & (gm["ter"] == ter), not_self & (gm["sic2"] == s2),
                not_self & (gm["ter"] == ter)]
        cand = cand if s2 >= 0 else cand[-1:]
        mask = next((m for m in cand if m.sum() >= 10), cand[-1])
        return [col[c] for c in gm["cik"][mask]]

    def ar_path(cik, pcols, a, b):
        if b < a:
            return np.array([])
        rows = np.arange(a, b + 1)
        own = R[rows, col[cik]]
        with np.errstate(all="ignore"):
            bench = np.nanmean(R[np.ix_(rows, pcols)], axis=1)
        x = own - bench
        return np.where(np.isnan(x), 0.0, x)

    # ------------------------------------------------------------------ late signals
    sig = pd.read_parquet(LR / "signals.parquet")
    sig["O"] = pd.to_datetime(sig["O"]).astype("datetime64[ns]")
    sig["month_end"] = [formation(d) for d in sig["O"]]
    sig = sig[[(me, c) in member for me, c in zip(sig["month_end"], sig["cik"])]].copy()
    out = []
    for e in sig.itertuples():
        pc = peers(e.cik, e.month_end)
        hold = ar_path(e.cik, pc, e.o_idx + 1, e.exit_idx)
        wait = ar_path(e.cik, pc, e.o_idx + 1, e.release_i0 - 1) if e.released else hold
        react = ar_path(e.cik, pc, e.release_i0, e.release_i0 + 1) if e.released else np.array([])
        n_hold = e.exit_idx - e.o_idx
        cost = COST_RT + BORROW * n_hold / 252
        out.append({"cik": e.cik, "ticker": tick.get(e.cik), "rule": e.rule, "E": e.E, "O": e.O.date(),
                    "released": e.released, "delay_days": e.delay_days, "hold_days": n_hold, "n_peers": len(pc),
                    "car": hold.sum(), "car_wait": wait.sum(), "car_react": react.sum() if len(react) else np.nan,
                    "cost": cost, "short_net": -hold.sum() - cost, "o_idx": e.o_idx, "path": hold})
    ev = pd.DataFrame(out)
    ev["month"] = pd.to_datetime(ev["O"]).dt.to_period("M").astype(str)
    k3, k5 = ev[ev["rule"] == "k3"], ev[ev["rule"] == "k5"]

    say("=== DATA ===")
    say(f"late signals in the universe: E+3 {len(k3):,} ({k3['cik'].nunique():,} firms), E+5 {len(k5):,}")
    say(f"E+3: released within 60 trading days {k3['released'].mean():.1%}; median holding {k3['hold_days'].median():.0f} "
        f"days (mean {k3['hold_days'].mean():.1f}); median peers {k3['n_peers'].median():.0f}")

    say("\n=== PRIMARY: short late reporters from E+3 to release day +1 (prediction: CAR < 0) ===")
    m, t, n = clustered_mean(k3["car"], k3["month"])
    nm, nt, _ = clustered_mean(k3["short_net"], k3["month"])
    say(f"N {n:,} events in {k3['month'].nunique()} months | mean CAR {m * 100:+.3f}% | t (clustered by month) {t:+.2f} | "
        f"share negative {(k3['car'] < 0).mean():.2f} | median {k3['car'].median() * 100:+.3f}%")
    say(f"tradable short, net of {k3['cost'].mean() * 100:.2f}% mean cost: {nm * 100:+.3f}% per event (t {nt:+.2f})")
    verdict = ("INCONCLUSIVE (< 100 events)" if n < 100 else "PASS" if (t <= -2.0 and nm > 0) else "FAIL")
    if verdict == "PASS" and t <= -3:
        verdict = "PASS (convincing, t <= -3)"
    say(f"VERDICT: {verdict}")

    say("\n=== ROBUSTNESS (reported only) ===")
    rows = []

    def add(label, x, g):
        mm, tt, nn = clustered_mean(x, g)
        rows.append({"variant": label, "N": nn, "mean_%": mm * 100, "t": tt})
    rel_k3 = k3[k3["released"]]
    add("2a waiting part (E+3 -> day before release)", rel_k3["car_wait"], rel_k3["month"])
    add("2b release reaction (day 0 -> +1)", rel_k3["car_react"], rel_k3["month"])
    add("3 stricter threshold (E+5)", k5["car"], k5["month"])
    late5 = k3[pd.to_datetime(k3["O"]) >= "2022-07-01"]
    add("5 O >= 2022-07-01 (skip COVID base year)", late5["car"], late5["month"])
    nr = k3[~k3["released"]]
    add("7 signals with no release within 60 days", nr["car"], nr["month"])

    # post-release drift by delay group (robustness 1 and 4)
    rel = pd.read_parquet(LR / "releases.parquet")
    rel["release_date"] = pd.to_datetime(rel["release_date"]).astype("datetime64[ns]")
    rel = rel[(rel["release_date"] >= REL_START) & (rel["release_date"] <= REL_END)]
    # one row per filing: if two anchors claim the same release, keep the anchor it is closest to
    rel = rel.assign(absd=rel["delay_days"].abs()).sort_values("absd").drop_duplicates(["cik", "acc"])
    rel["month_end"] = [formation(d) for d in rel["release_date"]]
    rel = rel[[(me, c) in member for me, c in zip(rel["month_end"], rel["cik"])]]
    last = len(cal) - 1
    drift = []
    for r in rel.itertuples():
        a, b = r.release_i0 + 2, min(r.release_i0 + 63, r.next_i0 + 1, last)
        if b < a:
            continue
        p = ar_path(r.cik, peers(r.cik, r.month_end), a, b)
        drift.append({"cik": r.cik, "release_date": r.release_date, "delay_days": r.delay_days, "car_post": p.sum()})
    dr = pd.DataFrame(drift)
    dr["month"] = dr["release_date"].dt.to_period("M").astype(str)
    late_r, on_r, early_r = dr[dr["delay_days"] >= 7], dr[dr["delay_days"].abs() <= 3], dr[dr["delay_days"] <= -7]
    add("1 post-release drift (+2..+63), releases >= 7 days late", late_r["car_post"], late_r["month"])
    add("1b post-release drift, on-time releases (|delay| <= 3)", on_r["car_post"], on_r["month"])
    add("4 post-release drift, early releases (<= -7 days)", early_r["car_post"], early_r["month"])
    both = pd.concat([late_r.assign(late=1.0), on_r.assign(late=0.0)])
    X = sm.add_constant(both["late"])
    fit = sm.OLS(both["car_post"].to_numpy(), X).fit(cov_type="cluster",
                                                     cov_kwds={"groups": pd.factorize(both["month"])[0]})
    rows.append({"variant": "1c late minus on-time post drift", "N": len(both),
                 "mean_%": fit.params["late"] * 100, "t": fit.tvalues["late"]})
    say(pd.DataFrame(rows).set_index("variant").round(3).to_string())

    # calendar-time version of the primary (robustness 6)
    tot, cnt = np.zeros(len(cal)), np.zeros(len(cal))
    for o, pth in zip(k3["o_idx"], k3["path"]):
        tot[o + 1:o + 1 + len(pth)] += pth
        cnt[o + 1:o + 1 + len(pth)] += 1
    d = pd.DataFrame({"ar": np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan), "cnt": cnt}, index=cal)
    mon = d.groupby(d.index.to_period("M")).agg(ar=("ar", lambda s: s.sum(min_count=1)), held=("cnt", "mean"))
    mon = mon[mon["ar"].notna()]
    cm, ct, cn = nw_mean(mon["ar"])
    say(f"6 calendar-time (daily mean AR of open shorts, summed by month): {cm * 100:+.3f}%/month, NW t {ct:+.2f}, "
        f"months {cn}, avg positions held {mon['held'].mean():.1f}")

    say("\nlargest late-signal moves:")
    for r in k3.reindex(k3["car"].abs().sort_values(ascending=False).index).head(10).itertuples():
        say(f"  {r.ticker or '?':6s} O {r.O} hold {r.hold_days:2d}d delay {r.delay_days} CAR {r.car * 100:+7.2f}%")
    ev.drop(columns=["path"]).to_csv(HERE / "events_out.csv", index=False)
    dr.to_csv(HERE / "releases_out.csv", index=False)
    (HERE / "run_output.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
