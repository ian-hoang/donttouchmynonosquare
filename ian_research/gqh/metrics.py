"""Performance metrics the track asks for, plus uncertainty, exposure and the Deflated Sharpe Ratio.

Intraday results are compounded to daily returns (New York dates) before any statistic is computed,
so Sharpe and friends are always comparable daily-data numbers.
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

EULER_GAMMA = 0.5772156649
SUSPICIOUS_SHARPE = 3.0


def infer_periods_per_year(index: pd.DatetimeIndex) -> float:
    years = (index[-1] - index[0]).days / 365.25
    return (len(index) - 1) / years if years > 0 else float("nan")


def is_intraday(index: pd.DatetimeIndex) -> bool:
    return len(index) > 2 and pd.Series(index).diff().median() < pd.Timedelta(hours=20)


def to_daily(net: pd.Series, turnover: pd.Series, tz: str = "America/New_York"):
    local = net.index.tz_convert(tz) if net.index.tz is not None else net.index
    day = pd.DatetimeIndex(local.date)
    daily_net = (1 + net).groupby(day).prod() - 1
    daily_turnover = turnover.groupby(day).sum()
    return daily_net, daily_turnover


def daily_frame(df: pd.DataFrame, how: str = "compound", tz: str = "America/New_York") -> pd.DataFrame:
    """Per-asset intraday table -> daily ("compound" for returns, "sum" for volumes). Daily input passes through."""
    if not is_intraday(df.index):
        return df
    local = df.index.tz_convert(tz) if df.index.tz is not None else df.index
    groups = df.groupby(pd.DatetimeIndex(local.date))
    return groups.sum() if how == "sum" else (1 + df.fillna(0.0)).groupby(pd.DatetimeIndex(local.date)).prod() - 1


def daily(net: pd.Series, turnover: pd.Series, periods_per_year: float):
    """(net, turnover, periods_per_year), compounded to daily if the input is intraday."""
    if is_intraday(net.index):
        n, t = to_daily(net, turnover)
        return n, t, 252.0
    return net, turnover, periods_per_year


def summarize(net: pd.Series, turnover: pd.Series, periods_per_year: float) -> dict:
    """Annualized return, volatility, Sharpe (95% CI), drawdown, turnover, worst day/month, skew."""
    net, turnover, ppy = daily(net, turnover, periods_per_year)
    r = net.dropna()
    n = len(r)
    sd = r.std(ddof=1)
    sr_pp = r.mean() / sd if sd > 0 else float("nan")
    # Lo (2002) iid standard error of the Sharpe ratio
    se_pp = math.sqrt((1 + 0.5 * sr_pp ** 2) / n) if n > 1 else float("nan")
    equity = (1 + r).cumprod()
    peak = np.maximum.accumulate(np.r_[1.0, equity.to_numpy()])[1:]
    times = pd.Series(r.index, index=r.index)
    last_peak = times.where(equity.to_numpy() >= peak).ffill().fillna(r.index[0])
    monthly = (1 + r).resample("ME").prod() - 1
    return {
        "ann_return": equity.iloc[-1] ** (ppy / n) - 1,
        "ann_vol": sd * math.sqrt(ppy),
        "sharpe": sr_pp * math.sqrt(ppy),
        "sharpe_lo": (sr_pp - 1.96 * se_pp) * math.sqrt(ppy),
        "sharpe_hi": (sr_pp + 1.96 * se_pp) * math.sqrt(ppy),
        "max_drawdown": (equity.to_numpy() / peak - 1).min(),
        "max_dd_days": int((times - last_peak).dt.days.max()),
        "turnover": turnover.loc[r.index].mean() * ppy,
        "worst_day": r.min(),
        "worst_month": monthly.min(),
        "skew": r.skew(),
        "n_obs": n,
        "sharpe_pp": sr_pp,
    }


def exposure(positions: pd.DataFrame) -> dict:
    """How much risk the book actually carried: leverage, net direction, biggest single position."""
    gross = positions.abs().sum(axis=1)
    return {
        "avg_gross": gross.mean(),
        "max_gross": gross.max(),
        "avg_net": positions.sum(axis=1).mean(),
        "max_position": positions.abs().max().max(),
        "time_in_market": (gross > 0).mean(),
    }


def warnings(m: dict) -> list[str]:
    out = []
    if abs(m["sharpe"]) > SUSPICIOUS_SHARPE:
        out.append(f"Sharpe {m['sharpe']:.2f} is above {SUSPICIOUS_SHARPE:g}. On daily data that usually means a bug "
                   "(lookahead, missing costs, bad data). Check before celebrating.")
    if m["n_obs"] < 250:
        out.append(f"Only {m['n_obs']} daily observations: the Sharpe confidence interval is wide.")
    return out


def table(rows: dict[str, dict]) -> pd.DataFrame:
    """Format {column label: summarize(...)} as a readable string table."""
    pct = "{:.1%}".format
    fmt = {
        "ann_return": pct,
        "ann_vol": pct,
        "sharpe": "{:.2f}".format,
        "sharpe_95ci": None,
        "max_drawdown": pct,
        "max_dd_days": "{:,} days".format,
        "turnover": "{:.1f}x/yr".format,
        "worst_day": pct,
        "worst_month": pct,
        "skew": "{:.2f}".format,
        "n_obs": "{:,}".format,
    }
    out = {}
    for label, m in rows.items():
        col = {}
        for key, f in fmt.items():
            if key == "sharpe_95ci":
                col[key] = f"[{m['sharpe_lo']:.2f}, {m['sharpe_hi']:.2f}]"
            else:
                col[key] = f(m[key])
        out[label] = col
    return pd.DataFrame(out)


def expected_max_sharpe(n_trials: int, var_sharpe: float) -> float:
    """Sharpe the luckiest of `n_trials` zero-edge strategies should show by chance (Bailey & Lopez de Prado)."""
    if n_trials <= 1:
        return 0.0
    z = NormalDist().inv_cdf
    return math.sqrt(var_sharpe) * ((1 - EULER_GAMMA) * z(1 - 1 / n_trials)
                                    + EULER_GAMMA * z(1 - 1 / (n_trials * math.e)))


def deflated_sharpe(net: pd.Series, n_trials: int, var_sharpe_pp: float | None = None) -> dict:
    """Probability the true Sharpe beats what luck alone predicts after `n_trials` tries.

    Works in per-period (daily) Sharpe units. `var_sharpe_pp` is the variance of per-period Sharpe across
    all the variants you tried; without it, the null sampling variance 1/n is used.
    """
    if is_intraday(net.index):
        net, _ = to_daily(net, net * 0)
    r = net.dropna()
    n = len(r)
    sr = r.mean() / r.std(ddof=1)
    var = var_sharpe_pp if var_sharpe_pp and var_sharpe_pp > 0 else 1 / n
    sr0 = expected_max_sharpe(n_trials, var)
    kurt = r.kurt() + 3  # pandas gives excess kurtosis
    denom = math.sqrt(max(1 - r.skew() * sr + (kurt - 1) / 4 * sr ** 2, 1e-12))
    return {"dsr": NormalDist().cdf((sr - sr0) * math.sqrt(n - 1) / denom),
            "sr0_pp": sr0, "sr_pp": sr, "n_trials": n_trials}
