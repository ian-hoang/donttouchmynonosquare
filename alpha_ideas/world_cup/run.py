"""Step 3 — the pre-registered World Cup test (PREREGISTRATION.md). Run ONCE from the repo root:

    uv run python alpha_ideas/world_cup/run.py

Inputs: data/cache/world_cup/ (fetch.py, build_events.py). Writes events_out.csv and run_output.txt here.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "cache" / "world_cup"
INCEPTION = {"EDEN": "2012-01-25", "KSA": "2015-09-16"}       # earlier rows belong to other securities
COLOMBIA = ("GXG", "COLO", "2025-06-20", "2025-06-23")          # same fund, renamed
SOCCER_NATIONS = {"Argentina", "Brazil", "England", "France", "Germany", "Italy", "Netherlands", "Portugal", "Spain"}
LIQUID_DV = 5e6
COST_LIQUID, COST_ILLIQUID, COST_BASKET = 0.0010, 0.0030, 0.0005
MAX_GAP = 5


# ------------------------------------------------------------------------------------------- prices
def load_etf(t: str) -> pd.DataFrame:
    rows = json.loads((CACHE / f"aggs_{t}.json").read_text())
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None)
    df = df.rename(columns={"o": "open", "c": "close", "v": "volume"})[["date", "open", "close", "volume"]]
    if t in INCEPTION:
        df = df[df["date"] >= INCEPTION[t]]
    divs = pd.DataFrame(json.loads((CACHE / f"dividends_{t}.json").read_text()))
    spl = pd.DataFrame(json.loads((CACHE / f"splits_{t}.json").read_text()))
    df["div"] = 0.0
    if not divs.empty:
        divs = divs[divs.get("currency", pd.Series("USD", index=divs.index)).fillna("USD") == "USD"].copy()
        divs["ex"] = pd.to_datetime(divs["ex_dividend_date"])
        if t in INCEPTION:
            divs = divs[divs["ex"] >= INCEPTION[t]]
        divs = divs.drop_duplicates(["ex", "cash_amount"])
        f = np.ones(len(divs))
        if not spl.empty:
            spl["exec"] = pd.to_datetime(spl["execution_date"])
            for i, ex in enumerate(divs["ex"]):
                for e, a, b in zip(spl["exec"], spl["split_from"], spl["split_to"]):
                    if e > ex:
                        f[i] *= b / a
        divs["adj"] = divs["cash_amount"].to_numpy() / f
        dates = df["date"].to_numpy()
        for ex, amt in zip(divs["ex"], divs["adj"]):
            k = np.searchsorted(dates, np.datetime64(ex))
            if k < len(dates):
                df.iloc[k, df.columns.get_loc("div")] += amt
    return df.reset_index(drop=True)


def load_prices(etfs: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    for t in etfs:
        if t == "GXG|COLO":
            a, b = load_etf(COLOMBIA[0]), load_etf(COLOMBIA[1])
            a, b = a[a["date"] <= COLOMBIA[2]], b[b["date"] >= COLOMBIA[3]]
            print(f"Colombia stitch: GXG last close {a['close'].iloc[-1]:.2f} on {a['date'].iloc[-1].date()}, "
                  f"COLO first close {b['close'].iloc[0]:.2f} on {b['date'].iloc[0].date()}")
            df = pd.concat([a, b], ignore_index=True)
        else:
            df = load_etf(t)
        prev = df["close"].shift(1)
        df["ret"] = (df["close"] + df["div"]) / prev - 1  # gap rule applied below, in U.S. trading days
        df["dv"] = df["close"] * df["volume"]
        out[t] = df.set_index("date")
    return out


# ------------------------------------------------------------------------------------------- helpers
def clustered_mean(x: pd.Series, groups: pd.Series):
    x = pd.Series(x).astype(float)
    ok = x.notna()
    x, groups = x[ok], groups[ok]
    if len(x) < 3:
        return np.nan, np.nan, len(x)
    res = sm.OLS(x.to_numpy(), np.ones(len(x))).fit(cov_type="cluster",
                                                     cov_kwds={"groups": pd.factorize(groups)[0]})
    return float(res.params[0]), float(res.tvalues[0]), len(x)


def entry_point(end_utc: pd.Timestamp, us_days: pd.DatetimeIndex):
    """First U.S. price after the match ends: ('close', day) if it ends 09:30-15:50 ET on a trading day, else
    ('open', next trading day at or after the end)."""
    et = end_utc.tz_convert("America/New_York")
    d = et.normalize().tz_localize(None)
    minutes = et.hour * 60 + et.minute
    if d in us_days and 9 * 60 + 30 <= minutes <= 15 * 60 + 50:
        return "close", d
    if d in us_days and minutes < 9 * 60 + 30:
        return "open", d
    k = us_days.searchsorted(d, side="right")
    return "open", us_days[k]


def interval_return(df: pd.DataFrame, kind: str, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Total return from (close or open of `start`) to the close of `end` (dividends with ex-date after the entry)."""
    if start not in df.index or end not in df.index or end < start:
        return np.nan
    p0 = df.at[start, "close"] if kind == "close" else df.at[start, "open"]
    seg = df.loc[(df.index > start) & (df.index <= end)] if kind == "close" else df.loc[(df.index >= start) & (df.index <= end)]
    divs = seg["div"].sum() if kind == "close" else seg["div"].iloc[1:].sum() if len(seg) > 1 else 0.0
    return float((df.at[end, "close"] + divs) / p0 - 1)


