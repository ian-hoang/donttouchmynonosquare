"""Event-driven, market-hedged backtest.

Each event (one curated CEO video) opens a stock position at the entry session's open, sized by signal
strength and the stock's ex-ante idiosyncratic volatility, hedged with the market ETF at the ex-ante beta,
and closes at the open H sessions later. Overlapping events in the same name add up, subject to caps.

P&L convention: a weight held at session d earns the open(d) -> open(d+1) return. Costs are charged on
every weight change (entry and exit, stock and hedge legs). Borrow is charged daily on short legs.
Every estimate used for sizing (beta, idio vol) uses data strictly before the entry session.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class BTParams:
    horizon: int = 5                       # holding period in sessions (pre-registered primary: 5)
    hedge: str = "SPY"                     # hedge instrument column in the price panel ("" = unhedged)
    signal_cap: float = 2.0                # |signal| clipped here; full size at |signal| = cap
    target_vol_per_event: float = 0.10     # annualized idio-vol budget of a full-size event position
    max_weight_per_event: float = 0.35     # notional cap per event
    max_weight_per_name: float = 0.50      # notional cap per ticker after overlaps
    max_gross: float = 2.0                 # cap on sum |weights| incl. hedge
    beta_lookback: int = 252
    vol_lookback: int = 63
    min_history: int = 120                 # sessions of price history needed to size an event
    cost_bps_stock: float = 5.0            # one-way: half-spread + slippage + fees (justified in note)
    cost_bps_hedge: float = 1.0            # one-way for SPY
    borrow_bps_annual_stock: float = 30.0  # general-collateral borrow for mega-caps
    borrow_bps_annual_hedge: float = 25.0
    cost_multiplier: float = 1.0           # 2.0 for the "costs doubled" robustness row
    dd_brake: float = 0.0                  # >0: halve exposure while running drawdown exceeds this
    overlap: str = "replace"               # "replace": a new event closes the name's open position; "stack": add up
    beta_clip: tuple = (0.3, 2.5)

    def to_dict(self) -> dict:
        return asdict(self)

    def with_(self, **kw) -> "BTParams":
        return replace(self, **kw)


@dataclass
class BTResult:
    daily: pd.Series                       # strategy return per session (net)
    gross_daily: pd.Series                 # before costs and borrow
    weights: pd.DataFrame                  # session x instrument weights (after caps)
    events: pd.DataFrame                   # per-event sizing + abnormal returns
    turnover_per_year: float
    params: BTParams
    extras: dict = field(default_factory=dict)


def _beta(y: np.ndarray, x: np.ndarray) -> float:
    m = np.isfinite(y) & np.isfinite(x)
    y, x = y[m], x[m]
    if len(y) < 30 or np.var(x) == 0:
        return np.nan
    return float(np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1))


def run_backtest(open_px: pd.DataFrame, close_px: pd.DataFrame, events: pd.DataFrame,
                 params: BTParams = BTParams()) -> BTResult:
    """events: columns [event_id, ticker, entry, signal]; `entry` is a session date in open_px.index."""
    p = params
    sessions = open_px.index
    n_days = len(sessions)
    pos = {d: i for i, d in enumerate(sessions)}
    r_oo = (open_px.shift(-1) / open_px - 1.0)                     # earned while holding at session d
    r_cc = close_px.pct_change()

    tickers = sorted(set(events["ticker"]) & set(open_px.columns))
    hedge = p.hedge if p.hedge and p.hedge in open_px.columns else ""
    instruments = tickers + ([hedge] if hedge and hedge not in tickers else [])
    col = {t: j for j, t in enumerate(instruments)}
    R = r_oo.reindex(columns=instruments).fillna(0.0).values

    # with overlap="replace", an event's holding window ends early at the next event in the same name
    next_entry: dict = {}
    if p.overlap == "replace":
        ev_sorted = events.dropna(subset=["entry"]).sort_values("entry")
        for tkr, g in ev_sorted.groupby("ticker"):
            idx = [pos.get(e) for e in g["entry"]]
            for k, eid in enumerate(g["event_id"]):
                later = [j for j in idx[k + 1:] if j is not None and idx[k] is not None and j > idx[k]]
                next_entry[eid] = later[0] if later else None

    rows = []
    stock_legs = np.zeros((n_days, len(instruments)))
    hedge_by_name = np.zeros((n_days, len(instruments)))           # hedge leg attributed to each name
    for ev in events.itertuples(index=False):
        rec = {"event_id": ev.event_id, "ticker": ev.ticker, "entry": ev.entry, "signal": ev.signal,
               "sized": False, "reason": ""}
        if pd.isna(ev.entry) or ev.entry not in pos or ev.ticker not in col:
            rec["reason"] = "no_entry_or_price"
            rows.append(rec)
            continue
        i0 = pos[ev.entry]
        if not np.isfinite(ev.signal) or ev.signal == 0:
            rec["reason"] = "zero_signal"
            rows.append(rec)
            continue
        hist = r_cc[ev.ticker].values[:i0]                          # strictly before entry
        if np.isfinite(hist).sum() < p.min_history:
            rec["reason"] = "insufficient_history"
            rows.append(rec)
            continue
        y = hist[-p.beta_lookback:]
        if hedge:
            x = r_cc[hedge].values[:i0][-p.beta_lookback:]
            beta = _beta(y, x)
            beta = float(np.clip(beta, *p.beta_clip)) if np.isfinite(beta) else 1.0
            yv, xv = hist[-p.vol_lookback:], r_cc[hedge].values[:i0][-p.vol_lookback:]
            mm = np.isfinite(yv) & np.isfinite(xv)
            idio = float(np.std(yv[mm] - beta * xv[mm], ddof=1)) if mm.sum() > 20 else np.nan
        else:
            beta = 0.0
            idio = float(np.nanstd(hist[-p.vol_lookback:], ddof=1))
        if not np.isfinite(idio) or idio <= 0:
            rec["reason"] = "no_vol"
            rows.append(rec)
            continue
        idio_ann = idio * np.sqrt(TRADING_DAYS)
        s = float(np.clip(ev.signal, -p.signal_cap, p.signal_cap)) / p.signal_cap
        w = float(np.clip(s * p.target_vol_per_event / idio_ann, -p.max_weight_per_event, p.max_weight_per_event))
        i1 = min(i0 + p.horizon, n_days)                            # exclusive
        if next_entry.get(ev.event_id) is not None:
            i1 = min(i1, next_entry[ev.event_id])
        stock_legs[i0:i1, col[ev.ticker]] += w
        if hedge:
            hedge_by_name[i0:i1, col[ev.ticker]] += -beta * w
        # sizing-free abnormal return over the holding window (event study input)
        ar = R[i0:i1, col[ev.ticker]] - (beta * R[i0:i1, col[hedge]] if hedge else 0.0)
        rec.update(sized=True, beta=beta, idio_vol_ann=idio_ann, weight=w, n_held=i1 - i0,
                   car=float(np.sum(ar)), signed_car=float(np.sign(w) * np.sum(ar)),
                   pnl_contrib=float(w * np.sum(ar)))
        rows.append(rec)

    # name caps: scale a name's stock leg and its hedge together
    gross_name = np.abs(stock_legs)
    f_name = np.where(gross_name > p.max_weight_per_name,
                      p.max_weight_per_name / np.maximum(gross_name, 1e-12), 1.0)
    stock_legs *= f_name
    hedge_by_name *= f_name
    W = stock_legs.copy()
    if hedge:
        W[:, col[hedge]] += hedge_by_name.sum(axis=1)

    gross = np.abs(W).sum(axis=1)
    W *= np.where(gross > p.max_gross, p.max_gross / np.maximum(gross, 1e-12), 1.0)[:, None]

    # drawdown brake: path-dependent, decided from P&L realized before each session
    if p.dd_brake > 0:
        eq, peak, scale = 1.0, 1.0, np.ones(n_days)
        for d in range(n_days):
            scale[d] = 0.5 if eq / peak - 1.0 < -p.dd_brake else 1.0
            eq *= 1.0 + scale[d] * float(W[d] @ R[d])
            peak = max(peak, eq)
        W *= scale[:, None]

    cost_bps = np.array([p.cost_bps_hedge if t == hedge else p.cost_bps_stock for t in instruments]) * p.cost_multiplier
    borrow = np.array([p.borrow_bps_annual_hedge if t == hedge else p.borrow_bps_annual_stock for t in instruments])
    dW = np.abs(np.diff(np.vstack([np.zeros((1, W.shape[1])), W]), axis=0))
    costs = (dW * cost_bps / 1e4).sum(axis=1)
    borrow_cost = (np.clip(-W, 0, None) * borrow / 1e4 / TRADING_DAYS).sum(axis=1)
    gross_ret = (W * R).sum(axis=1)
    net = gross_ret - costs - borrow_cost

    years = n_days / TRADING_DAYS
    return BTResult(
        daily=pd.Series(net, index=sessions, name="strategy"),
        gross_daily=pd.Series(gross_ret, index=sessions, name="gross"),
        weights=pd.DataFrame(W, index=sessions, columns=instruments),
        events=pd.DataFrame(rows),
        turnover_per_year=float(dW.sum() / years) if years > 0 else float("nan"),
        params=p,
        extras={"total_costs": float(costs.sum()), "total_borrow": float(borrow_cost.sum())},
    )


def window(s: pd.Series, start, end) -> pd.Series:
    """Restrict a daily series to [start, end]; sessions with no position count as zero return."""
    return s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
