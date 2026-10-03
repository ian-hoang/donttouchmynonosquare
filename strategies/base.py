"""What every strategy file implements. See strategies/_template.py for a filled-in starting point."""
from __future__ import annotations

import pandas as pd


class BaseStrategy:
    name: str = ""                    # set from the file name by strategies.get()
    defaults: dict = {}               # every tunable parameter and its default
    cost_bps: float = 5.0             # cost per unit of weight traded, per side. Justify it in the note.
    periods_per_year: float | None = None  # inferred from the data if left as None

    def load(self):
        """Full history, out-of-sample included: a DataFrame or a dict of DataFrames indexed by time.

        The harness cuts off the out-of-sample part before your code sees it during exploration.
        """
        raise NotImplementedError

    def asset_returns(self, data) -> pd.DataFrame:
        """Return of each asset from the previous row to this row. Default: close-to-close on a price table."""
        return data.pct_change()

    def weights(self, data, **params) -> pd.DataFrame:
        """Target weight per asset, decided at the end of each row using only data up to that row.

        The engine holds it over the next row. Positive = long, negative = short, 1.0 = 100% of capital.
        Use 0 for flat; NaN means "keep the previous target".
        """
        raise NotImplementedError

    def dollar_volume(self, data) -> pd.DataFrame | None:
        """Optional: traded dollar volume per asset per row (same shape as asset_returns).

        Lets run_all.py estimate capacity automatically. For futures: volume * price * multiplier.
        """
        return None