# ------------------------------------------------------------------------------------------- main
def main():
    lines = []

    def say(s=""):
        print(s)
        lines.append(str(s))

    ev = pd.read_parquet(CACHE / "events.parquet")
    matches = pd.read_parquet(CACHE / "matches.parquet")
    etf_by_country = ev.drop_duplicates("team").set_index("team")["etf"].to_dict()
    from build_events import ETF  # the full country -> ETF table (basket members)
    all_etfs = sorted({v[0] for v in ETF.values()})
    px = load_prices(all_etfs)
    us_days = pd.DatetimeIndex(sorted(px["SPY"].index))
    pos = pd.Series(np.arange(len(us_days)), index=us_days)
    for t, df in px.items():
        # a return spanning more than MAX_GAP missing U.S. trading days is stale -> missing
        gap = pos.reindex(df.index).diff().to_numpy() - 1
        df["ret"] = df["ret"].where(gap <= MAX_GAP)
    R = pd.DataFrame({t: df["ret"] for t, df in px.items()}).reindex(us_days)

    # ---- per-tournament estimation (alpha, beta, liquidity) for every country ETF
    first_match = matches.groupby("year")["date"].min()
    est = {}
    for y, d0 in first_match.items():
        k0 = us_days.searchsorted(d0)
        win = us_days[max(k0 - 270, 0):k0 - 20]
        for t in all_etfs:
            others = [o for o in all_etfs if o != t]
            b = R.loc[win, others].mean(axis=1)
            x = pd.concat([R.loc[win, t], b], axis=1, keys=["r", "b"]).dropna()
            if len(x) < 150:
                continue
            fit = sm.OLS(x["r"], sm.add_constant(x["b"])).fit()
            dv = px[t].loc[px[t].index.isin(win), "dv"].median()
            est[(y, t)] = {"alpha": fit.params["const"], "beta": fit.params["b"], "n_est": len(x), "dv": dv}

    # ---- event returns
    out, stale = [], []
    for e in ev.itertuples():
        key = (e.year, e.etf)
        if key not in est:
            continue
        p = est[key]
        df = px[e.etf]
        others = [o for o in all_etfs if o != e.etf]
        d = e.event_date
        # if the ETF did not trade on D (illiquid), use its first trading day after D (return since its last close)
        k = df.index.searchsorted(d)
        if k >= len(df.index):
            continue
        d_used = df.index[k]
        prev = df.index[k - 1]
        if pos[d_used] - pos[prev] - 1 > MAX_GAP or (d_used != d and pos[d_used] - pos[d] > MAX_GAP):
            stale.append(f"{e.year} {e.team} {e.etf} {d.date()}")
            continue
        r_i = (df.at[d_used, "close"] + df.loc[(df.index > prev) & (df.index <= d_used), "div"].sum()) / df.at[prev, "close"] - 1
        span = us_days[(us_days > prev) & (us_days <= d_used)]
        b_days = R.loc[span, others].mean(axis=1)
        r_b = float((1 + b_days).prod() - 1)
        n_days = len(span)
        ar = r_i - (p["alpha"] * n_days + p["beta"] * r_b)
        ar_mkt = r_i - r_b
        # two-day window: D and the next U.S. trading day
        k2 = us_days.searchsorted(d_used) + 1
        ar2 = np.nan
        if k2 < len(us_days):
            d2 = us_days[k2]
            if d2 in df.index:
                r2 = df.at[d2, "ret"]
                b2 = R.loc[d2, others].mean()
                ar2 = ar + (r2 - (p["alpha"] + p["beta"] * b2))
        # tradable: first U.S. price after the match ends -> close of D (hedged with beta x basket)
        kind, start = entry_point(e.end_utc, us_days)
        ri_t = interval_return(df, kind, start, d_used)
        rb_t = np.nanmean([interval_return(px[o], kind, start, d_used) for o in others
                           if start in px[o].index and d_used in px[o].index])
        cost_i = COST_LIQUID if p["dv"] >= LIQUID_DV else COST_ILLIQUID
        cost = 2 * (cost_i + abs(p["beta"]) * COST_BASKET)
        short_gross = -(ri_t - p["beta"] * rb_t)
        out.append({**e._asdict(), "d_used": d_used, "n_days": n_days, "r_i": r_i, "r_b": r_b, "alpha": p["alpha"],
                    "beta": p["beta"], "n_est": p["n_est"], "dv": p["dv"], "liquid": p["dv"] >= LIQUID_DV,
                    "ar": ar, "ar_mkt": ar_mkt, "ar2": ar2, "entry": f"{kind} {start.date()}",
                    "short_gross": short_gross, "short_net": short_gross - cost, "cost": cost})
    o = pd.DataFrame(out)
    o["date_key"] = o["d_used"].astype(str)
    o.drop(columns=["Index"]).to_csv(HERE / "events_out.csv", index=False)

    ko = o[(o["side"] == "loss") & o["knockout"]]
    say("=== DATA ===")
    say(f"events with an available ETF: {len(o)} (knockout losses {len(ko)}, group losses "
        f"{int(((o['side'] == 'loss') & ~o['knockout']).sum())}, wins {int((o['side'] == 'win').sum())})")
    say("knockout losses by tournament: " + str(ko.groupby("year").size().to_dict()))
    say(f"events where the ETF had no trade on the event day (next trading day used): {int((o['d_used'] != o['event_date']).sum())}; "
        f"dropped as stale (> {MAX_GAP} missing trading days): {len(stale)} {stale[:8]}")
    say(f"betas: median {o['beta'].median():.2f} (range {o['beta'].min():.2f} to {o['beta'].max():.2f}); "
        f"illiquid-ETF events {int((~o['liquid']).sum())}")

    say("\n=== PRIMARY: knockout losses, event-day abnormal return (prediction < 0) ===")
    m, t, n = clustered_mean(ko["ar"], ko["date_key"])
    sn, st, _ = clustered_mean(ko["short_net"], ko["date_key"])
    sg, sgt, _ = clustered_mean(ko["short_gross"], ko["date_key"])
    say(f"N {n} events on {ko['date_key'].nunique()} dates | mean AR {m * 100:+.3f}% | t (clustered by date) {t:+.2f} | "
        f"share negative {(ko['ar'] < 0).mean():.2f}")
    say(f"tradable short (first price after the final whistle -> close of D, beta-hedged): gross {sg * 100:+.3f}% "
        f"(t {sgt:+.2f}), net {sn * 100:+.3f}% (t {st:+.2f}) per event, mean cost {ko['cost'].mean() * 100:.2f}%")
    verdict = ("INCONCLUSIVE (< 30 events)" if n < 30 else "PASS" if (t <= -2.0 and sn > 0) else "FAIL")
    if verdict == "PASS" and t <= -3:
        verdict = "PASS (convincing, t <= -3)"
    say(f"VERDICT: {verdict}")

    say("\n=== ROBUSTNESS (reported only) ===")
    rows = []

    def add(label, sub, col="ar"):
        mm, tt, nn = clustered_mean(sub[col], sub["date_key"])
        rows.append({"variant": label, "N": nn, "mean_%": mm * 100, "t": tt})
    add("1 group-stage losses", o[(o["side"] == "loss") & ~o["knockout"]])
    add("2 all wins", o[o["side"] == "win"])
    add("2b knockout wins", o[(o["side"] == "win") & o["knockout"]])
    add("3 knockout losses, two-day window", ko, "ar2")
    add("4 knockout losses, market-adjusted (beta=1)", ko, "ar_mkt")
    add("5 knockout losses, soccer nations", ko[ko["team"].isin(SOCCER_NATIONS)])
    add("6 knockout losses, 2026 only", ko[ko["year"] == 2026])
    add("7 knockout losses, liquid ETFs only", ko[ko["liquid"]])
    add("  (all losses pooled)", o[o["side"] == "loss"])
    say(pd.DataFrame(rows).set_index("variant").round(3).to_string())

    # diagnostic (not pre-registered): the AR model on ordinary days inside the tournaments should average ~0
    diag = []
    for y, d0 in first_match.items():
        end = matches.loc[matches["year"] == y, "date"].max() + pd.Timedelta(days=3)
        days = us_days[(us_days >= d0) & (us_days <= end)]
        for (yy, tkr), p in est.items():
            if yy != y:
                continue
            others = [x for x in all_etfs if x != tkr]
            a = R.loc[days, tkr] - (p["alpha"] + p["beta"] * R.loc[days, others].mean(axis=1))
            diag.append(a.dropna())
    dg = pd.concat(diag)
    say(f"\ndiagnostic: mean AR over all ETF-days during the tournaments (events included): {dg.mean() * 100:+.3f}% "
        f"(sd {dg.std() * 100:.2f}%, n {len(dg)})")

    say("\nknockout losses, largest moves:")
    show = ko.reindex(ko["ar"].abs().sort_values(ascending=False).index).head(12)
    for r in show.itertuples():
        say(f"  {r.year} {r.round:22s} {r.team:13s} {r.etf:8s} {r.d_used.date()} AR {r.ar * 100:+6.2f}%  ({r.score})")
    (HERE / "run_output.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
