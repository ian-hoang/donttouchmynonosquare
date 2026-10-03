"""Descriptive evidence for fixed intraday experiments, without parameter search.

``pnl`` is cumulative net dollar P&L from a run that starts flat at zero P&L.
UTC calendar days are the resampling units. For regular US daytime windows this
matches the intended session; overnight strategies need an exchange-session
label instead and must not interpret this helper's dates as trading sessions.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _curve(curve: pd.DataFrame) -> pd.Series:
    if not isinstance(curve.index, pd.DatetimeIndex) or str(curve.index.tz) != "UTC":
        raise ValueError("curve must have a UTC DatetimeIndex")
    if not curve.index.is_unique or not curve.index.is_monotonic_increasing:
        raise ValueError("curve timestamps must be increasing and unique")
    missing = {"equity", "pnl", "position", "valid"} - set(curve)
    if missing:
        raise ValueError(f"Missing curve columns: {sorted(missing)}")
    if not np.isfinite(curve[["equity", "pnl", "position"]].to_numpy(dtype=float)).all():
        raise ValueError("curve equity, cumulative pnl and position must be finite")
    if curve["valid"].isna().any() or not curve["valid"].isin([True, False]).all():
        raise ValueError("curve valid must be boolean without missing values")
    if curve.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    capital = curve["equity"].to_numpy(dtype=float) - curve["pnl"].to_numpy(dtype=float)
    if not np.allclose(capital, capital[0], rtol=1e-10, atol=1e-7):
        raise ValueError("equity minus cumulative pnl must be constant initial capital")
    final = curve["pnl"].groupby(curve.index.normalize()).last().astype(float)
    # Zero, not the first observed P&L, is the pre-run initial P&L. This keeps
    # entry fees or losses already present in the first row of the first day.
    return final.diff().fillna(final.iloc[0])


def _fills(fills: pd.DataFrame, curve: pd.DataFrame, days: pd.DatetimeIndex):
    costs = pd.Series(0.0, index=days)
    summary = {"count": 0, "contracts_traded": 0.0, "fees": 0.0,
               "extra_costs": 0.0, "reasons": {}}
    if fills.empty:
        return summary, costs
    required = {"time", "quantity", "fee", "extra_cost"}
    if not required.issubset(fills):
        raise ValueError(f"Missing fill columns: {sorted(required - set(fills))}")
    if curve.empty:
        raise ValueError("Nonempty fills cannot accompany an empty curve")
    numeric = fills[["quantity", "fee", "extra_cost"]].to_numpy(dtype=float)
    if not np.isfinite(numeric).all() or np.any(numeric[:, 0] == 0):
        raise ValueError("Fill quantity/costs must be finite and quantity nonzero")
    timestamps = pd.DatetimeIndex(pd.to_datetime(fills["time"], utc=True))
    if timestamps.isna().any() or not timestamps.isin(curve.index).all():
        raise ValueError("Each fill must map to an observed curve timestamp")
    explicit = pd.Series(numeric[:, 1] + numeric[:, 2], index=timestamps)
    costs = explicit.groupby(timestamps.normalize()).sum().reindex(days, fill_value=0.0)
    reasons = fills["reason"].fillna("unspecified").astype(str).value_counts() if "reason" in fills else {}
    summary = {
        "count": int(len(fills)),
        "contracts_traded": float(np.abs(numeric[:, 0]).sum()),
        "fees": float(numeric[:, 1].sum()),
        "extra_costs": float(numeric[:, 2].sum()),
        "reasons": {str(k): int(v) for k, v in dict(reasons).items()},
    }
    return summary, costs


def _episodes(curve: pd.DataFrame) -> dict:
    """Flat-to-flat episodes preserve total costs without guessing a multiplier.

    A reversal that never displays a flat position remains in the same episode.
    These therefore are explicitly not individual directional trade statistics.
    """
    closed, entry_pnl, previous_pnl = [], None, 0.0
    reversals, previous_position = 0, 0.0
    for pnl, position in curve[["pnl", "position"]].itertuples(index=False, name=None):
        if previous_position * position < 0:
            reversals += 1
        if position != 0 and entry_pnl is None:
            entry_pnl = previous_pnl
        elif position == 0 and entry_pnl is not None:
            closed.append(float(pnl - entry_pnl))
            entry_pnl = None
        previous_pnl, previous_position = float(pnl), float(position)
    return {
        "definition": "Flat-to-flat position episodes; direct reversals remain in the same episode.",
        "closed_count": len(closed),
        "winning_count": sum(x > 0 for x in closed),
        "losing_count": sum(x < 0 for x in closed),
        "flat_count": sum(x == 0 for x in closed),
        "hit_ratio": float(np.mean(np.asarray(closed) > 0)) if closed else None,
        "mean_net_pnl": float(np.mean(closed)) if closed else None,
        "median_net_pnl": float(np.median(closed)) if closed else None,
        "closed_net_pnl": float(sum(closed)),
        "open_episode": entry_pnl is not None,
        "direct_reversals": reversals,
        "uncertainty": "Episode outcomes are dependent; uncertainty is assessed using whole UTC-day blocks.",
    }


def _bootstrap(matrix, *, seed, repetitions, block_length):
    """Circular moving blocks of complete days; paired columns share draws."""
    n, columns = matrix.shape
    rng = np.random.default_rng(seed)
    means = np.empty((repetitions, columns), dtype=float)
    blocks = math.ceil(n / block_length)
    # Bound temporary memory even when histories or repetition counts grow.
    for start in range(0, repetitions, 256):
        count = min(256, repetitions - start)
        starts = rng.integers(0, n, size=(count, blocks))
        indices = (starts[..., None] + np.arange(block_length)) % n
        indices = indices.reshape(count, -1)[:, :n]
        means[start:start + count] = matrix[indices].mean(axis=1)
    return means


def _stats(values, draws, confidence):
    values = np.asarray(values, dtype=float)
    n = len(values)
    interval = None
    if draws is not None:
        tails = (1 - confidence) / 2
        low, high = np.quantile(draws, [tails, 1 - tails])
        interval = {"lower": float(low), "upper": float(high), "confidence": confidence}
    return {
        "total_pnl": float(values.sum()),
        "mean_daily_pnl": float(values.mean()) if n else None,
        "median_daily_pnl": float(np.median(values)) if n else None,
        "positive_day_fraction": float(np.mean(values > 0)) if n else None,
        "mean_daily_pnl_interval": interval,
    }


def evidence(curve: pd.DataFrame, fills: pd.DataFrame,
             baseline_curve: pd.DataFrame | None = None, *, seed: int = 1729,
             repetitions: int = 5000, block_length: int = 5,
             confidence: float = 0.95) -> dict:
    """Build a JSON-serializable, descriptive report with no tuning or downloads.

    Requires complete simulation curves starting at zero cumulative P&L; do not
    pass an arbitrary slice that retains earlier cumulative P&L. Intervals are
    withheld below 20 UTC days. The optional baseline must cover exactly the
    same timestamps, so paired daily differences cannot compare unequal runs.
    """
    for name, value in (("repetitions", repetitions), ("block_length", block_length)):
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if repetitions < 100:
        raise ValueError("Use at least 100 bootstrap repetitions")
    if not np.isfinite(confidence) or not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    daily = _curve(curve)
    n = len(daily)
    fill_summary, costs = _fills(fills, curve, daily.index)
    # This is an accounting addback for the actual fills. It still includes
    # crossing the spread and does not rerun cost-dependent stops or entries.
    before_explicit_costs = daily + costs
    vectors = [daily.to_numpy(), before_explicit_costs.to_numpy()]
    baseline_daily = None
    if baseline_curve is not None:
        baseline_daily = _curve(baseline_curve)
        if not baseline_curve.index.equals(curve.index):
            raise ValueError("Baseline must have the same timestamps as the strategy")
        vectors.extend([baseline_daily.to_numpy(), (daily - baseline_daily).to_numpy()])
    effective_block = min(block_length, n) if n else 0
    enough = n >= 20 and n >= 2 * block_length
    samples = _bootstrap(np.column_stack(vectors), seed=seed, repetitions=repetitions,
                         block_length=effective_block) if enough else None

    def stats(column):
        return _stats(vectors[column], None if samples is None else samples[:, column], float(confidence))

    rows = []
    for i, date in enumerate(daily.index):
        row = {"session": date.date().isoformat(), "net_pnl": float(daily.iloc[i]),
               "pnl_before_explicit_costs": float(before_explicit_costs.iloc[i])}
        if baseline_daily is not None:
            row.update(baseline_net_pnl=float(baseline_daily.iloc[i]),
                       difference_vs_baseline=float(daily.iloc[i] - baseline_daily.iloc[i]))
        rows.append(row)
    warnings = [
        "These are descriptive sample estimates, not proof of alpha or future profitability.",
        "Intervals do not adjust for testing three strategies, parameter variants, or reusing the sample.",
        "Block resampling assumes the observed days are representative; it cannot repair regime shifts or execution bias.",
        "UTC dates are calendar boundaries, not exchange trading-session definitions.",
    ]
    if not enough:
        warnings.append("Confidence intervals withheld: need at least 20 days and two full session blocks.")
    elif n < 100:
        warnings.append("Short history: intervals are exploratory and tail/regime coverage is limited.")
    if n and daily.nunique() < 2:
        warnings.append("Observed daily P&L has no variation; a degenerate interval does not establish certainty.")
    report = {
        "session_unit": "UTC calendar date", "sessions": n,
        "interval_status": "exploratory" if enough else "insufficient_sessions",
        "bootstrap": {"method": "circular moving blocks of complete UTC days",
                      "block_length": int(effective_block), "requested_block_length": int(block_length),
                      "repetitions": int(repetitions) if enough else 0, "seed": int(seed),
                      "minimum_sessions": 20, "paired_baseline": baseline_daily is not None},
        "strategy": stats(0),
        "execution_pnl_before_explicit_costs": {
            **stats(1),
            "definition": "Actual-fill net P&L plus fees and extra costs; spread remains embedded. Accounting addback, not a zero-cost rerun.",
        },
        "baseline": stats(2) if baseline_daily is not None else None,
        "difference_vs_baseline": stats(3) if baseline_daily is not None else None,
        "daily": rows, "fills": fill_summary, "episodes": _episodes(curve),
        "valid_bar_fraction": float(curve["valid"].mean()) if len(curve) else None,
        "exposure_bar_fraction": float(curve["position"].ne(0).mean()) if len(curve) else None,
        "raw_mid_markout": {"available": False,
                            "reason": "Requires decision timestamps and later midquotes; cannot be inferred from equity and fills alone. Gross markouts would measure prediction, not executable profit."},
        "warnings": warnings,
    }
    return report
