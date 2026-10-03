"""Performance and overfitting statistics.

Everything here is a pure function of a return series (or a matrix of variant returns), so the numbers in
the quant note can be recomputed from `results/daily_returns.csv` alone.

References
- Bailey & Lopez de Prado (2012), "The Sharpe Ratio Efficient Frontier" (PSR, MinTRL).
- Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio" (DSR).
- Bailey, Borwein, Lopez de Prado & Zhu (2017), "The Probability of Backtest Overfitting" (PBO via CSCV).
- Politis & Romano (1994), stationary bootstrap.
- Newey & West (1987), HAC standard errors.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
from scipy import stats as sps

TRADING_DAYS = 252
EULER_GAMMA = 0.5772156649015329


# ----------------------------------------------------------------------------- basic performance

def annualized_return(r: pd.Series) -> float:
    r = pd.Series(r).dropna()
    if len(r) == 0:
        return float("nan")
    growth = float(np.prod(1.0 + r.values))
    return growth ** (TRADING_DAYS / len(r)) - 1.0


def annualized_vol(r: pd.Series) -> float:
    r = pd.Series(r).dropna()
    return float(r.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(r) > 1 else float("nan")


def sharpe(r: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Annualized Sharpe of excess returns (inputs are already market-hedged strategy returns)."""
    r = pd.Series(r).dropna()
    sd = r.std(ddof=1)
    if len(r) < 2 or sd == 0 or not np.isfinite(sd):
        return float("nan")
    return float(r.mean() / sd * math.sqrt(periods))


def max_drawdown(r: pd.Series) -> float:
    eq = (1.0 + pd.Series(r).fillna(0.0)).cumprod()
    peak = eq.cummax()
    return float((eq / peak - 1.0).min())


def worst_month(r: pd.Series) -> float:
    r = pd.Series(r).fillna(0.0)
    if not isinstance(r.index, pd.DatetimeIndex) or len(r) == 0:
        return float("nan")
    m = (1.0 + r).groupby(r.index.to_period("M")).prod() - 1.0
    return float(m.min())


def summarize(r: pd.Series, turnover_per_year: float | None = None, label: str = "") -> dict:
    """The minimum the track asks for: ann. return, vol, Sharpe, max DD, turnover (+ extras)."""
    r = pd.Series(r).dropna()
    active = (r != 0).mean() if len(r) else float("nan")
    out = {
        "label": label,
        "start": str(r.index.min().date()) if len(r) and isinstance(r.index, pd.DatetimeIndex) else "",
        "end": str(r.index.max().date()) if len(r) and isinstance(r.index, pd.DatetimeIndex) else "",
        "days": int(len(r)),
        "ann_return": annualized_return(r),
        "ann_vol": annualized_vol(r),
        "sharpe": sharpe(r),
        "max_drawdown": max_drawdown(r),
        "worst_month": worst_month(r),
        "skew": float(sps.skew(r, bias=False)) if len(r) > 2 else float("nan"),
        "kurtosis": float(sps.kurtosis(r, fisher=False, bias=False)) if len(r) > 3 else float("nan"),
        "frac_days_active": float(active),
    }
    if turnover_per_year is not None:
        out["turnover_x_per_year"] = float(turnover_per_year)
    return out


# ----------------------------------------------------------------------------- Sharpe inference

def _sr_moments(r: pd.Series) -> tuple[float, float, float, int]:
    r = pd.Series(r).dropna().values
    t = len(r)
    sd = r.std(ddof=1)
    sr = r.mean() / sd if sd > 0 else 0.0  # per-period, NOT annualized
    g3 = float(sps.skew(r, bias=False)) if t > 2 else 0.0
    g4 = float(sps.kurtosis(r, fisher=False, bias=False)) if t > 3 else 3.0
    return float(sr), g3, g4, t


