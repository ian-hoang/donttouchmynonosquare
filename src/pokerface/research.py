"""Research pipeline: committed features + downloaded prices -> events -> backtest -> statistics.

Everything the quant note reports is produced by functions in this module, driven by run_all.py, from the
frozen configs (config/strategy.json, config/signal_spec.json).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

from . import stats as S
from .backtest import BTParams, BTResult, run_backtest
from .events import entry_session, near_earnings
from .signal import SignalParams, build_signals

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = __import__("os").environ.get("PF_UNIVERSE", "")      # "" = original 20 CEOs, "_h2" = Hypothesis 2 universe
RESULTS = ROOT / f"results{UNIVERSE}"
FACE_PREFIX, VOICE_PREFIX, TEXT_PREFIX = "fc_", "voc_", "txt_"


# ----------------------------------------------------------------------------- configuration

def load_configs() -> tuple[dict, dict]:
    strat = json.loads((ROOT / "config" / "strategy.json").read_text())
    spec = json.loads((ROOT / "config" / "signal_spec.json").read_text())
    return strat, spec


def config_hash(*objs) -> str:
    return hashlib.sha256(json.dumps(objs, sort_keys=True, default=str).encode()).hexdigest()[:12]


def bt_params(strat: dict, **overrides) -> BTParams:
    b = strat["backtest"]
    p = BTParams(horizon=b["horizon"], hedge=b["hedge"], signal_cap=b["signal_cap"],
                 target_vol_per_event=b["target_vol_per_event"], max_weight_per_event=b["max_weight_per_event"],
                 max_weight_per_name=b["max_weight_per_name"], max_gross=b["max_gross"],
                 beta_lookback=b["beta_lookback"], vol_lookback=b["vol_lookback"], min_history=b["min_history"],
                 cost_bps_stock=b["cost_bps_stock"], cost_bps_hedge=b["cost_bps_hedge"],
                 borrow_bps_annual_stock=b["borrow_bps_annual_stock"],
                 borrow_bps_annual_hedge=b["borrow_bps_annual_hedge"], dd_brake=b["dd_brake"],
                 overlap=strat["events"]["overlap"])
    return p.with_(**overrides) if overrides else p


def signal_params(strat: dict, **overrides) -> SignalParams:
    s = strat["signal"]
    kw = dict(window=s["baseline_window"], min_prior=s["min_prior"], z_clip=s["z_clip"], min_pool=s["min_pool"],
              min_features=s["min_features"], min_modalities=s["min_modalities"])
    kw.update(overrides)
    return SignalParams(**kw)


# ----------------------------------------------------------------------------- data

@dataclass
class Market:
    open: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    factors: pd.DataFrame
    earnings: pd.DataFrame
    source: str
    fingerprint: str = ""


def load_market(source: str = "yfinance") -> Market:
    m = ROOT / "data" / "market"
    px = pd.read_parquet(m / f"prices_{source}.parquet")
    meta = json.loads((m / "download_meta.json").read_text()) if (m / "download_meta.json").exists() else {}
    return Market(open=px["Open"], close=px["Close"], volume=px["Volume"],
                  factors=pd.read_parquet(m / "ff_factors.parquet"),
                  earnings=pd.read_parquet(m / "earnings_dates.parquet"), source=source,
                  fingerprint=meta.get("prices", {}).get("fingerprint", ""))


def load_features() -> pd.DataFrame:
    f = pd.read_csv(ROOT / "data" / "features" / f"video_features{UNIVERSE}.csv", dtype={"video_id": str})
    f["publish_ts_utc"] = pd.to_datetime(f["publish_ts_utc"], utc=True)
    return f


def apply_qc(f: pd.DataFrame, strat: dict) -> tuple[pd.DataFrame, dict]:
    """Pre-registered QC: drop failed identity, then blank modality blocks that lack enough evidence."""
    q = strat["qc"]
    n0 = len(f)
    f = f[f.get("qc_fail").isna()] if "qc_fail" in f else f
    f = f[f["id_cos"].fillna(1.0) >= q["min_id_cos"]].copy()
    face_cols = [c for c in f if c.startswith(FACE_PREFIX)]
    voc_cols = [c for c in f if c.startswith(VOICE_PREFIX) and c != "voc_seconds"]
    txt_cols = [c for c in f if c.startswith(TEXT_PREFIX)]
    no_face = f["face_minutes"].fillna(0) < q["min_face_minutes"]
    f.loc[no_face, face_cols] = np.nan
    if "fc_gesture_energy" in f:
        f.loc[f.get("fc_hands_visible", pd.Series(0, index=f.index)).fillna(0) < q["gesture_requires_hands_visible"],
              "fc_gesture_energy"] = np.nan
    f.loc[f["ceo_speech_s"].fillna(0) < q["min_ceo_speech_seconds"], voc_cols] = np.nan
    f.loc[f["n_words"].fillna(0) < q["min_ceo_words"], txt_cols] = np.nan
    return f, {"videos_in": n0, "after_identity_qc": len(f), "face_ok": int((~no_face).sum()),
               "voice_ok": int(f["voc_f0_mean_st"].notna().sum()) if "voc_f0_mean_st" in f else 0,
               "text_ok": int(f["txt_negation"].notna().sum()) if "txt_negation" in f else 0}


def folk_spec(spec: dict) -> dict:
    """Pre-registered placebo: equal-weight, sign +1 mean of the excluded folk-cue z-scores."""
    by_mod: dict[str, list] = {"face": [], "voice": [], "text": []}
    for c in spec["excluded_folk_cues"]:
        m = "face" if c["name"].startswith(FACE_PREFIX) else "voice" if c["name"].startswith(VOICE_PREFIX) else "text"
        by_mod[m].append({"name": c["name"], "sign": 1, "weight": 1.0})
    return {"modalities": {m: {"weight": 1.0, "features": fs} for m, fs in by_mod.items() if fs}}


def modify_spec(spec: dict, variant: str) -> dict:
    s = json.loads(json.dumps(spec))
    if variant == "no_incongruence":
        s.pop("incongruence", None)
    elif variant == "equal_feature_weights":
        for m in s["modalities"].values():
            for f in m["features"]:
                f["weight"] = 1.0
    elif variant in ("face_only", "voice_only", "text_only"):
        keep = variant.split("_")[0]
        s["modalities"] = {keep: s["modalities"][keep]}
        s.pop("incongruence", None)
    return s


# ----------------------------------------------------------------------------- events

def make_events(feat: pd.DataFrame, sig: pd.DataFrame, mkt: Market, strat: dict, signal_col: str = "signal",
                exclude_earnings: bool = True) -> pd.DataFrame:
    """One row per (CEO, entry session): averaged signal, flags, and the sample it belongs to."""
    sessions = mkt.open.dropna(how="all").index
    df = sig[["video_id", "ceo_id", "ticker", "publish_ts_utc", signal_col, "tell"]].copy()
    df["entry"] = entry_session(df["publish_ts_utc"], sessions)
    df = df.dropna(subset=["entry", signal_col])
    g = df.groupby(["ceo_id", "ticker", "entry"], as_index=False).agg(
        signal=(signal_col, "mean"), tell=("tell", "mean"), n_videos=("video_id", "size"),
        video_ids=("video_id", lambda x: ",".join(x)), publish_ts_utc=("publish_ts_utc", "min"))
    w = strat["events"]["exclude_earnings_window_sessions"]
    g["near_earnings"] = near_earnings(g["entry"], g["ticker"], mkt.earnings, sessions, window=w)
    if exclude_earnings:
        g = g[~g["near_earnings"]]
    s = strat["samples"]
    g["sample"] = np.where(g["entry"] <= pd.Timestamp(s["is_end"]), "IS",
                           np.where(g["entry"] >= pd.Timestamp(s["oos_start"]), "OOS", "gap"))
    g = g[(g["entry"] >= pd.Timestamp(s["sample_start"])) & (g["entry"] <= pd.Timestamp(s["oos_end"]))]
    g = g.sort_values("entry").reset_index(drop=True)
    g["event_id"] = np.arange(len(g))
    return g


def abnormal_paths(ev: pd.DataFrame, mkt: Market, hedge: str = "SPY", max_h: int = 60,
                   beta_lookback: int = 252) -> pd.DataFrame:
    """Beta-hedged open-to-open cumulative abnormal returns for horizons 1..max_h (sizing-free)."""
    o, c = mkt.open, mkt.close
    r_oo = o.shift(-1) / o - 1.0
    r_cc = c.pct_change()
    pos = {d: i for i, d in enumerate(o.index)}
    out = np.full((len(ev), max_h), np.nan)
    for k, e in enumerate(ev.itertuples(index=False)):
        if e.entry not in pos or e.ticker not in o:
            continue
        i0 = pos[e.entry]
        y = r_cc[e.ticker].values[max(0, i0 - beta_lookback):i0]
        x = r_cc[hedge].values[max(0, i0 - beta_lookback):i0]
        m = np.isfinite(y) & np.isfinite(x)
        beta = float(np.clip(np.cov(y[m], x[m])[0, 1] / np.var(x[m], ddof=1), 0.3, 2.5)) if m.sum() > 60 else 1.0
        ar = r_oo[e.ticker].values[i0:i0 + max_h] - beta * r_oo[hedge].values[i0:i0 + max_h]
        ar = np.where(np.isfinite(ar), ar, 0.0)
        out[k, :len(ar)] = np.cumsum(ar)
    return pd.DataFrame(out, index=ev.index, columns=[f"car_{h}" for h in range(1, max_h + 1)])


# ----------------------------------------------------------------------------- evaluation

@dataclass
class Evaluation:
    name: str
    sample: str
    summary: dict
    result: BTResult
    events: pd.DataFrame
    extras: dict = field(default_factory=dict)


def evaluate(name: str, ev: pd.DataFrame, mkt: Market, p: BTParams, sample: str, strat: dict,
             factors: bool = True) -> Evaluation:
    e = ev[ev["sample"] == sample]
    res = run_backtest(mkt.open, mkt.close, e[["event_id", "ticker", "entry", "signal"]], p)
    s = strat["samples"]
    lo, hi = (s["sample_start"], s["is_end"]) if sample == "IS" else (s["oos_start"], s["oos_end"])
    r = res.daily[(res.daily.index >= pd.Timestamp(lo)) & (res.daily.index <= pd.Timestamp(hi))]
    gross = res.gross_daily.reindex(r.index)
    summ = S.summarize(r, res.turnover_per_year * len(res.daily) / max(len(r), 1), label=name)
    summ.update({"n_events": int(len(e)), "n_traded": int(res.events["sized"].sum()) if len(res.events) else 0,
                 "gross_sharpe": S.sharpe(gross), "gross_ann_return": S.annualized_return(gross),
                 "total_cost_drag_annual": float((gross - r).mean() * 252)})
    if factors:
        summ.update({f"ff_{k}": v for k, v in S.factor_regression(r, mkt.factors).items()})
    return Evaluation(name, sample, summ, res, e)


def event_tests(ev: pd.DataFrame, cars: pd.DataFrame, horizon: int, seed: int = 3) -> dict:
    """IC, tercile spread with clustered bootstrap, hit rate (sizing-free, event level)."""
    y = cars[f"car_{horizon}"]
    d = pd.DataFrame({"s": ev["signal"], "y": y, "ceo": ev["ceo_id"], "date": ev["entry"]}).dropna()
    out = {"n": int(len(d))}
    if len(d) < 15:
        return out
    out.update({f"ic_{k}": v for k, v in S.information_coefficient(d["s"], d["y"], d["ceo"]).items()})
    d["tercile"] = pd.qcut(d["s"].rank(method="first"), 3, labels=["low_S(high_tell)", "mid", "high_S(low_tell)"])
    t = d.groupby("tercile", observed=True)["y"].agg(["mean", "count"])
    out["tercile_mean_car"] = t["mean"].round(5).to_dict()
    out["tercile_n"] = t["count"].astype(int).to_dict()
    hi, lo = d[d["tercile"] == "high_S(low_tell)"], d[d["tercile"] == "low_S(high_tell)"]
    out["spread_long_minus_short"] = float(hi["y"].mean() - lo["y"].mean())
    rng = np.random.default_rng(seed)
    for cl in ("ceo", "date"):
        groups_hi = [g["y"].values for _, g in hi.groupby(cl)]
        groups_lo = [g["y"].values for _, g in lo.groupby(cl)]
        if len(groups_hi) < 3 or len(groups_lo) < 3:
            continue
        boots = []
        for _ in range(3000):
            bh = np.concatenate([groups_hi[i] for i in rng.integers(len(groups_hi), size=len(groups_hi))])
            bl = np.concatenate([groups_lo[i] for i in rng.integers(len(groups_lo), size=len(groups_lo))])
            boots.append(bh.mean() - bl.mean())
        boots = np.array(boots)
        out[f"spread_ci_{cl}"] = [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))]
        out[f"spread_p_{cl}"] = float(2 * min((boots <= 0).mean(), (boots >= 0).mean()))
    out["hit_rate"] = float((np.sign(d["s"]) == np.sign(d["y"])).mean())
    out["signed_car_mean"] = float((np.sign(d["s"]) * d["y"]).mean())
    return out


def permutation_null(ev: pd.DataFrame, mkt: Market, p: BTParams, sample: str, strat: dict, n: int = 200,
                     seed: int = 17) -> np.ndarray:
    """Strategy Sharpe when signals are shuffled within each CEO (keeps timing, names, sizing)."""
    rng = np.random.default_rng(seed)
    e = ev[ev["sample"] == sample].copy()
    out = []
    for _ in range(n):
        e2 = e.copy()
        e2["signal"] = e2.groupby("ceo_id")["signal"].transform(lambda x: rng.permutation(x.values))
        out.append(evaluate("perm", e2, mkt, p, sample, strat, factors=False).summary["sharpe"])
    return np.array(out)


def pseudo_event_null(ev: pd.DataFrame, mkt: Market, p: BTParams, sample: str, strat: dict, n: int = 200,
                      seed: int = 23) -> np.ndarray:
    """Strategy Sharpe when each event is moved to a random session of the same year (same name, same signal)."""
    rng = np.random.default_rng(seed)
    e = ev[ev["sample"] == sample].copy()
    sess = mkt.open.dropna(how="all").index
    by_year = {y: sess[sess.year == y] for y in sorted(set(sess.year))}
    out = []
    for _ in range(n):
        e2 = e.copy()
        e2["entry"] = [by_year[d.year][rng.integers(len(by_year[d.year]))] for d in e2["entry"]]
        out.append(evaluate("pseudo", e2, mkt, p, sample, strat, factors=False).summary["sharpe"])
    return np.array(out)


def capacity(ev_res: BTResult, mkt: Market, net_sharpe: float, gross_sharpe: float, strat_vol: float,
             fixed_bps: float, y_coef: float = 0.7) -> dict:
    """Square-root impact: cost/trade = fixed + Y * sigma_daily * sqrt(Q / ADV). Capacity = AUM where the
    net Sharpe falls to half the gross Sharpe."""
    w = ev_res.weights
    names = [c for c in w.columns if c not in ("SPY", "QQQ")]
    adv = (mkt.close[names] * mkt.volume[names]).rolling(63).median()
    sig = mkt.close[names].pct_change().rolling(63).std()
    trades = w[names].diff().abs()
    turnover_annual = float(trades.sum().sum() / (len(w) / 252))
    out = {"turnover_x_per_year": turnover_annual}
    if turnover_annual <= 0 or not np.isfinite(gross_sharpe):
        return out
    mask = trades > 0
    part = (trades / adv.reindex_like(trades))[mask]
    med_sig = float(sig.reindex_like(trades)[mask].stack().median())
    med_adv = float(adv.reindex_like(trades)[mask].stack().median())
    med_trade_w = float(trades[mask].stack().median())
    gross_ret = gross_sharpe * strat_vol

    def net_sharpe_at(aum):
        impact_bps = y_coef * med_sig * np.sqrt(aum * med_trade_w / med_adv) * 1e4
        drag = turnover_annual * (fixed_bps + impact_bps) / 1e4
        return (gross_ret - drag) / strat_vol if strat_vol > 0 else np.nan

    grid = np.logspace(5, 11, 61)
    curve = [(a, net_sharpe_at(a)) for a in grid]
    half = next((a for a, s in curve if s <= 0.5 * gross_sharpe), np.nan)
    zero = next((a for a, s in curve if s <= 0), np.nan)
    out.update({"median_adv_usd": med_adv, "median_daily_vol": med_sig, "median_trade_weight": med_trade_w,
                "aum_net_sharpe_half_gross": float(half), "aum_net_sharpe_zero": float(zero),
                "participation_at_10m": float(1e7 * med_trade_w / med_adv),
                "curve": [(float(a), float(s)) for a, s in curve[::6]]})
    return out


def tail_stats(r: pd.Series) -> dict:
    x = pd.Series(r).dropna()
    x = x[x != 0] if (x != 0).sum() > 50 else x
    out = {}
    for q in (0.95, 0.99):
        var = float(-np.quantile(x, 1 - q))
        out[f"var_{int(q*100)}"] = var
        out[f"cvar_{int(q*100)}"] = float(-x[x <= -var].mean()) if (x <= -var).any() else np.nan
    out["worst_day"] = float(x.min())
    out["best_day"] = float(x.max())
    m = (1 + pd.Series(r).fillna(0)).groupby(pd.Series(r).index.to_period("M")).prod() - 1
    out["pct_months_positive"] = float((m > 0).mean())
    return out


def alpha_decay(ev: pd.DataFrame, cars: pd.DataFrame, horizons=(1, 2, 3, 5, 10, 20, 40, 60)) -> pd.DataFrame:
    rows = []
    for h in horizons:
        y = cars[f"car_{h}"]
        d = pd.DataFrame({"s": ev["signal"], "y": y}).dropna()
        if len(d) < 15:
            continue
        sc = np.sign(d["s"]) * d["y"]
        rows.append({"h": h, "signed_car_bps": float(sc.mean() * 1e4),
                     "t": float(sc.mean() / (sc.std(ddof=1) / np.sqrt(len(sc)))) if sc.std() > 0 else np.nan,
                     "ic": float(sps.spearmanr(d["s"], d["y"]).statistic), "n": int(len(d))})
    return pd.DataFrame(rows)


def runup_control(ev: pd.DataFrame, cars: pd.DataFrame, mkt: Market, horizon: int) -> dict:
    """Kill-condition check: does S still predict CAR after controlling for the 5-day pre-entry run-up?"""
    import statsmodels.api as sm

    o = mkt.open
    pos = {d: i for i, d in enumerate(o.index)}
    run = []
    for e in ev.itertuples(index=False):
        i = pos.get(e.entry)
        ok = i is not None and i >= 6 and e.ticker in o
        run.append(float(o[e.ticker].iloc[i] / o[e.ticker].iloc[i - 5] - o["SPY"].iloc[i] / o["SPY"].iloc[i - 5])
                   if ok else np.nan)
    d = pd.DataFrame({"y": cars[f"car_{horizon}"], "s": ev["signal"], "runup": run, "ceo": ev["ceo_id"]}).dropna()
    if len(d) < 30:
        return {"n": int(len(d))}
    x = sm.add_constant(d[["s", "runup"]])
    res = sm.OLS(d["y"], x).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["ceo"])[0]})
    return {"n": int(len(d)), "beta_s": float(res.params["s"]), "t_s": float(res.tvalues["s"]),
            "beta_runup": float(res.params["runup"]), "t_runup": float(res.tvalues["runup"]),
            "corr_s_runup": float(d["s"].corr(d["runup"]))}


def volatility_mechanism(ev: pd.DataFrame, mkt: Market, horizon: int = 20, pre: int = 60, hedge: str = "SPY") -> dict:
    """Pre-registered prediction 6: high TELL predicts higher subsequent idiosyncratic volatility.
    y = log(RV_idio[entry, entry+h-1] / RV_idio[entry-pre, entry-1]); residuals use the pre-window beta vs SPY.
    OLS of y on TELL with CEO-clustered standard errors, plus a rank correlation."""
    import statsmodels.api as sm

    r = mkt.close.pct_change()
    pos = {d: i for i, d in enumerate(mkt.close.index)}
    ys, tells, ceos = [], [], []
    for e in ev.itertuples(index=False):
        i0 = pos.get(e.entry)
        if i0 is None or i0 < pre + 5 or i0 + horizon >= len(r) or e.ticker not in r or not np.isfinite(e.tell):
            continue
        y_pre, x_pre = r[e.ticker].values[i0 - pre:i0], r[hedge].values[i0 - pre:i0]
        m = np.isfinite(y_pre) & np.isfinite(x_pre)
        if m.sum() < 40:
            continue
        b = np.cov(y_pre[m], x_pre[m])[0, 1] / np.var(x_pre[m], ddof=1)
        res_pre = y_pre[m] - b * x_pre[m]
        y_post, x_post = r[e.ticker].values[i0:i0 + horizon], r[hedge].values[i0:i0 + horizon]
        mp = np.isfinite(y_post) & np.isfinite(x_post)
        res_post = y_post[mp] - b * x_post[mp]
        if res_pre.std() <= 0 or res_post.std() <= 0:
            continue
        ys.append(np.log(res_post.std() / res_pre.std()))
        tells.append(e.tell)
        ceos.append(e.ceo_id)
    d = pd.DataFrame({"y": ys, "tell": tells, "ceo": ceos})
    if len(d) < 30:
        return {"n": int(len(d))}
    fit = sm.OLS(d["y"], sm.add_constant(d[["tell"]])).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["ceo"])[0]})
    q = pd.qcut(d["tell"].rank(method="first"), 3, labels=["low", "mid", "high"])
    return {"n": int(len(d)), "beta_tell": float(fit.params["tell"]), "t_tell_ceo_clustered": float(fit.tvalues["tell"]),
            "spearman": float(sps.spearmanr(d["tell"], d["y"]).statistic),
            "mean_log_rv_ratio_by_tell_tercile": d.groupby(q, observed=True)["y"].mean().round(4).to_dict()}


def claims_analysis(ev: pd.DataFrame, cars: pd.DataFrame, horizon: int, seed: int = 5) -> dict:
    """EXPLORATORY (not pre-registered): what the CEO says (LLM labels on masked transcripts) x how stressed
    they sound (TELL). Event-level 20-day beta-hedged CAR by denial presence and by denial x TELL tercile, with
    CEO-clustered bootstrap CIs. Labels: data/features/utterance_labels.csv."""
    p = ROOT / "data" / "features" / "utterance_labels.csv"
    if not p.exists():
        return {"available": False}
    lab = pd.read_csv(p, dtype={"video_id": str})
    first = ev["video_ids"].str.split(",").str[0]
    d = ev.assign(video_id=first.values, car=cars[f"car_{horizon}"].values).merge(lab, on="video_id", how="inner")
    if len(d) < 40:
        return {"available": True, "n": int(len(d))}
    d["has_denial"] = d["denials"] > 0
    d["tell_t"] = pd.qcut(d["tell"].rank(method="first"), 3, labels=["low", "mid", "high"])
    rng = np.random.default_rng(seed)

    def ci(x: pd.DataFrame) -> list:
        g = [v["car"].values for _, v in x.groupby("ceo_id")]
        if len(g) < 3:
            return [float("nan"), float("nan")]
        b = [np.concatenate([g[i] for i in rng.integers(len(g), size=len(g))]).mean() for _ in range(2000)]
        return [float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))]

    out = {"available": True, "n": int(len(d)), "share_with_denial": float(d["has_denial"].mean()),
           "leak_rate_speaker_identifiable": float(d["speaker_identifiable"].astype(str).str.lower().eq("true").mean())}
    for k, sub in {"denial": d[d["has_denial"]], "no_denial": d[~d["has_denial"]],
                   "denial_high_tell": d[d["has_denial"] & (d["tell_t"] == "high")],
                   "denial_low_tell": d[d["has_denial"] & (d["tell_t"] == "low")],
                   "promises_high_tell": d[(d["forward_promises"] > d["forward_promises"].median()) & (d["tell_t"] == "high")],
                   "promises_low_tell": d[(d["forward_promises"] > d["forward_promises"].median()) & (d["tell_t"] == "low")]}.items():
        out[f"car_{k}"] = float(sub["car"].mean()) if len(sub) else float("nan")
        out[f"n_{k}"] = int(len(sub))
        out[f"ci_{k}"] = ci(sub) if len(sub) >= 10 else [float("nan"), float("nan")]
    return out


STRESS_WINDOWS = {
    "2018Q4 selloff": ("2018-10-01", "2018-12-24"),
    "COVID crash": ("2020-02-19", "2020-03-23"),
    "2022 bear market": ("2022-01-03", "2022-10-12"),
    "SVB crisis": ("2023-03-08", "2023-03-24"),
    "Aug-2024 vol spike": ("2024-07-16", "2024-08-07"),
}


def stress_table(r: pd.Series, mkt: Market) -> pd.DataFrame:
    spy = mkt.open["SPY"].shift(-1) / mkt.open["SPY"] - 1
    rows = []
    for name, (a, b) in STRESS_WINDOWS.items():
        m = (r.index >= pd.Timestamp(a)) & (r.index <= pd.Timestamp(b))
        if not m.any():
            continue
        rs, sp = r[m].fillna(0), spy.reindex(r.index)[m].fillna(0)
        rows.append({"window": name, "start": a, "end": b, "strategy": float((1 + rs).prod() - 1),
                     "spy": float((1 + sp).prod() - 1), "strategy_max_dd": S.max_drawdown(rs),
                     "days_with_position": int((rs != 0).sum())})
    return pd.DataFrame(rows)


def spread_estimates(mkt: Market, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Abdi & Ranaldo (2017) close-high-low effective spread estimator from daily bars (no quote data needed):
    s^2 = 4 E[(c_t - eta_t)(c_t - eta_{t+1})], eta = (log high + log low) / 2, monthly windows, negatives set to 0."""
    px = pd.read_parquet(ROOT / "data" / "market" / f"prices_{mkt.source}.parquet")
    out = []
    for t in tickers:
        if t not in px["Close"]:
            continue
        h, l, c = (np.log(px[f][t]) for f in ("High", "Low", "Close"))
        sl = slice(pd.Timestamp(start), pd.Timestamp(end))
        h, l, c = h.loc[sl], l.loc[sl], c.loc[sl]
        eta = (h + l) / 2
        prod = (c - eta) * (c - eta.shift(-1))
        monthly = prod.groupby(prod.index.to_period("M")).mean()
        s = np.sqrt((4 * monthly).clip(lower=0))
        out.append({"ticker": t, "effective_spread_bps_median": float(s.median() * 1e4),
                    "half_spread_bps_median": float(s.median() * 1e4 / 2)})
    return pd.DataFrame(out)


# ----------------------------------------------------------------------------- variants log (DSR trial count)

def log_variant(name: str, cfg_hash: str, summ: dict, sample: str = "IS") -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / "variants_log.csv"
    row = pd.DataFrame([{"time": pd.Timestamp.now(tz="America/New_York").isoformat(timespec="seconds"),
                         "variant": name, "config_hash": cfg_hash, "sample": sample,
                         "sharpe": summ.get("sharpe"), "n_events": summ.get("n_events")}])
    row.to_csv(p, mode="a", header=not p.exists(), index=False)


def n_trials() -> tuple[int, float]:
    """Unique (variant, config) pairs evaluated in-sample, and the variance of their daily Sharpe estimates."""
    p = RESULTS / "variants_log.csv"
    if not p.exists():
        return 1, np.nan
    v = pd.read_csv(p)
    v = v[v["sample"] == "IS"].drop_duplicates(["variant", "config_hash"], keep="last")
    srs = v["sharpe"].dropna() / np.sqrt(252)
    return max(len(v), 1), float(srs.var(ddof=1)) if len(srs) > 2 else np.nan
