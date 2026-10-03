"""Automated checks: lookahead, and data problems the note has to explain."""
from __future__ import annotations

import pandas as pd

from gqh.split import truncate


def lookahead_check(strategy, data, params: dict, fractions=(0.5, 0.7, 0.9), tol=1e-8) -> dict:
    """Recompute weights on data cut at several points and compare with the full-data weights.

    Catches full-sample normalization, centered windows, backfills, and anything else that lets
    later rows leak into earlier decisions.
    """
    full = strategy.weights(data, **params).astype(float)
    worst, worst_at = 0.0, None
    for f in fractions:
        cut = full.index[int(len(full.index) * f)]
        part = strategy.weights(truncate(data, cut), **params).astype(float)
        common = part.index.intersection(full.index[full.index <= cut])
        a = full.loc[common, part.columns].fillna(0.0)
        b = part.loc[common].fillna(0.0)
        diff = float((a - b).abs().max().max()) if len(common) else 0.0
        if diff > worst:
            worst, worst_at = diff, cut
    return {"passed": worst <= tol, "max_diff": worst, "cut": worst_at}


def data_quality(asset_returns: pd.DataFrame, jump: float = 0.25, stale_run: int = 5) -> pd.DataFrame:
    """Per asset: missing data, suspicious jumps (unadjusted splits, bad ticks, roll gaps), stale prices."""
    rows = {}
    for col in asset_returns.columns:
        r = asset_returns[col]
        zero = r.eq(0)
        runs = zero.groupby((~zero).cumsum()).sum()
        rows[col] = {
            "obs": int(r.notna().sum()),
            "missing": f"{r.isna().mean():.1%}",
            f"moves_over_{jump:.0%}": int((r.abs() > jump).sum()),
            "largest_move": f"{r.abs().max():.1%}",
            "longest_flat_run": int(runs.max()) if len(runs) else 0,
        }
    df = pd.DataFrame(rows).T
    df.attrs["flags"] = [f"{c}: {int(n)} single-period moves over {jump:.0%} (unadjusted split? bad tick? roll gap?)"
                         for c, n in df[f"moves_over_{jump:.0%}"].items() if n] + \
                        [f"{c}: {int(n)} consecutive unchanged prices (stale data?)"
                         for c, n in df["longest_flat_run"].items() if n >= stale_run]
    return df
