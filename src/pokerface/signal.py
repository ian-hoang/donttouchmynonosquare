"""Baseline-relative tell score.

For CEO c and video i published at t_i, every feature is scored against that CEO's own previous videos
(publish time strictly before t_i, last `window` of them, at least `min_prior`):

    z_ik = clip((x_ik - median_prior_k) / (1.4826 * MAD_prior_k), -3, 3)

Modality score m = weighted mean of sign_k * z_ik over the modality's available features; the tell score T
is the weighted mean over available modalities. The trade signal is s_i = -T_i / sigma_T, where sigma_T is
the pooled standard deviation of all tell scores published before t_i (expanding, >= `min_pool`). High
tell (stress / incongruence vs. one's own baseline) => negative signal => short the stock, hedged.

Nothing here is fitted to returns: signs and weights come from config/signal_spec.json, written from
published effect sizes before any backtest (see HYPOTHESIS.md).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SignalParams:
    window: int = 30          # prior videos in the CEO baseline
    min_prior: int = 5        # burn-in: need this many prior videos
    z_clip: float = 3.0
    min_pool: int = 20        # prior tell scores needed to standardize T
    min_features: int = 5     # need at least this many scorable features in a video (pre-registered)
    min_modalities: int = 2   # ... spread across at least this many of face/voice/text


def load_spec(path: Path | str = ROOT / "config" / "signal_spec.json") -> dict:
    return json.loads(Path(path).read_text())


def _robust_z(x: float, prior: np.ndarray, clip: float) -> float:
    prior = prior[np.isfinite(prior)]
    if len(prior) < 3 or not np.isfinite(x):
        return np.nan
    med = np.median(prior)
    mad = 1.4826 * np.median(np.abs(prior - med))
    if mad <= 1e-12:
        sd = np.std(prior, ddof=1)
        if not np.isfinite(sd) or sd <= 1e-12:
            return np.nan
        mad = sd
    return float(np.clip((x - med) / mad, -clip, clip))


def baseline_z(features: pd.DataFrame, cols: list[str], p: SignalParams = SignalParams()) -> pd.DataFrame:
    """Per-video robust z-scores vs. the same CEO's strictly-earlier videos. Index preserved."""
    df = features.sort_values("publish_ts_utc")
    out = pd.DataFrame(index=df.index, columns=cols, dtype=float)
    n_prior = pd.Series(0, index=df.index)
    for _, g in df.groupby("ceo_id", sort=False):
        ts = pd.to_datetime(g["publish_ts_utc"], utc=True).values
        X = g[cols].to_numpy(dtype=float)
        for r in range(len(g)):
            prior_mask = ts < ts[r]                                     # strictly earlier only
            idx = np.flatnonzero(prior_mask)[-p.window:]
            n_prior.loc[g.index[r]] = len(idx)
            if len(idx) < p.min_prior:
                continue
            for k, c in enumerate(cols):
                out.loc[g.index[r], c] = _robust_z(X[r, k], X[idx, k], p.z_clip)
    out["n_prior"] = n_prior
    return out.reindex(features.index)


def tell_score(z: pd.DataFrame, spec: dict, p: SignalParams = SignalParams()) -> pd.DataFrame:
    """Weighted, signed combination of z-scores into modality scores and the composite tell T."""
    mods = {}
    for m, mspec in spec["modalities"].items():
        num = pd.Series(0.0, index=z.index)
        den = pd.Series(0.0, index=z.index)
        cnt = pd.Series(0, index=z.index)
        for f in mspec["features"]:
            if f["name"] not in z.columns:
                continue
            v = z[f["name"]]
            ok = v.notna()
            num[ok] += f["weight"] * f["sign"] * v[ok]
            den[ok] += f["weight"]
            cnt[ok] += 1
        mods[m] = (num / den.replace(0, np.nan), cnt)
    res = pd.DataFrame({f"m_{m}": s for m, (s, _) in mods.items()})
    n_feat = sum(c for _, c in mods.values())
    num = pd.Series(0.0, index=z.index)
    den = pd.Series(0.0, index=z.index)
    for m, mspec in spec["modalities"].items():
        s = res[f"m_{m}"]
        ok = s.notna()
        num[ok] += mspec["weight"] * s[ok]
        den[ok] += mspec["weight"]
    if "incongruence" in spec:
        inc = spec["incongruence"]
        a, b = z.get(inc["verbal_positive"]), res.get(f"m_{inc['nonverbal_modality']}")
        if a is not None and b is not None:
            # positive words while the face/voice show stress: product is large only when both are high
            term = (a.clip(lower=0) * b.clip(lower=0)).where(a.notna() & b.notna())
            ok = term.notna()
            num[ok] += inc["weight"] * term[ok]
            den[ok] += inc["weight"]
            res["incongruence"] = term
    n_mod = sum(res[f"m_{m}"].notna().astype(int) for m in spec["modalities"])
    res["tell"] = (num / den.replace(0, np.nan)).where((n_feat >= p.min_features) & (n_mod >= p.min_modalities))
    res["n_features"] = n_feat
    res["n_modalities"] = n_mod
    return res


def trade_signal(features: pd.DataFrame, tell: pd.Series, p: SignalParams = SignalParams()) -> pd.Series:
    """s_i = -T_i / sigma(T_j : t_j < t_i), pooled across CEOs, expanding."""
    ts = pd.to_datetime(features["publish_ts_utc"], utc=True)
    order = ts.sort_values().index
    vals = tell.reindex(order).to_numpy(dtype=float)
    tsv = ts.reindex(order).values
    out = np.full(len(order), np.nan)
    for i in range(len(order)):
        prior = vals[(tsv < tsv[i]) & np.isfinite(vals)]
        if len(prior) < p.min_pool or not np.isfinite(vals[i]):
            continue
        sd = np.std(prior, ddof=1)
        if sd > 1e-12:
            out[i] = -vals[i] / sd
    return pd.Series(out, index=order).reindex(features.index)


def build_signals(features: pd.DataFrame, spec: dict, p: SignalParams = SignalParams()) -> pd.DataFrame:
    cols = [f["name"] for m in spec["modalities"].values() for f in m["features"]]
    if "incongruence" in spec:
        cols.append(spec["incongruence"]["verbal_positive"])
    cols = [c for c in dict.fromkeys(cols) if c in features.columns]
    z = baseline_z(features, cols, p)
    t = tell_score(z, spec, p)
    out = pd.concat([features[["video_id", "ceo_id", "ticker", "publish_ts_utc"]], z.add_prefix("z_"), t], axis=1)
    out["signal"] = trade_signal(features, t["tell"], p)
    return out
