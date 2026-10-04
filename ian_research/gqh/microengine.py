"""Small-size intraday simulation at sampled, executable bid/ask quotes.

This is a research simulator, not an exchange matching engine. Decisions at t
can execute only at a later grid timestamp >= t + latency. Crossing the spread,
per-contract fees and extra adverse ticks are charged for every side, including
reversals and scheduled liquidation. No same-bar close-to-close P&L is credited.
Stop-loss, daily-loss, and invalid-data exits latch when observed and use the
same latency rule. Maximum-holding exits are scheduled at entry; session-end
exits are scheduled at session start, so those known deadlines need no further
reaction delay. Conflicting signal changes wait while a reactive exit is pending.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Execution:
    tick_size: float = 0.25
    multiplier: float = 50.0
    fee_per_side: float = 2.5
    slippage_ticks: float = 1.0
    latency_ms: float = 100.0
    max_spread_ticks: float = 4.0
    max_hold_seconds: float = 30.0
    stop_loss_dollars: float = 100.0
    daily_loss_dollars: float = 300.0
    capital: float = 100_000.0

    def validate(self):
        for key, value in vars(self).items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{key} must be finite and nonnegative")
        for key in ("tick_size", "multiplier", "max_spread_ticks", "max_hold_seconds",
                    "stop_loss_dollars", "daily_loss_dollars", "capital"):
            if getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")


@dataclass
class MicroResult:
    curve: pd.DataFrame
    fills: pd.DataFrame
    summary: dict


def validate_target(target, frame):
    if not isinstance(target, pd.Series) or not target.index.equals(frame.index):
        raise ValueError("Signal must return a Series on the EXACT input index (no dropped endpoints)")
    if target.isna().any() or not target.isin([-1, 0, 1]).all():
        raise ValueError("Signal must contain only finite -1, 0, 1 targets")


def check_causality(function, frame, params=None):
    """Prefix check that fails on omitted rows/NaNs instead of ignoring them.

    This is a regression check, not a proof of causality. Strategy review and
    focused tests remain necessary. Uses in-sample observations only.
    """
    params = params or {}
    full = function(frame, **params)
    validate_target(full, frame)
    cuts = sorted({max(1, int(len(frame) * f)) for f in (.25, .5, .75, .9, 1)})
    for n in cuts:
        part = function(frame.iloc[:n], **params)
        validate_target(part, frame.iloc[:n])
        if not np.array_equal(part.to_numpy(), full.iloc[:n].to_numpy()):
            raise ValueError(f"Signal changes when future rows are removed at prefix {n}")
    return full


def simulate(frame, target, config=None, *, cost_mult=1.0):
    config = config or Execution()
    config.validate()
    if not np.isfinite(cost_mult) or cost_mult <= 0:
        raise ValueError("cost_mult must be positive")
    validate_target(target, frame)
    if len(frame) < 2 or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Need at least two unique increasing quote bars")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("Quote bars must have a timezone-aware index")
    if frame.instrument_id.nunique() != 1:
        raise ValueError("No implicit futures rolls: run one fixed contract at a time")
    needed = ["bid", "ask", "mid", "bid_size", "ask_size", "session", "valid"]
    if frame[needed].isna().any().any():
        # Invalid rows may contain missing quotes, but never mark them valid.
        if frame.loc[frame.valid, needed].isna().any().any():
            raise ValueError("A valid row contains missing quote fields")
    delay = pd.Timedelta(milliseconds=config.latency_ms)
    # UTC/session windows and sample end are fixed before testing. Liquidation
    # at their final grid row is scheduled, never selected by future quote quality.
    terminal = frame.session.ne(frame.session.shift(-1)).to_numpy()
    times, targets = frame.index, target.to_numpy(dtype=int)
    position, cash, entry_cash, entry_time = 0, 0.0, 0.0, None
    session, session_cash, halted, last_mid = None, 0.0, False, None
    cooldown_direction = 0
    risk_exit = None
    session_decision_time = None
    eligible, desired = -1, 0
    fills, rows = [], []
    fill_cols = ["time", "decision_time", "quantity", "price", "fee", "extra_cost", "reason"]
    for i, (ts, row) in enumerate(frame.iterrows()):
        if row.session != session:
            if position:
                raise ValueError("Position crossed an unliquidated session boundary")
            session, session_cash, halted = row.session, cash, False
            eligible, desired, cooldown_direction = i - 1, 0, 0
            risk_exit = None
            session_decision_time = ts
        # Only past decisions can be eligible, even with zero configured latency.
        while eligible + 1 < i and times[eligible + 1] + delay <= ts:
            eligible += 1
            desired = targets[eligible]
        good = bool(row.valid) and all(np.isfinite(row[k]) for k in ("bid", "ask", "mid"))
        good = good and row.ask > row.bid and row.bid_size > 0 and row.ask_size > 0
        if good:
            last_mid = row.mid
        equity = cash + (position * last_mid * config.multiplier if last_mid is not None else 0)
        if equity - session_cash <= -config.daily_loss_dollars:
            halted = True
            if position and risk_exit is None:
                risk_exit = (ts, "daily_loss")
        reason = "signal"
        decision_time = times[eligible] if eligible >= 0 else pd.NaT
        wanted = desired
        if desired != cooldown_direction:
            cooldown_direction = 0
        if cooldown_direction:
            wanted = 0
        holding_deadline = False
        if position:
            elapsed = (ts - entry_time).total_seconds()
            pnl = equity - entry_cash
            holding_deadline = elapsed >= config.max_hold_seconds
            if pnl <= -config.stop_loss_dollars and risk_exit is None:
                risk_exit = (ts, "stop_loss")
        if not good:
            # The signal resets while data is unavailable; liquidation waits for
            # a real valid quote after the observed fault plus execution latency.
            # Retain the first request instead of postponing it on each bad bar.
            if position and risk_exit is None:
                risk_exit = (ts, "invalid_data_exit")
            # Forget all decisions before the bad row, even if their latency
            # would otherwise make them eligible on recovery.
            eligible, desired = i, 0
            wanted = position
        if risk_exit is not None:
            trigger, reason = risk_exit
            decision_time = trigger
            # A threshold observed at this row cannot use this row's quote,
            # even when configured latency is zero. Keep marking the position.
            due = ts > trigger and ts >= trigger + delay
            wanted = 0 if due else position
        if halted:
            # A halt blocks new exposure immediately; an existing position must
            # still wait for its pending exit's observable execution time.
            if not position:
                wanted = 0
        if holding_deadline:
            wanted, reason, decision_time = 0, "time_limit", entry_time
        if terminal[i]:
            wanted, reason, decision_time = 0, "scheduled_close", session_decision_time
        if good and wanted != position:
            spread_ticks = (row.ask - row.bid) / config.tick_size
            # Avoid opening or reversing into wide spreads; exits stay allowed.
            if spread_ticks > config.max_spread_ticks and wanted:
                wanted = 0
                reason = "spread_limit"
            qty = wanted - position
            if qty:
                depth = row.ask_size if qty > 0 else row.bid_size
                if depth < abs(qty):
                    if terminal[i] and position:
                        raise ValueError("Insufficient quoted depth to liquidate at scheduled close")
                else:
                    price = row.ask if qty > 0 else row.bid
                    # Spread paid in price; x2 stress adds another half-spread
                    # per side as well as doubling explicit fees/slippage.
                    extra = abs(qty) * config.multiplier * (
                        config.slippage_ticks * config.tick_size * cost_mult +
                        (cost_mult - 1) * (row.ask - row.bid) / 2)
                    fee = abs(qty) * config.fee_per_side * cost_mult
                    before = equity
                    cash -= qty * price * config.multiplier + fee + extra
                    fills.append(dict(time=ts,
                                      decision_time=decision_time,
                                      quantity=qty, price=price, fee=fee, extra_cost=extra, reason=reason))
                    if wanted and wanted != position:
                        entry_time, entry_cash = ts, before
                    if not wanted and reason in ("stop_loss", "time_limit"):
                        cooldown_direction = position
                    position = wanted
                    if not position:
                        risk_exit = None
        if terminal[i] and position:
            raise ValueError("No valid quote to liquidate at scheduled close; repair/narrow data window")
        equity = cash + (position * last_mid * config.multiplier if last_mid is not None else 0)
        if equity <= -config.capital:
            raise ValueError("Simulated capital exhausted")
        rows.append(dict(equity=config.capital + equity, pnl=equity, position=position, valid=good))
    curve = pd.DataFrame(rows, index=times)
    fills = pd.DataFrame(fills, columns=fill_cols)
    daily = curve.groupby(frame.session).equity.last()
    daily_return = daily.pct_change()
    daily_return.iloc[0] = daily.iloc[0] / config.capital - 1
    sharpe = None
    if len(daily_return) >= 20 and daily_return.std() > 0:
        sharpe = float(daily_return.mean() / daily_return.std() * np.sqrt(252))
    peak = curve.equity.cummax().clip(lower=config.capital)
    ann_return = ann_vol = None
    if len(daily_return) >= 20:
        ann_return = float((daily.iloc[-1] / config.capital) ** (252 / len(daily_return)) - 1)
        ann_vol = float(daily_return.std() * np.sqrt(252))
    summary = dict(net_pnl=float(curve.pnl.iloc[-1]), return_on_capital=float(curve.pnl.iloc[-1] / config.capital),
                   max_drawdown=float((curve.equity / peak - 1).min()), daily_sharpe=sharpe,
                   ann_return=ann_return, ann_vol=ann_vol,
                   sessions=len(daily), fills=len(fills),
                   contracts_traded=int(fills.quantity.abs().sum()) if len(fills) else 0,
                   invalid_bars=int((~curve.valid).sum()),
                   exposure_fraction=float(curve.position.ne(0).mean()))
    return MicroResult(curve, fills, summary)
