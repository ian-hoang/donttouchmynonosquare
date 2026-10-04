"""Vectorized backtest.

Weights decided at row t are held over row t+1. The engine applies that lag itself, so a strategy
can never trade on the same bar it observes.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from gqh.metrics import infer_periods_per_year


@dataclass
class Result:
    net: pd.Series          # per-period return after costs
    gross: pd.Series        # per-period return before costs
    turnover: pd.Series     # sum of |change in weight| per period
    positions: pd.DataFrame  # weight held during each period
    cost_bps: float
    periods_per_year: float

    def _mask(self, keep) -> "Result":
        return Result(self.net[keep], self.gross[keep], self.turnover[keep], self.positions[keep],
                      self.cost_bps, self.periods_per_year)

    def in_sample(self, oos_start) -> "Result":
        return self._mask(self.net.index < oos_start)

    def out_of_sample(self, oos_start) -> "Result":
        return self._mask(self.net.index >= oos_start)


def backtest(weights: pd.DataFrame, asset_returns: pd.DataFrame, cost_bps,
             periods_per_year: float | None = None) -> Result:
    """Run target `weights` against `asset_returns`, charging `cost_bps` per unit of weight traded.

    `cost_bps` is one number for every asset, or a {column: bps} mapping for per-asset costs.
    Rows of `weights` that fall between rows of `asset_returns` apply from the next returns row on;
    missing rows hold the previous target; NaN before the first target means flat.
    """
    asset_returns = asset_returns.astype(float)
    grid = asset_returns.index
    weights = (weights.astype(float)
               .reindex(grid.union(weights.index)).ffill()
               .reindex(index=grid, columns=asset_returns.columns)
               .fillna(0.0))
    positions = weights.shift(1).fillna(0.0)
    gross = (positions * asset_returns.fillna(0.0)).sum(axis=1)
    trades = positions.diff().abs()
    trades.iloc[0] = positions.iloc[0].abs()
    turnover = trades.sum(axis=1)
    if isinstance(cost_bps, (dict, pd.Series)):
        per_asset = pd.Series(cost_bps, dtype=float).reindex(asset_returns.columns)
        if per_asset.isna().any():
            raise ValueError(f"No cost given for {list(per_asset[per_asset.isna()].index)}")
        costs = (trades * per_asset).sum(axis=1) / 1e4
        cost_bps = float(per_asset.mean())
    else:
        costs = turnover * cost_bps / 1e4
    net = gross - costs
    ppy = periods_per_year or infer_periods_per_year(grid)
    return Result(net, gross, turnover, positions, cost_bps, ppy)
