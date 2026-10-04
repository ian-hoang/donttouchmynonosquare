"""Roll-Flow leg 2: open interest still sitting in the front contract predicts the front-vs-next spread.

Hypothesis: hypotheses/roll_oi.md (incl. the amendment narrowing the universe before any backtest).
Universe: CL HO RB NG (energy) and HE GF (cash-settled), which can be held to expiry without delivery risk.

Rows are trading days stamped 17:00 ET (after every settlement). Open interest for day T is published around
21:30 ET on T, so a decision on day T only uses open interest through T-1.
  roll leg:        business days 1-9 of a month whose front expires within `roll_dte` business days:
                   short front / long next, size fixed at entry from the residual front share
  liquidation leg: last `liq_dte` business days before expiry: long front / short next, sized by the front share
"""
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from gqh import data as gd
from strategies.base import BaseStrategy

ET = "America/New_York"
ROOTS = ["CL", "HO", "RB", "NG", "HE", "GF"]
ALL_ROOTS = "CL HO RB NG ZC ZS ZW KE ZL ZM LE HE GF GC SI HG".split()  # the cached download covers all 16
START, END = "2010-07-01", "2026-10-01"
HOLIDAYS = USFederalHolidayCalendar().holidays("2010-01-01", "2027-12-31").values.astype("datetime64[D]")
# (typical price, tick, $ per point) from CME specs, for per-contract costs
SPECS = {"CL": (70, 0.01, 1000), "HO": (2.5, 0.0001, 42000), "RB": (2.2, 0.0001, 42000),
         "NG": (3.0, 0.001, 10000), "HE": (0.85, 0.00025, 40000), "GF": (2.5, 0.00025, 50000)}


def _bdays_between(a: pd.Series, b: pd.Series) -> np.ndarray:
    return np.busday_count(a.to_numpy().astype("datetime64[D]"), b.to_numpy().astype("datetime64[D]"),
                           holidays=HOLIDAYS)


