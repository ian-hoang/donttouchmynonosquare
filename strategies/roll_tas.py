"""Roll-Flow leg 1: the Trade-at-Settlement (TAS) premium in crude oil predicts the settlement-window move.

Hypothesis: hypotheses/roll_tas.md. Benchmark-tied traders (index funds, ETFs, hedgers) buy or sell CL at the
settlement price through TAS contracts. Dealers who take the other side hedge by trading the outright during the
14:28-14:30 ET settlement window, pushing price toward the TAS flow; the push reverses after settlement.

Each trading day has three rows (ET):
  14:15  decide using TAS trades up to 14:00; leg A holds from here into settlement
  14:30  settlement price; leg B holds from here (entered via TAS at settlement) to 16:30
  16:30  flat
"""
import numpy as np
import pandas as pd

from gqh import data as gd
from strategies.base import BaseStrategy

ET = "America/New_York"
START, END = "2012-01-01", "2026-10-01"
TIMES = {"pre": "14:15", "settle": "14:30", "post": "16:30"}


def _at(day_et: pd.DatetimeIndex, hhmm: str) -> pd.DatetimeIndex:
    h, m = map(int, hhmm.split(":"))
    return (day_et + pd.Timedelta(hours=h, minutes=m)).tz_convert("UTC")


class RollTAS(BaseStrategy):
    # measure: "offset" = volume-weighted TAS price offset from settlement (the hypothesis);
    #          "imbalance" = buyer- minus seller-initiated TAS volume (disclosed variant)
    defaults = {"measure": "offset", "z_window": 60, "threshold": 0.0, "legs": "AB", "cap": 2.0}
    # CL: tick $0.01 x 1,000 bbl at ~$70: half-spread + half-tick slippage + $2.50 fees ~ 1.8 bp per side
    cost_bps = round(gd.futures_cost_bps(70, 0.01, 1000, fee_per_contract=2.5), 2)

    def load(self):
        tas = gd.databento_chunked("GLBX.MDP3", ["CLT.FUT"], "trades", START, END, stype_in="parent")
        stats = gd.databento_chunked("GLBX.MDP3", ["CL.v.0"], "statistics", START, END, stype_in="continuous")
        bars = gd.databento_chunked("GLBX.MDP3", ["CL.v.0"], "ohlcv-1m", START, END, stype_in="continuous")
        symbols = gd.instrument_symbols("GLBX.MDP3", "CL.FUT", START, END)
        return self._daily_table(tas, stats, gd.stamp_bar_end(bars, "1m"), symbols)

    @staticmethod
    def _daily_table(tas, stats, bars, symbols) -> pd.DataFrame:
        """One row per trading day: prices at 14:15 / settlement / 16:30, and the TAS flow known by 14:00."""
        # Settlement of the volume-front contract, per trading day (last message wins: final over preliminary)
        st = stats[stats["stat_type"] == 3].copy()
        st["day"] = st["ts_ref"].dt.tz_localize(None).dt.normalize()
        settle = st.groupby("day").agg(settle=("price", "last"), instrument_id=("instrument_id", "last"))
        settle["outright"] = settle["instrument_id"].map(symbols)
        settle["tas_symbol"] = settle["outright"].str.replace("^CL", "CLT", regex=True)

        # Outright prices at 14:15 and 16:30 ET from 1-minute bars stamped at their end time
        day_et = settle.index.tz_localize(ET)
        b = bars[["close", "instrument_id"]].sort_index().rename_axis("t").reset_index()
        b["t"] = b["t"].astype("datetime64[ns, UTC]")
        out = pd.DataFrame(index=settle.index)
        for key in ("pre", "post"):
            at = pd.DataFrame({"t": _at(day_et, TIMES[key]).astype("datetime64[ns, UTC]")})
            snap = pd.merge_asof(at, b, on="t", direction="backward", tolerance=pd.Timedelta("10min"))
            out[key] = snap["close"].to_numpy()
            out[f"{key}_id"] = snap["instrument_id"].to_numpy()
        out = out.join(settle)
        same = (out["pre_id"] == out["instrument_id"]) & (out["post_id"] == out["instrument_id"])
        out = out[same & (out[["pre", "settle", "post"]] > 0).all(axis=1)]

        # TAS flow for each settlement day: trades from 18:00 ET the evening before up to 14:00 ET
        t = tas[~tas["symbol"].str.contains("-")].copy()
        local = t.index.tz_convert(ET)
        t["day"] = (local + pd.Timedelta(hours=9, minutes=30)).normalize().tz_localize(None)  # 14:30 cut-over
        t = t[(local - local.normalize()) <= pd.Timedelta(hours=14)]
        t = t[t["symbol"].to_numpy() == out["tas_symbol"].reindex(t["day"]).to_numpy()]  # front contract only
        signed = t["size"] * np.where(t["side"] == "B", 1, np.where(t["side"] == "A", -1, 0))
        flow = pd.DataFrame({"vol": t["size"], "px_vol": t["price"] * t["size"], "signed": signed, "day": t["day"]})
        flow = flow.groupby("day").sum()
        out["tas_volume"] = flow["vol"]
        out["offset"] = flow["px_vol"] / flow["vol"]          # ticks above/below settlement, volume-weighted
        out["imbalance"] = flow["signed"] / flow["vol"]       # +1 all buyer-initiated, -1 all seller-initiated
        out = out.dropna(subset=["offset"])
        # Index each day by 16:30 ET, when its last value is known, so truncating the table never leaks
        out.index = _at(out.index.tz_localize(ET), TIMES["post"])
        return out

    @staticmethod
    def _days(table: pd.DataFrame) -> pd.DatetimeIndex:
        return table.index.tz_convert(ET).normalize()

    def _rows(self, table: pd.DataFrame) -> pd.DataFrame:
        day_et = self._days(table)
        frames = [pd.DataFrame({"price": table[k].to_numpy(), "leg": k}, index=_at(day_et, TIMES[k]))
                  for k in ("pre", "settle", "post")]
        return pd.concat(frames).sort_index()

    def asset_returns(self, table) -> pd.DataFrame:
        rows = self._rows(table)
        r = rows["price"].pct_change()
        r[rows["leg"] == "pre"] = 0.0  # overnight 16:30 -> next 14:15 is never held (and may span a roll)
        return r.to_frame("CL")

    def signal(self, table, measure, z_window) -> pd.Series:
        """Today's TAS flow measured against its own trailing history (prior days only)."""
        x = table[measure]
        mu = x.rolling(z_window, min_periods=z_window // 2).mean().shift(1)
        sd = x.rolling(z_window, min_periods=z_window // 2).std().shift(1)
        return (x - mu) / sd

    def weights(self, table, measure, z_window, threshold, legs, cap) -> pd.DataFrame:
        z = self.signal(table, measure, z_window)
        size = (z.clip(-cap, cap) / cap).where(z.abs() >= threshold, 0.0).fillna(0.0)
        day_et = self._days(table)
        a = pd.Series(size.to_numpy() if "A" in legs else 0.0, index=_at(day_et, TIMES["pre"]))
        b = pd.Series(-size.to_numpy() if "B" in legs else 0.0, index=_at(day_et, TIMES["settle"]))
        flat = pd.Series(0.0, index=_at(day_et, TIMES["post"]))
        return pd.concat([a, b, flat]).sort_index().to_frame("CL")


STRATEGY = RollTAS
