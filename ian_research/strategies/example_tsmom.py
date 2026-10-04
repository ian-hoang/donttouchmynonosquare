"""Worked example on SYNTHETIC prices, so the whole pipeline runs without an API key.

Time-series momentum: long assets whose trailing return is positive, short the rest, optionally scaled
to a volatility target. Replace it with a real idea; don't submit this one.
"""
import numpy as np
import pandas as pd

from gqh import data as gd
from gqh import risk
from strategies.base import BaseStrategy


class ExampleTSMom(BaseStrategy):
    defaults = {"lookback": 60, "vol_target": 0.0}
    cost_bps = 5.0

    def load(self) -> pd.DataFrame:
        return gd.synthetic_prices()

    def weights(self, prices, lookback, vol_target) -> pd.DataFrame:
        r = prices.pct_change()
        w = np.sign(np.log(prices).diff(lookback)) / prices.shape[1]
        if vol_target:
            w = risk.vol_target(w, r, target=vol_target)
        return risk.cap_weights(w, max_abs=0.5)

    def dollar_volume(self, prices) -> pd.DataFrame:
        return prices * 0 + 50e6  # synthetic: $50M traded per asset per day


STRATEGY = ExampleTSMom
