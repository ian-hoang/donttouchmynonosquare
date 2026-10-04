"""
Copy this file to strategies/<your_idea>.py (the file name becomes the strategy name) and fill it in.
Before your first backtest, copy hypotheses/TEMPLATE.md to hypotheses/<your_idea>.md and commit it.

What the harness enforces for you:
- weights() is the target decided at the END of each row. The engine holds it over the NEXT row,
  so you can't trade on the bar you observe.
- run.py only passes in-sample data. The out-of-sample period stays locked until run_all.py --final.
- run_all.py re-runs weights() on truncated data. If earlier rows change, you're peeking at the future.

Databento notes:
- Check the price before pulling anything big: gd.price(dataset, symbols, schema, start, end, stype_in)
- ohlcv-1d bars are UTC days. Fine for futures as long as you're consistent; for stocks/ETFs the
  "close" would be an after-hours print. Pull ohlcv-1m and use gd.session_daily() for the 4 PM close.
- Futures: continuous symbols (ES.c.0) plus the next rank (ES.c.1) so roll_safe_returns() can bridge rolls.
- Equity/ETF bars are NOT adjusted for splits or dividends. Handle that, and say how in the note.
"""
import numpy as np
import pandas as pd

from gqh import data as gd
from gqh import risk
from strategies.base import BaseStrategy

ES_MULTIPLIER = 50  # $ per index point (CME contract spec)


class MyIdea(BaseStrategy):
    defaults = {"lookback": 20, "vol_target": 0.10}
    # ES: 0.25 tick, $50 multiplier, ~$2.50/contract fees at ~6,500 -> about 0.5 bp per side.
    # Rounded up to 1 bp for safety; run_all.py also reports costs x2.
    cost_bps = 1.0

    def load(self):
        return gd.databento(dataset="GLBX.MDP3", symbols=["ES.c.0", "ES.c.1"], schema="ohlcv-1d",
                            start="2012-01-01", end="2026-10-01", stype_in="continuous")

    def asset_returns(self, bars) -> pd.DataFrame:
        return gd.roll_safe_returns(bars)[["ES.c.0"]]

    def weights(self, bars, lookback, vol_target) -> pd.DataFrame:
        r = self.asset_returns(bars)
        trailing = np.log1p(r).rolling(lookback).sum()  # only uses rows up to t
        w = np.sign(trailing)
        if vol_target:
            w = risk.vol_target(w, r, target=vol_target)
        return risk.cap_gross(w, max_gross=2.0)

    def dollar_volume(self, bars) -> pd.DataFrame:
        return (gd.panel(bars, "volume") * gd.panel(bars, "close") * ES_MULTIPLIER)[["ES.c.0"]]


STRATEGY = MyIdea
