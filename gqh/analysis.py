"""Robustness evidence for the note: returns by year, factor exposure, and a capacity estimate."""
from __future__ import annotations

import io
import math
import urllib.request
import zipfile

import numpy as np
import pandas as pd

from gqh import CACHE

FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FRENCH_FILES = {"ff3": "F-F_Research_Data_Factors_daily_CSV.zip", "mom": "F-F_Momentum_Factor_daily_CSV.zip"}


def by_year(net: pd.Series) -> pd.Series:
    """Compounded return per calendar year. Shows whether the profit came from one lucky period."""
    return (1 + net).groupby(net.index.year).prod() - 1


def _french_csv(name: str) -> pd.DataFrame:
    path = CACHE / FRENCH_FILES[name]
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(FRENCH + FRENCH_FILES[name], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            path.write_bytes(resp.read())
    with zipfile.ZipFile(path) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    first = next(i for i, l in enumerate(lines) if l.split(",")[0].strip().isdigit() and len(l.split(",")[0].strip()) == 8)
    header = ["date"] + [c.strip() for c in lines[first - 1].split(",")[1:]]
    rows = []
    for line in lines[first:]:
        cells = [c.strip() for c in line.split(",")]
        if not (cells[0].isdigit() and len(cells[0]) == 8):
            break
        rows.append(cells)
    df = pd.DataFrame(rows, columns=header)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    df = df.set_index("date").astype(float).replace(-99.99, np.nan)
    return df / 100  # files are in percent


def french_factors() -> pd.DataFrame:
    """Daily Mkt-RF, SMB, HML, Mom and RF from the Ken French Data Library (cached in data/cache/)."""
    return _french_csv("ff3").join(_french_csv("mom"), how="inner")


def factor_regression(net: pd.Series, factors: pd.DataFrame | None = None, hac_lags: int = 5) -> pd.DataFrame:
    """Regress daily strategy returns on market, size, value and momentum (Newey-West t-stats).

    A significant alpha with small betas means the edge isn't just a known factor in disguise.
    """
    import statsmodels.api as sm

    factors = french_factors() if factors is None else factors
    daily = (1 + net).groupby(pd.DatetimeIndex(net.index).tz_localize(None).normalize()).prod() - 1
    cols = [c for c in ["Mkt-RF", "SMB", "HML", "Mom"] if c in factors]
    df = pd.concat([daily.rename("strategy"), factors[cols]], axis=1, join="inner").dropna()
    if len(df) < 60:
        raise ValueError(f"Only {len(df)} days overlap with the factor data")
    fit = sm.OLS(df["strategy"], sm.add_constant(df[cols])).fit(cov_type="HAC", cov_kwds={"maxlags": hac_lags})
    out = pd.DataFrame({"coef": fit.params, "t_stat": fit.tvalues})
    out.loc["const", "coef"] *= 252  # annualized alpha
    out = out.rename(index={"const": "alpha (ann.)"})
    out.attrs["r2"], out.attrs["n_days"] = fit.rsquared, len(df)
    return out


def capacity(aum: float, names: int, adv_per_name: float, turnover: float, gross_sharpe: float,
             strategy_vol: float, fixed_bps: float, daily_vol: float, impact_coef: float = 1.0) -> dict:
    """Square-root impact model, the same one as the track brief's capacity dial.

    cost per trade = fixed + impact_coef * daily_vol * sqrt(trade / ADV); yearly drag = turnover * cost;
    net Sharpe = gross Sharpe - drag / strategy vol. Capacity is the AUM where net Sharpe hits zero.
    """
    def net_at(a):
        trade = a * turnover / 252 / names
        impact = impact_coef * daily_vol * math.sqrt(trade / adv_per_name) * 1e4
        cost = fixed_bps + impact
        drag = turnover * cost / 1e4
        return {"trade_per_name": trade, "participation": trade / adv_per_name, "impact_bps": impact,
                "cost_bps": cost, "yearly_drag": drag, "net_sharpe": gross_sharpe - drag / strategy_vol}

    def aum_at(target_sharpe):
        impact = (gross_sharpe - target_sharpe) * strategy_vol / turnover * 1e4 - fixed_bps
        if impact <= 0:
            return 0.0
        participation = (impact / 1e4 / (impact_coef * daily_vol)) ** 2
        return participation * adv_per_name * names * 252 / turnover

    return {**net_at(aum), "aum": aum, "capacity": aum_at(0.0), "half_edge_aum": aum_at(gross_sharpe / 2)}
