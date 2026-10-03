"""Reproduce every number and figure in the quant note.

    python data/download.py                 # market data (free sources; ~1 min)
    python run_all.py                       # in-sample research report; out-of-sample stays sealed
    python run_all.py --unlock-oos          # evaluate the sealed out-of-sample period ONCE

Inputs: data/features/video_features.csv (committed, produced by pipeline/), data/market/* (downloaded),
config/strategy.json + config/signal_spec.json (frozen at the pre-registration commit).
Outputs: results/summary.md, results/*.json|csv, results/figures/*.png, results/variants_log.csv,
results/oos_log.md (append-only record of every out-of-sample evaluation).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from pokerface import research as R  # noqa: E402
from pokerface import stats as S  # noqa: E402
from pokerface.signal import build_signals  # noqa: E402

RES = ROOT / "results"
FIG = RES / "figures"


def git_hash() -> str:
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT)
    return r.stdout.strip() or "unknown"


def run_lookahead_tests() -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests/"], capture_output=True, text=True, cwd=ROOT)
    print(r.stdout.strip().splitlines()[-1] if r.stdout else r.stderr[-300:])
    return r.returncode == 0


def fmt(x, pct=False, nd=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/a"
    return f"{100 * x:.{nd}f}%" if pct else f"{x:.{nd}f}"


def ml_ridge_signal(feat: pd.DataFrame, sig: pd.DataFrame, ev_all: pd.DataFrame, cars: pd.DataFrame,
                    horizon: int, alpha: float = 10.0, min_train: int = 60) -> pd.Series:
    """Secondary ML variant: walk-forward ridge of CAR_h on the same baseline z-scores, trained only on events
    whose holding window closed (entry + h sessions, plus an h-session purge) before the predicted event."""
    zc = [c for c in sig.columns if c.startswith("z_")]
    X = sig.set_index("video_id")[zc]
    y = cars[f"car_{horizon}"]
    out = pd.Series(np.nan, index=ev_all.index)
    first_vid = ev_all["video_ids"].str.split(",").str[0]
    Xe = X.reindex(first_vid.values).set_axis(ev_all.index)
    entries = ev_all["entry"].values
    for i in range(len(ev_all)):
        cutoff = entries[i] - np.timedelta64(int(2.9 * 2 * horizon), "D")   # ~2h sessions of purge
        tr = (entries < cutoff) & y.notna().values & Xe.notna().any(axis=1).values
        if tr.sum() < min_train:
            continue
        Xt = Xe[tr].fillna(0.0).values
        yt = y[tr].values
        mu, sd = Xt.mean(0), Xt.std(0) + 1e-9
        A = (Xt - mu) / sd
        beta = np.linalg.solve(A.T @ A + alpha * np.eye(A.shape[1]), A.T @ (yt - yt.mean()))
        xi = (Xe.iloc[i].fillna(0.0).values - mu) / sd
        pred_tr = A @ beta
        out.iloc[i] = float(xi @ beta) / (pred_tr.std() + 1e-12)
    return out


def figures(prim, ev, cars, decay, nulls, robust, cases, oos=None):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                         "figure.dpi": 150, "savefig.bbox": "tight"})
    ink, accent, warn, muted = "#1f2937", "#2563eb", "#dc2626", "#9ca3af"

    # 1. equity curves
    r = prim["net"]
    fig, ax = plt.subplots(2, 1, figsize=(6.8, 3.6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    for s, lab, col, ls in [(prim["gross"], "gross", muted, "--"), (r, "net (5 bps)", accent, "-"),
                            (prim["net_x2"], "net, costs x2", warn, ":")]:
        ax[0].plot((1 + s.fillna(0)).cumprod(), ls, color=col, lw=1.3, label=lab)
    if oos is not None:
        ax[0].plot((1 + oos.fillna(0)).cumprod() * (1 + r.fillna(0)).prod(), color=ink, lw=1.3, label="out-of-sample")
        ax[0].axvline(oos.index[0], color=ink, lw=0.6, ls="--")
    ax[0].set_ylabel("growth of $1")
    ax[0].legend(frameon=False, ncol=4, loc="upper left")
    eq = (1 + r.fillna(0)).cumprod()
    ax[1].fill_between(eq.index, eq / eq.cummax() - 1, 0, color=warn, alpha=0.35, lw=0)
    ax[1].set_ylabel("drawdown")
    fig.savefig(FIG / "equity.png")
    plt.close(fig)

    # 2. alpha decay
    if len(decay):
        fig, ax = plt.subplots(figsize=(3.4, 2.4))
        ax.axhline(0, color=muted, lw=0.6)
        se = decay["signed_car_bps"] / decay["t"].replace(0, np.nan)
        ax.errorbar(decay["h"], decay["signed_car_bps"], yerr=1.96 * se.abs(), fmt="o-", color=accent, ms=3, lw=1, capsize=2)
        ax.set_xscale("log")
        ax.set_xticks(decay["h"])
        ax.set_xticklabels(decay["h"])
        ax.set_xlabel("sessions after entry")
        ax.set_ylabel("signed CAR (bps)")
        fig.savefig(FIG / "alpha_decay.png")
        plt.close(fig)

    # 3. nulls
    fig, axs = plt.subplots(1, len(nulls), figsize=(3.4 * len(nulls), 2.3))
    axs = np.atleast_1d(axs)
    for a, (lab, vals) in zip(axs, nulls.items()):
        a.hist(vals, bins=30, color=muted)
        a.axvline(prim["summary"]["sharpe"], color=warn, lw=1.5)
        a.set_title(f"{lab}: p = {(vals >= prim['summary']['sharpe']).mean():.2f}", fontsize=9)
        a.set_xlabel("Sharpe")
    fig.savefig(FIG / "nulls.png")
    plt.close(fig)

    # 4. robustness forest
    if len(robust):
        rb = robust.dropna(subset=["sharpe"]).sort_values("sharpe")
        fig, ax = plt.subplots(figsize=(4.2, 0.18 * len(rb) + 0.8))
        ax.axvline(0, color=muted, lw=0.6)
        ax.axvline(prim["summary"]["sharpe"], color=accent, lw=0.8, ls="--")
        ax.barh(rb["variant"], rb["sharpe"], color=[accent if v == "PRIMARY" else muted for v in rb["variant"]])
        ax.set_xlabel("in-sample net Sharpe")
        fig.savefig(FIG / "robustness.png")
        plt.close(fig)

    # 5. case studies
    for ceo, d in cases.items():
        if d is None or d.empty:
            continue
        fig, ax = plt.subplots(figsize=(6.8, 2.2))
        ax.plot(d["px_date"], d["rel_px"], color=muted, lw=1)
        ax.set_ylabel(f"{d['ticker'].iloc[0]} / SPY")
        ax2 = ax.twinx()
        ax2.scatter(d["entry"], d["tell"], c=np.where(d["tell"] > 0, warn, accent), s=10, zorder=3)
        ax2.axhline(0, color=muted, lw=0.5)
        ax2.set_ylabel("tell score")
        ax.set_title(f"{ceo}: tell score per interview vs relative price", fontsize=9)
        fig.savefig(FIG / f"case_{ceo}.png")
        plt.close(fig)


def case_frame(ceo, ev_all, mkt):
    d = ev_all[ev_all["ceo_id"] == ceo]
    if d.empty:
        return None
    tkr = d["ticker"].iloc[0]
    rel = (mkt.close[tkr] / mkt.close["SPY"]).dropna()
    rel = rel[rel.index >= d["entry"].min() - pd.Timedelta(days=60)]
    out = d[["entry", "tell", "signal", "ticker"]].copy()
    px = pd.DataFrame({"px_date": rel.index, "rel_px": (rel / rel.iloc[0]).values})
    return pd.concat([out.reset_index(drop=True), px], axis=1)


def corpus_funnel(feat_raw: pd.DataFrame, qc: dict, ev_all: pd.DataFrame) -> dict:
    m = ROOT / "data" / "manifest"
    n = lambda f: int(len(pd.read_csv(m / f, usecols=[0]))) if (m / f).exists() else None
    lab = pd.read_csv(m / "curation_labels.csv", dtype={"video_id": str})
    return {"search_hits_round1": n("candidates_raw.csv"),
            "search_hits_round2": n("candidates_years.csv"),
            "rule_prefiltered": n("candidates_for_curation.csv"),
            "agent_curated_keep": int(lab["keep"].astype(str).str.lower().eq("true").sum()),
            "dated_in_tenure_window": n("videos.csv"),
            "processed": int(len(feat_raw)),
            "identity_qc_pass": qc["after_identity_qc"],
            "events_IS": int((ev_all["sample"] == "IS").sum()),
            "events_OOS": int((ev_all["sample"] == "OOS").sum()),
            "ceos_with_events": int(ev_all["ceo_id"].nunique())}


def oos_lock_check(cfg_hash: str, relock: str | None) -> str:
    p = RES / "oos_log.md"
    if p.exists():
        last = [l for l in p.read_text().splitlines() if l.startswith("|") and "config" not in l and "---" not in l]
        if last and cfg_hash not in last[-1]:
            if not relock:
                raise SystemExit("Out-of-sample was already evaluated with a different configuration. Changing the "
                                 "strategy after seeing OOS results is test-set tuning. Rerun with --relock \"reason\" "
                                 "only for a genuine bug fix, and disclose it in the note.")
            return f"relock: {relock}"
        return "reproduction" if last else "first evaluation"
    return "first evaluation"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unlock-oos", action="store_true", help="evaluate the sealed out-of-sample period")
    ap.add_argument("--relock", default=None, help="reason for re-evaluating OOS after a change (disclosed)")
    ap.add_argument("--source", default="yfinance", choices=["yfinance", "databento"])
    ap.add_argument("--fast", action="store_true", help="fewer null draws (development only)")
    a = ap.parse_args()
    RES.mkdir(exist_ok=True)
    print("lookahead tests:", end=" ")
    if not run_lookahead_tests():
        raise SystemExit("lookahead tests failed; refusing to report numbers")

    strat, spec = R.load_configs()
    cfg = R.config_hash(strat, spec)
    mkt = R.load_market(a.source)
    feat_raw = R.load_features()
    feat, qc = R.apply_qc(feat_raw, strat)
    sp = R.signal_params(strat)
    H = strat["backtest"]["horizon"]
    p = R.bt_params(strat)

    sig = build_signals(feat, spec, sp)
    folk = build_signals(feat, R.folk_spec(spec), R.signal_params(strat, min_features=3, min_modalities=1))
    sig["folk_signal"] = folk["signal"]
    ev_all = R.make_events(feat, sig, mkt, strat)                       # primary: earnings windows excluded
    ev_incl = R.make_events(feat, sig, mkt, strat, exclude_earnings=False)
    cars = R.abnormal_paths(ev_all, mkt, hedge=p.hedge)
    is_mask = ev_all["sample"] == "IS"

    # ---------------- primary, in-sample
    prim = R.evaluate("PRIMARY", ev_all, mkt, p, "IS", strat)
    x2 = R.evaluate("costs_x2", ev_all, mkt, p.with_(cost_multiplier=2.0), "IS", strat, factors=False)
    R.log_variant("PRIMARY", cfg, prim.summary)
    s = strat["samples"]
    win = lambda ser: ser[(ser.index >= pd.Timestamp(s["sample_start"])) & (ser.index <= pd.Timestamp(s["is_end"]))]
    net, gross, net_x2 = win(prim.result.daily), win(prim.result.gross_daily), win(x2.result.daily)
    ev_tests = R.event_tests(ev_all[is_mask], cars[is_mask], H)
    decay = R.alpha_decay(ev_all[is_mask], cars[is_mask])
    runup = R.runup_control(ev_all[is_mask], cars[is_mask], mkt, H)
    vol_mech = R.volatility_mechanism(ev_all[is_mask], mkt, horizon=H)
    claims = R.claims_analysis(ev_all[is_mask], cars[is_mask], H)          # exploratory, labeled as such
    spy = mkt.open["SPY"].shift(-1) / mkt.open["SPY"] - 1
    extra = {"calmar": S.calmar(net), "information_ratio_vs_spy": S.information_ratio(net, spy),
             **S.stationary_bootstrap_sharpe(net, n_boot=500 if a.fast else 2000), **R.tail_stats(net),
             "min_track_record_years": S.min_track_record_length(net) / 252}

    # ---------------- folk placebo (pre-registered)
    ev_folk = R.make_events(feat, sig, mkt, strat, signal_col="folk_signal")
    folk_eval = R.evaluate("FOLK_placebo", ev_folk, mkt, p, "IS", strat, factors=False)
    folk_tests = R.event_tests(ev_folk[ev_folk["sample"] == "IS"],
                               R.abnormal_paths(ev_folk, mkt)[ev_folk["sample"] == "IS"], H)
    R.log_variant("FOLK_placebo", cfg, folk_eval.summary)

    # ---------------- pre-declared robustness
    rows = [{"variant": "PRIMARY", **{k: prim.summary.get(k) for k in ("sharpe", "ann_return", "max_drawdown", "n_traded")}}]

    def add(name, ev, params, log=True):
        e = R.evaluate(name, ev, mkt, params, "IS", strat, factors=False)
        rows.append({"variant": name, **{k: e.summary.get(k) for k in ("sharpe", "ann_return", "max_drawdown", "n_traded")}})
        if log:
            R.log_variant(name, cfg, e.summary)
        return e

    add("costs_x2", ev_all, p.with_(cost_multiplier=2.0))
    for h in strat["robustness_predeclared"]["horizons"]:
        add(f"horizon_{h}", ev_all, p.with_(horizon=h))
    add("hedge_QQQ", ev_all, p.with_(hedge="QQQ"))
    add("earnings_included", ev_incl, p)
    # benchmarks: the unconditional interview effect (Kim & Meschke reversal) with no TELL information
    add("benchmark_short_every_interview", ev_all.assign(signal=-1.0), p)
    add("benchmark_long_every_interview", ev_all.assign(signal=1.0), p)
    short_only = ev_all.assign(signal=ev_all["signal"].clip(upper=0))
    add("short_only", short_only, p)
    add("stack_overlap", ev_all, p.with_(overlap="stack"))
    add("dd_brake_0.10", ev_all, p.with_(dd_brake=0.10))
    for v in ("no_incongruence", "equal_feature_weights", "face_only", "voice_only", "text_only"):
        sp_v = R.signal_params(strat, min_modalities=1, min_features=2) if v.endswith("_only") else sp
        sig_v = build_signals(feat, R.modify_spec(spec, v), sp_v)
        add(v, R.make_events(feat, sig_v, mkt, strat), p)
    for ceo in sorted(ev_all["ceo_id"].unique()):
        add(f"leave_out_{ceo}", ev_all[ev_all["ceo_id"] != ceo], p, log=False)
    ml = ev_all.copy()
    ml["signal"] = ml_ridge_signal(feat, sig, ev_all, cars, H)
    add("ml_ridge_secondary", ml.dropna(subset=["signal"]), p)
    robust = pd.DataFrame(rows)

    # ---------------- nulls
    nd = 60 if a.fast else 300
    nulls = {"permutation": R.permutation_null(ev_all, mkt, p, "IS", strat, n=nd),
             "random_dates": R.pseudo_event_null(ev_all, mkt, p, "IS", strat, n=nd)}
    trials, var_sr = R.n_trials()
    dsr = S.deflated_sharpe(net, trials, var_sr)
    by_year = (1 + net).groupby(net.index.year).prod() - 1
    cap = R.capacity(prim.result, mkt, prim.summary["sharpe"], prim.summary["gross_sharpe"],
                     prim.summary["ann_vol"], p.cost_bps_stock)
    stress = R.stress_table(net, mkt)
    spreads = R.spread_estimates(mkt, sorted(ev_all["ticker"].unique()) + ["SPY"], s["sample_start"], s["is_end"])
    per_ceo = (prim.result.events[prim.result.events["sized"]]
               .merge(ev_all[["event_id", "ceo_id"]], on="event_id")
               .groupby("ceo_id").agg(n=("event_id", "size"), pnl=("pnl_contrib", "sum"),
                                       hit=("signed_car", lambda x: float((x > 0).mean()))))

    # ---------------- out-of-sample (sealed)
    oos_daily, oos_summary = None, None
    if a.unlock_oos:
        why = R.config_hash(strat, spec)
        reason = oos_lock_check(why, a.relock)
        oe = R.evaluate("PRIMARY_OOS", ev_all, mkt, p, "OOS", strat)
        oe2 = R.evaluate("PRIMARY_OOS_x2", ev_all, mkt, p.with_(cost_multiplier=2.0), "OOS", strat, factors=False)
        oos_daily = oe.result.daily[(oe.result.daily.index >= pd.Timestamp(s["oos_start"])) &
                                    (oe.result.daily.index <= pd.Timestamp(s["oos_end"]))]
        oos_summary = {**oe.summary, "sharpe_costs_x2": oe2.summary["sharpe"],
                       "event_tests": R.event_tests(ev_all[~is_mask & (ev_all["sample"] == "OOS")],
                                                    cars[ev_all["sample"] == "OOS"], H)}
        log = RES / "oos_log.md"
        if not log.exists():
            log.write_text("# Out-of-sample evaluations (append-only)\n\n| time | git | config | reason | sharpe |\n|---|---|---|---|---|\n")
        with log.open("a") as fh:
            fh.write(f"| {datetime.now().isoformat(timespec='seconds')} | {git_hash()} | {why} | {reason} | "
                     f"{fmt(oe.summary['sharpe'])} |\n")
        (RES / "oos_summary.json").write_text(json.dumps(oos_summary, indent=2, default=str))

    # ---------------- outputs
    figures({"summary": prim.summary, "net": net, "gross": gross, "net_x2": net_x2}, ev_all, cars, decay, nulls,
            robust, {c: case_frame(c, ev_all, mkt) for c in strat["case_studies"]}, oos_daily)
    out = {"config_hash": cfg, "git": git_hash(), "price_source": mkt.source, "price_fingerprint": mkt.fingerprint,
           "funnel": corpus_funnel(feat_raw, qc, ev_all), "qc": qc, "events": {"total": int(len(ev_all)), "IS": int(is_mask.sum()),
                                "OOS": int((ev_all["sample"] == "OOS").sum()),
                                "excluded_near_earnings": int(len(ev_incl) - len(ev_all))},
           "primary_IS": prim.summary, "costs_x2_IS": x2.summary, "extra": extra, "event_tests_IS": ev_tests,
           "runup_control": runup, "volatility_mechanism_IS": vol_mech, "claims_exploratory_IS": claims, "folk_placebo": {"summary": folk_eval.summary, "event_tests": folk_tests},
           "dsr": dsr, "capacity": cap, "stress": stress.to_dict("records"), "spreads": spreads.to_dict("records"), "nulls": {k: {"mean": float(v.mean()), "p_ge_actual": float((v >= prim.summary["sharpe"]).mean())}
                                                 for k, v in nulls.items()},
           "by_year": by_year.round(5).to_dict(), "oos": oos_summary}
    (RES / "summary.json").write_text(json.dumps(out, indent=2, default=str))
    robust.to_csv(RES / "robustness.csv", index=False)
    stress.to_csv(RES / "stress_windows.csv", index=False)
    spreads.to_csv(RES / "spread_estimates.csv", index=False)
    decay.to_csv(RES / "alpha_decay.csv", index=False)
    per_ceo.to_csv(RES / "per_ceo.csv")
    ev_all.drop(columns=["video_ids"]).assign(**cars[["car_1", "car_5", f"car_{H}"]]).to_csv(RES / "events.csv", index=False)
    net.to_frame("net").join(gross.rename("gross")).join(net_x2.rename("net_costs_x2")).to_csv(RES / "daily_returns_IS.csv")

    ps = prim.summary
    md = [f"# PokerFace results ({'IS + OOS' if a.unlock_oos else 'in-sample only; OOS sealed'})",
          f"Generated {datetime.now():%Y-%m-%d %H:%M} | git {git_hash()} | config {cfg} | prices {mkt.source} "
          f"(fingerprint {mkt.fingerprint})", "",
          f"Events: {out['events']} | QC: {qc}", "",
          "| metric | in-sample | " + ("out-of-sample |" if oos_summary else ""),
          "|---|---|" + ("---|" if oos_summary else "")]
    for k, lab, pct in [("ann_return", "annualized return (net)", True), ("ann_vol", "volatility", True),
                        ("sharpe", "Sharpe (net)", False), ("gross_sharpe", "Sharpe (gross)", False),
                        ("max_drawdown", "max drawdown", True), ("calmar", "Calmar", False),
                        ("turnover_x_per_year", "turnover (x/yr)", False), ("n_traded", "events traded", False)]:
        v = ps.get(k, extra.get(k))
        row = f"| {lab} | {fmt(v, pct) if k != 'n_traded' else v} |"
        if oos_summary:
            ov = oos_summary.get(k)
            row += f" {fmt(ov, pct) if k != 'n_traded' else ov} |"
        md.append(row)
    md += ["", f"Costs x2 Sharpe (IS): {fmt(x2.summary['sharpe'])} | DSR: {fmt(dsr['dsr'])} over {trials} trials | "
               f"PSR(>0): {fmt(dsr['psr_vs_zero'])} | bootstrap Sharpe CI: [{fmt(extra['sharpe_ci_lo'])}, {fmt(extra['sharpe_ci_hi'])}]",
           f"FF5+Mom alpha: {fmt(ps.get('ff_alpha_annual'), True)} (t = {fmt(ps.get('ff_alpha_t'))}), R2 {fmt(ps.get('ff_r2'))}",
           f"Event IC (rank, {H}d): {fmt(ev_tests.get('ic_ic'), nd=3)} | tercile spread: {fmt(ev_tests.get('spread_long_minus_short'), True)} "
           f"CEO-clustered CI {ev_tests.get('spread_ci_ceo')} | hit rate {fmt(ev_tests.get('hit_rate'), True)}",
           f"Run-up control: beta_S t = {fmt(runup.get('t_s'))}, corr(S, run-up) = {fmt(runup.get('corr_s_runup'))}",
           f"Volatility mechanism (pred. 6): beta {fmt(vol_mech.get('beta_tell'), nd=3)}, CEO-clustered t = {fmt(vol_mech.get('t_tell_ceo_clustered'))}, n = {vol_mech.get('n')}",
           f"FOLK placebo Sharpe: {fmt(folk_eval.summary['sharpe'])} | IC {fmt(folk_tests.get('ic_ic'), nd=3)}",
           f"Nulls: " + ", ".join(f"{k} p = {v['p_ge_actual']:.2f}" for k, v in out["nulls"].items()),
           f"Capacity (net Sharpe = half gross): ${cap.get('aum_net_sharpe_half_gross', float('nan'))/1e6:,.0f}M",
           "", "## Robustness (in-sample, all logged as trials)", robust.round(3).to_markdown(index=False),
           "", "## Alpha decay", decay.round(3).to_markdown(index=False),
           "", "## Stress windows", stress.round(4).to_markdown(index=False),
           "", "## Cost justification: Abdi-Ranaldo effective spreads (bps), IS period", spreads.round(2).to_markdown(index=False),
           "", "## By year (net)", by_year.round(4).to_frame("return").to_markdown(),
           "", "## Per CEO", per_ceo.round(4).to_markdown()]
    (RES / "summary.md").write_text("\n".join(md))
    print("\n".join(md[:20]))


if __name__ == "__main__":
    main()
