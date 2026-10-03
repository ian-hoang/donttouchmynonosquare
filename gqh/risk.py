"""Risk overlays for the Risk Management criterion. Wrap your raw weights with these in weights().

Each one only uses information up to the current row, so it passes the lookahead check.

    w = raw_signal(...)
    w = risk.vol_target(w, returns, target=0.10)   # size to a volatility target
    w = risk.cap_weights(w, max_abs=0.25)          # per-asset limit
    w = risk.cap_gross(w, max_gross=2.0)           # leverage limit
    w = risk.drawdown_brake(w, returns, max_dd=0.15, scale=0.5)  # pre-set de-risking rule
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _strategy_returns(weights: pd.DataFrame, asset_returns: pd.DataFrame) -> pd.Series:
    """What the unadjusted strategy earned: yesterday's weights times today's returns."""
    return (weights.shift(1) * asset_returns).sum(axis=1)


def vol_target(weights, asset_returns, target: float = 0.10, window: int = 60, max_leverage: float = 3.0,
               periods_per_year: float = 252) -> pd.DataFrame:
    """Scale the whole book so its trailing realized volatility matches `target` (annualized)."""
    realized = _strategy_returns(weights, asset_returns).rolling(window).std() * np.sqrt(periods_per_year)
    scale = (target / realized).clip(upper=max_leverage)
    return weights.mul(scale, axis=0)


def inverse_vol(weights, asset_returns, window: int = 60) -> pd.DataFrame:
    """Give each asset equal risk: divide its weight by its own trailing volatility (then renormalize)."""
    vol = asset_returns.rolling(window).std()
    raw = weights / vol
    gross_before = weights.abs().sum(axis=1)
    gross_after = raw.abs().sum(axis=1)
    return raw.mul(gross_before / gross_after, axis=0)


def cap_weights(weights, max_abs: float = 0.25) -> pd.DataFrame:
    """No single position larger than `max_abs` of capital."""
    return weights.clip(lower=-max_abs, upper=max_abs)


def cap_gross(weights, max_gross: float = 2.0) -> pd.DataFrame:
    """Total gross exposure (sum of |weights|) never above `max_gross`."""
    gross = weights.abs().sum(axis=1)
    return weights.mul((max_gross / gross).clip(upper=1.0).fillna(1.0), axis=0)


def drawdown_brake(weights, asset_returns, max_dd: float = 0.15, scale: float = 0.5) -> pd.DataFrame:
    """Cut size to `scale` while the strategy is more than `max_dd` below its high-water mark."""
    equity = (1 + _strategy_returns(weights, asset_returns).fillna(0.0)).cumprod()
    drawdown = equity / equity.cummax() - 1
    factor = pd.Series(np.where(drawdown < -max_dd, scale, 1.0), index=weights.index)
    return weights.mul(factor, axis=0)