class RollOI(BaseStrategy):
    defaults = {"legs": "RL", "sizing": "residual", "roll_dte": 25, "liq_dte": 5, "cycles": 24}
    cost_bps = {f"{r}.c.{k}": gd.futures_cost_bps(*SPECS[r], fee_per_contract=2.5) for r in ROOTS for k in (0, 1)}

    def load(self):
        stats = gd.databento_chunked("GLBX.MDP3", [f"{r}.c.{k}" for r in ALL_ROOTS for k in (0, 1)], "statistics",
                                     START, END, stype_in="continuous")
        defs = gd.databento_chunked("GLBX.MDP3", [f"{r}.c.{k}" for r in ROOTS for k in (0, 1)], "definition",
                                    START, END, stype_in="continuous")
        return self._daily_table(stats, defs)

    @staticmethod
    def _daily_table(stats, defs) -> pd.DataFrame:
        """Long table: one row per (day, symbol) with settlement, instrument, open interest, expiration."""
        s = stats[stats["symbol"].str.split(".").str[0].isin(ROOTS)].copy()
        s["day"] = s["ts_ref"].dt.tz_localize(None).dt.normalize()
        settle = (s[s["stat_type"] == 3].groupby(["day", "symbol"])
                  .agg(settle=("price", "last"), instrument_id=("instrument_id", "last")))
        oi = s[s["stat_type"] == 9].groupby(["day", "instrument_id"])["quantity"].last().rename("oi")
        volume = s[s["stat_type"] == 6].groupby(["day", "instrument_id"])["quantity"].last().rename("volume")
        t = (settle.reset_index().merge(oi.reset_index(), on=["day", "instrument_id"], how="left")
             .merge(volume.reset_index(), on=["day", "instrument_id"], how="left"))
        expiry = (defs.drop_duplicates("instrument_id", keep="last").set_index("instrument_id")["expiration"]
                  .dt.tz_convert(ET).dt.tz_localize(None).dt.normalize())
        t["expiration"] = t["instrument_id"].map(expiry)
        t = t[t["settle"] > 0].dropna(subset=["expiration"])
        # Databento's CME statistics carry open interest only from Nov 2015; start there so the strategy and
        # its placebo cover the same days
        t = t[t["day"] >= oi.index.get_level_values("day").min()]
        # Stamp each day at 17:00 ET, after every settlement (OI for that day arrives later, ~21:30 ET)
        t["ts"] = (t["day"].dt.tz_localize(ET) + pd.Timedelta(hours=17)).dt.tz_convert("UTC")
        return t.set_index("ts").sort_index()

    def asset_returns(self, table) -> pd.DataFrame:
        bars = table.rename(columns={"settle": "close"}).rename_axis("ts_event")
        r = gd.roll_safe_returns(bars)
        return r.reindex(columns=[f"{root}.c.{k}" for root in ROOTS for k in (0, 1)])

    def dollar_volume(self, table) -> pd.DataFrame:
        """Cleared volume x settlement x $ per price point, per contract per day (for the capacity estimate)."""
        # Databento prices: CL/NG in $, HO/RB in $/gallon, HE/GF in cents/lb (so $ per point = lbs / 100)
        dollars_per_point = {"CL": 1000, "HO": 42000, "RB": 42000, "NG": 10000, "HE": 400, "GF": 500}
        mult = table["symbol"].str.split(".").str[0].map(dollars_per_point)
        dv = (table["volume"] * table["settle"] * mult).rename("dv")
        out = pd.concat([dv, table["symbol"]], axis=1).reset_index().pivot_table(index="ts", columns="symbol", values="dv")
        return out.reindex(columns=[f"{root}.c.{k}" for root in ROOTS for k in (0, 1)])

    def signals(self, table, roll_dte, liq_dte, cycles) -> pd.DataFrame:
        """Per root and day: days to expiry, front OI share known at the decision, and its residual."""
        out = []
        for root in ROOTS:
            f = table[table["symbol"] == f"{root}.c.0"]
            n = table[table["symbol"] == f"{root}.c.1"]
            d = pd.DataFrame({"day": f["day"], "front_oi": f["oi"], "front_exp": f["expiration"]})
            d["next_oi"] = n["oi"].reindex(d.index)
            d["share"] = (d["front_oi"] / (d["front_oi"] + d["next_oi"])).shift(1)  # yesterday's OI only
            d["dte"] = _bdays_between(d["day"], d["front_exp"])
            # Residual vs the same days-to-expiry in previous contract cycles (past only)
            by_dte = d.groupby("dte")["share"]
            med = by_dte.transform(lambda x: x.shift(1).rolling(cycles, min_periods=6).median())
            sd = by_dte.transform(lambda x: x.shift(1).rolling(cycles, min_periods=6).std())
            d["resid_z"] = (d["share"] - med) / sd
            bday = pd.Series(np.busday_count(d["day"].dt.to_period("M").dt.start_time.to_numpy().astype("datetime64[D]"),
                                             d["day"].to_numpy().astype("datetime64[D]"), holidays=HOLIDAYS) + 1,
                             index=d.index)
            d["roll_window"] = (bday <= 9) & (d["dte"] <= roll_dte) & (d["dte"] > liq_dte)
            d["liq_window"] = (d["dte"] <= liq_dte) & (d["dte"] >= 1)
            d["root"] = root
            out.append(d)
        return pd.concat(out)

    def weights(self, table, legs, sizing, roll_dte, liq_dte, cycles) -> pd.DataFrame:
        sig = self.signals(table, roll_dte, liq_dte, cycles)
        idx = table.index.unique().sort_values()
        w = pd.DataFrame(0.0, index=idx, columns=[f"{r}.c.{k}" for r in ROOTS for k in (0, 1)])
        for root, d in sig.groupby("root"):
            d = d.sort_index()
            for leg, window, sign in (("R", "roll_window", -1.0), ("L", "liq_window", +1.0)):
                if leg not in legs:
                    continue
                on = d[window].fillna(False)
                block = (on != on.shift()).cumsum()[on]          # one id per contiguous window
                if sizing == "constant":
                    raw = pd.Series(0.5, index=d.index)
                elif leg == "R":
                    raw = (d["resid_z"].clip(0, 2) / 2).fillna(0.0)  # only when more roll than usual remains
                else:
                    raw = d["share"].clip(0, 1).fillna(0.0)          # remaining front open interest
                entry = raw[on].groupby(block).transform("first")  # size fixed at window entry
                s = sign * entry / len(ROOTS)
                w.loc[s.index, f"{root}.c.0"] += s
                w.loc[s.index, f"{root}.c.1"] -= s
        return w


STRATEGY = RollOI
