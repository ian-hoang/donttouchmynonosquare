"""Single-instrument GLBX.MDP3 MBO -> causal, completed research bars.

Use DBNStore.to_df(price_type='float'); preserve file/message order. This replay
supports true MBO only, never MBP synthesized into MBO. Book updates follow
Databento normalization: F/T do not mutate orders, C subtracts size, M replaces
size. Quotes and flow become observable only at F_LAST. Fill-associated removals
are excluded from the voluntary-cancellation proxy.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import heapq

import numpy as np
import pandas as pd

LAST, SNAPSHOT, TOB, MBP, BAD_RECV, BAD_BOOK = 128, 32, 64, 16, 8, 4
FLOWS = ("buy_volume", "sell_volume", "trade_volume", "bid_add", "ask_add",
         "bid_cancel", "ask_cancel", "bid_priority_cancel", "ask_priority_cancel", "unattributed_fill_volume")


@dataclass(slots=True)
class Order:
    side: str
    price: float
    size: int


class Book:
    def __init__(self):
        self.orders = {}
        self.levels = {"B": {}, "A": {}}
        self.totals = {"B": {}, "A": {}}
        self.heaps = {"B": [], "A": []}
        self.heap_prices = {"B": set(), "A": set()}
        self.filled = defaultdict(int)

    def best(self, side):
        heap = self.heaps[side]
        sign = -1 if side == "B" else 1
        while heap and sign * heap[0] not in self.levels[side]:
            self.heap_prices[side].remove(sign * heapq.heappop(heap))
        return sign * heap[0] if heap else np.nan

    def quote(self):
        bid, ask = self.best("B"), self.best("A")
        return dict(bid=bid, ask=ask,
                    bid_size=self.totals["B"].get(bid, 0),
                    ask_size=self.totals["A"].get(ask, 0))

    def _remove(self, oid):
        order = self.orders.pop(oid)
        level = self.levels[order.side][order.price]
        self.totals[order.side][order.price] -= level.pop(oid)
        if not level:
            del self.levels[order.side][order.price]
            del self.totals[order.side][order.price]

    def _add(self, oid, side, price, size):
        if oid in self.orders:
            raise ValueError(f"Duplicate add for order {oid}; bad/incomplete MBO stream")
        if price not in self.levels[side]:
            self.levels[side][price] = {}
            self.totals[side][price] = 0
            # A removed, off-touch price can still be present in the lazy heap.
            # Reusing its entry avoids unbounded duplicate-price accumulation.
            if price not in self.heap_prices[side]:
                heapq.heappush(self.heaps[side], price * (-1 if side == "B" else 1))
                self.heap_prices[side].add(price)
        self.levels[side][price][oid] = size
        self.totals[side][price] += size
        self.orders[oid] = Order(side, price, size)

    def apply(self, action, side, price, size, oid):
        """Return flow increments; explicit C only is the cancellation proxy."""
        flow = defaultdict(float)
        if action == "R":
            self.__init__()
        elif action == "T":
            flow["trade_volume"] = size
            if side in ("B", "A"):
                flow["buy_volume" if side == "B" else "sell_volume"] = size
        elif action == "F":
            if oid not in self.orders:
                # Trade Summary can attribute a fill to a transient/non-displayed
                # order that never has an A/M/C in the displayed book. F never
                # creates an order or another trade. Log and quarantine its bar.
                flow["unattributed_fill_volume"] += size
            else:
                self.filled[oid] += size
        elif action == "N":
            pass
        elif action in ("A", "C", "M"):
            if side not in ("B", "A") or not np.isfinite(price) or abs(price) > 1e9 or size < 0:
                raise ValueError("Invalid MBO side, price or size")
            prefix = "bid" if side == "B" else "ask"
            old = self.orders.get(oid)
            if action == "A":
                self._add(oid, side, price, size)
                if price == self.best(side):
                    flow[f"{prefix}_add"] += size
            elif action == "C":
                if old is None:
                    raise ValueError("Cancel for unknown order: start at a UTC-day MBO snapshot")
                if old.side != side or old.price != price or size > old.size:
                    raise ValueError("Cancel inconsistent with reconstructed order")
                executed = min(size, self.filled.get(oid, 0))
                self.filled[oid] -= executed
                voluntary = size - executed
                if price == self.best(side) and voluntary:
                    ahead = 0
                    for key, qty in self.levels[side][price].items():
                        if key == oid:
                            break
                        ahead += qty
                    flow[f"{prefix}_cancel"] += voluntary
                    flow[f"{prefix}_priority_cancel"] += voluntary / (1 + ahead)
                old.size -= size
                if old.size:
                    self.levels[side][price][oid] = old.size
                    self.totals[side][price] -= size
                else:
                    self._remove(oid)
                    self.filled.pop(oid, None)
            else:
                if old is None:
                    raise ValueError("Modify for unknown order: incomplete MBO history")
                if old.side != side:
                    raise ValueError("Order changed sides")
                # A modified size is the NEW displayed size. It is not a fill.
                added = max(0, size - old.size) if price == old.price else size
                if size == 0:
                    self._remove(oid)
                elif price != old.price or size > old.size:
                    self._remove(oid)
                    self._add(oid, side, price, size)
                else:
                    self.totals[side][price] += size - old.size
                    old.size = size
                    self.levels[side][price][oid] = size
                self.filled.pop(oid, None)
                if price == self.best(side):
                    flow[f"{prefix}_add"] += added
        else:
            raise ValueError(f"Unsupported MBO action {action!r}")
        return flow


def mbo_features(events: pd.DataFrame, *, interval="1s", max_quote_age="2s",
                 max_bars=1_000_000) -> pd.DataFrame:
    """Replay one DataFrame; see :func:`mbo_features_iter` for bounded input RAM."""
    return mbo_features_iter((events,), interval=interval,
                             max_quote_age=max_quote_age, max_bars=max_bars)


def mbo_features_iter(chunks, *, interval="1s", max_quote_age="2s",
                      max_bars=1_000_000) -> pd.DataFrame:
    """Replay one-pass DataFrame chunks into completed [t-interval,t) bars.

    Only finalized events are exposed. Snapshot adds never count as order flow.
    A complete leading snapshot/reset is required. Daily snapshots preserve
    priority but cannot establish order age. Gaps yield invalid bars, not zero
    returns or implicit good quotes. One outright/instrument/publisher only.

    Chunk boundaries have no market meaning: one book and pending event survive
    across all chunks, including tied timestamps and partial snapshots. A bar
    is emitted only when a later record reaches its end, so the unfinished tail
    is dropped. Input memory is bounded by the current chunk plus the book;
    output memory is bounded by ``max_bars``. For example, pass the iterator from
    ``DBNStore.to_df(price_type='float', count=250_000)`` directly.
    """
    required = {"action", "side", "price", "size", "order_id", "flags", "instrument_id"}
    step, age = pd.Timedelta(interval), pd.Timedelta(max_quote_age)
    if pd.isna(step) or pd.isna(age) or step <= pd.Timedelta(0) or age < pd.Timedelta(0):
        raise ValueError("interval must be positive and max_quote_age nonnegative")
    if isinstance(max_bars, (bool, np.bool_)) or not np.isfinite(max_bars) or int(max_bars) != max_bars or max_bars < 1:
        raise ValueError("max_bars must be a positive integer")
    step_ns, age_ns = step.value, age.value
    output, book, pending = [], Book(), defaultdict(float)
    flows = defaultdict(float)
    quote = dict(bid=np.nan, ask=np.nan, bid_size=0, ask_size=0)
    quote_ns = None
    start_ns = next_bar_ns = previous_ns = None
    identities = None
    interrupted = False
    event_complete = True
    bar_error = None

    def finish():
        valid = (not interrupted and event_complete and quote_ns is not None and next_bar_ns - quote_ns <= age_ns and
                 np.isfinite(quote["bid"]) and np.isfinite(quote["ask"]) and
                 quote["ask"] > quote["bid"] and quote["bid_size"] > 0 and quote["ask_size"] > 0)
        output.append({**quote, **{c: flows[c] for c in FLOWS}, "valid": bool(valid),
                       "quote_time": pd.Timestamp(quote_ns, tz="UTC") if quote_ns is not None else None})
        flows.clear()

    columns = ["action", "side", "price", "size", "order_id", "flags"]
    for events in chunks:
        if not isinstance(events, pd.DataFrame):
            raise TypeError("MBO chunks must be pandas DataFrames")
        if not required.issubset(events.columns):
            raise ValueError(f"Missing MBO fields: {sorted(required - set(events.columns))}")
        if not isinstance(events.index, pd.DatetimeIndex) or events.index.tz is None:
            raise ValueError("Nonempty MBO with a timezone-aware ts_recv index is required")
        if events.empty:
            continue
        if events.index.hasnans or not events.index.is_monotonic_increasing:
            raise ValueError("Preserve monotonic ts_recv/file order; do not sort tied events")
        times = events.index.tz_convert("UTC").as_unit("ns").asi8
        if previous_ns is not None and int(times[0]) < previous_ns:
            raise ValueError("Preserve monotonic ts_recv/file order across chunks; do not sort tied events")
        current_ids = {}
        for field in ("instrument_id", "publisher_id"):
            if field in events:
                if events[field].nunique(dropna=False) != 1 or pd.isna(events[field].iloc[0]):
                    raise ValueError(f"Select exactly one {field}; continuous rolls are unsupported")
                current_ids[field] = events[field].iloc[0]
        if identities is None:
            identities = current_ids
            if events.iloc[0]["action"] != "R":
                raise ValueError("Start replay at a full snapshot (normally 00:00 UTC), not midway through a book")
            start_ns = next_bar_ns = (int(times[0]) // step_ns + 1) * step_ns
        elif current_ids != identities:
            raise ValueError("Select exactly one instrument_id/publisher_id across chunks; continuous rolls are unsupported")

        # Integer receive timestamps avoid constructing millions of Timestamp
        # objects; only completed-bar quote timestamps are materialized.
        for ts, values in zip(times, events[columns].itertuples(index=False, name=None)):
            ts = int(ts)
            while ts >= next_bar_ns:
                if len(output) >= max_bars:
                    raise ValueError(f"Expected 1..{max_bars} complete bars; use a bounded sample")
                if bar_error is not None:
                    raise bar_error
                finish()
                next_bar_ns += step_ns
                interrupted = False
            if bar_error is not None:
                continue
            try:
                action, side, price, size, oid, flags = values
                flags, size, oid = int(flags), int(size), int(oid)
                if flags & (TOB | MBP):
                    raise ValueError("Queue research requires true MBO, not synthesized MBP/top-of-book orders")
                if flags & BAD_BOOK:
                    raise ValueError("F_MAYBE_BAD_BOOK: unreliable book after a feed gap; use a complete healthy sample")
                if flags & BAD_RECV and not flags & SNAPSHOT:
                    raise ValueError("Bad receive timestamp outside snapshot; repair source data before research")
                if action == "R":
                    quote_ns = None
                    pending.clear()
                    flows.clear()
                    interrupted = True
                if flags & SNAPSHOT:
                    interrupted = True
                event_complete = bool(flags & LAST)
                increments = book.apply(str(action), str(side), float(price), size, oid)
                if increments.get("unattributed_fill_volume", 0):
                    interrupted = True
                if not flags & SNAPSHOT:
                    for key, val in increments.items():
                        pending[key] += val
                if flags & LAST:
                    quote = book.quote()
                    if not flags & SNAPSHOT:
                        quote_ns = ts
                        for key, val in pending.items():
                            flows[key] += val
                    pending.clear()
            except (ValueError, TypeError, OverflowError, KeyError) as exc:
                # The old whole-frame replay never processes its final partial
                # bar. Preserve that behavior: propagate a tail error only if a
                # later record completes this bar. No invalid bar is emitted.
                bar_error = exc
        previous_ns = int(times[-1])
    if identities is None:
        raise ValueError("Nonempty MBO with a timezone-aware ts_recv index is required")
    if not output:
        raise ValueError(f"Expected 1..{max_bars} complete bars, found 0; use a bounded sample")
    grid = pd.date_range(pd.Timestamp(start_ns, tz="UTC"), periods=len(output), freq=step, name="ts_decision")
    frame = pd.DataFrame(output, index=grid)
    frame["mid"] = (frame.bid + frame.ask) / 2
    frame["signed_volume"] = frame.buy_volume - frame.sell_volume
    frame["instrument_id"] = int(identities["instrument_id"])
    frame["session"] = frame.index.strftime("%Y-%m-%d")
    return frame


def synthetic_features(n=3600, seed=7):
    """Deliberately artificial smoke fixture, never evidence for an edge."""
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-09-01T13:30:00Z", periods=n, freq="1s", name="ts_decision")
    mid = 6000.125 + rng.choice([-0.25, 0, 0.25], n).cumsum()
    frame = pd.DataFrame(index=index)
    frame["bid"], frame["ask"] = mid - 0.125, mid + 0.125
    frame["mid"] = mid
    frame["bid_size"], frame["ask_size"] = rng.integers(20, 100, (2, n))
    for c in FLOWS:
        frame[c] = rng.poisson(3, n).astype(float)
    frame["unattributed_fill_volume"] = 0.0
    frame["trade_volume"] = frame.buy_volume + frame.sell_volume
    frame["signed_volume"] = frame.buy_volume - frame.sell_volume
    for side in ("bid", "ask"):
        frame[f"{side}_priority_cancel"] = frame[f"{side}_cancel"] / rng.integers(1, 20, n)
    frame["valid"], frame["instrument_id"] = True, 1
    frame["quote_time"] = index - pd.Timedelta("1ms")
    frame["session"] = index.strftime("%Y-%m-%d")
    return frame