def probabilistic_sharpe(r: pd.Series, sr_benchmark_per_period: float = 0.0) -> float:
    """PSR: P(true SR > benchmark) accounting for sample length, skew and kurtosis."""
    sr, g3, g4, t = _sr_moments(r)
    denom = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr
    if t < 3 or denom <= 0:
        return float("nan")
    z = (sr - sr_benchmark_per_period) * math.sqrt(t - 1) / math.sqrt(denom)
    return float(sps.norm.cdf(z))


def expected_max_sharpe(n_trials: int, var_sr_per_period: float) -> float:
    """E[max SR] of n_trials unskilled strategies (per-period units), Bailey & Lopez de Prado (2014)."""
    n = max(int(n_trials), 1)
    if n == 1:
        return 0.0
    z1 = sps.norm.ppf(1.0 - 1.0 / n)
    z2 = sps.norm.ppf(1.0 - 1.0 / (n * math.e))
    return float(math.sqrt(max(var_sr_per_period, 0.0)) * ((1.0 - EULER_GAMMA) * z1 + EULER_GAMMA * z2))


def deflated_sharpe(r: pd.Series, n_trials: int, var_sr_trials_per_period: float | None = None) -> dict:
    """DSR = PSR evaluated at the expected maximum Sharpe of `n_trials` null strategies.

    If the cross-trial variance of Sharpe estimates is unknown we use the null sampling variance of a
    Sharpe estimate, (1 + SR^2/2)/(T-1), which is conservative when trials are highly correlated.
    """
    sr, g3, g4, t = _sr_moments(r)
    if var_sr_trials_per_period is None or not np.isfinite(var_sr_trials_per_period):
        var_sr_trials_per_period = (1.0 + 0.5 * sr * sr) / max(t - 1, 1)
    sr_star = expected_max_sharpe(n_trials, var_sr_trials_per_period)
    return {
        "n_trials": int(n_trials),
        "sr_annual": sr * math.sqrt(TRADING_DAYS),
        "sr_star_annual": sr_star * math.sqrt(TRADING_DAYS),
        "dsr": probabilistic_sharpe(r, sr_star),
        "psr_vs_zero": probabilistic_sharpe(r, 0.0),
    }


def min_track_record_length(r: pd.Series, sr_benchmark_per_period: float = 0.0, alpha: float = 0.05) -> float:
    """Number of observations needed for PSR >= 1-alpha (Bailey & Lopez de Prado 2012)."""
    sr, g3, g4, _ = _sr_moments(r)
    if sr <= sr_benchmark_per_period:
        return float("inf")
    za = sps.norm.ppf(1.0 - alpha)
    return float(1.0 + (1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr) * (za / (sr - sr_benchmark_per_period)) ** 2)


# ----------------------------------------------------------------------------- bootstrap / permutation

def stationary_bootstrap_sharpe(r: pd.Series, n_boot: int = 2000, mean_block: int = 10, seed: int = 7) -> dict:
    """Politis-Romano stationary bootstrap CI for the annualized Sharpe (keeps serial dependence)."""
    x = pd.Series(r).dropna().values
    t = len(x)
    if t < 20:
        return {"sharpe_ci_lo": float("nan"), "sharpe_ci_hi": float("nan"), "p_sharpe_le_0": float("nan")}
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_block
    out = np.empty(n_boot)
    for b in range(n_boot):
        idx = np.empty(t, dtype=np.int64)
        idx[0] = rng.integers(t)
        jumps = rng.random(t) < p
        starts = rng.integers(t, size=t)
        for i in range(1, t):
            idx[i] = starts[i] if jumps[i] else (idx[i - 1] + 1) % t
        s = x[idx]
        sd = s.std(ddof=1)
        out[b] = s.mean() / sd * math.sqrt(TRADING_DAYS) if sd > 0 else 0.0
    return {
        "sharpe_ci_lo": float(np.quantile(out, 0.025)),
        "sharpe_ci_hi": float(np.quantile(out, 0.975)),
        "p_sharpe_le_0": float((out <= 0).mean()),
    }


def cluster_bootstrap_mean(values: pd.Series, clusters: pd.Series, n_boot: int = 5000, seed: int = 11) -> dict:
    """CI for a mean of event-level outcomes, resampling whole clusters (e.g. event dates or CEOs)."""
    df = pd.DataFrame({"v": values.values, "c": clusters.values}).dropna()
    if df.empty:
        return {"mean": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"), "p_two_sided": float("nan")}
    groups = [g["v"].values for _, g in df.groupby("c")]
    rng = np.random.default_rng(seed)
    k = len(groups)
    sums = np.array([g.sum() for g in groups])
    cnts = np.array([len(g) for g in groups])
    boots = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(k, size=k)
        boots[b] = sums[pick].sum() / cnts[pick].sum()
    m = float(df["v"].mean())
    centered = boots - boots.mean()
    p = float((np.abs(centered) >= abs(m)).mean())
    return {"mean": m, "ci_lo": float(np.quantile(boots, 0.025)), "ci_hi": float(np.quantile(boots, 0.975)),
            "p_two_sided": p, "n": int(len(df)), "n_clusters": int(k)}


# ----------------------------------------------------------------------------- PBO (CSCV)

def pbo_cscv(variant_returns: pd.DataFrame, n_splits: int = 10) -> dict:
    """Probability of Backtest Overfitting via Combinatorially Symmetric Cross-Validation.

    variant_returns: T x N matrix (rows = periods, cols = strategy variants tried).
    """
    m = variant_returns.dropna(how="all").fillna(0.0).values
    t, n = m.shape
    if n < 2 or t < n_splits * 5:
        return {"pbo": float("nan"), "n_combinations": 0}
    s = n_splits - (n_splits % 2)
    blocks = np.array_split(np.arange(t), s)
    logits = []
    for is_blocks in itertools.combinations(range(s), s // 2):
        is_idx = np.concatenate([blocks[i] for i in is_blocks])
        oos_idx = np.concatenate([blocks[i] for i in range(s) if i not in is_blocks])

        def _sr(idx):
            x = m[idx]
            sd = x.std(axis=0, ddof=1)
            sd[sd == 0] = np.nan
            return x.mean(axis=0) / sd

        sr_is, sr_oos = _sr(is_idx), _sr(oos_idx)
        if np.all(np.isnan(sr_is)):
            continue
        best = int(np.nanargmax(sr_is))
        rank = sps.rankdata(np.nan_to_num(sr_oos, nan=-np.inf))[best] / (n + 1.0)
        logits.append(math.log(rank / (1.0 - rank)))
    logits = np.array(logits)
    return {"pbo": float((logits <= 0).mean()) if len(logits) else float("nan"),
            "n_combinations": int(len(logits)), "median_logit": float(np.median(logits)) if len(logits) else float("nan")}


# ----------------------------------------------------------------------------- factor regression

def factor_regression(r: pd.Series, factors: pd.DataFrame, hac_lags: int = 5) -> dict:
    """OLS of strategy returns on daily factors with Newey-West standard errors.

    `factors` columns are in decimal daily returns (Ken French data divided by 100), including RF.
    The strategy is already self-financing (hedged long/short), so we regress raw returns.
    """
    import statsmodels.api as sm

    cols = [c for c in ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"] if c in factors.columns]
    df = pd.concat([pd.Series(r, name="y"), factors[cols]], axis=1, join="inner").dropna()
    if len(df) < 60:
        return {"n": int(len(df))}
    x = sm.add_constant(df[cols])
    res = sm.OLS(df["y"], x).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    out = {
        "n": int(len(df)),
        "alpha_daily": float(res.params["const"]),
        "alpha_annual": float(res.params["const"] * TRADING_DAYS),
        "alpha_t": float(res.tvalues["const"]),
        "r2": float(res.rsquared),
    }
    for c in cols:
        out[f"beta_{c}"] = float(res.params[c])
        out[f"t_{c}"] = float(res.tvalues[c])
    return out
