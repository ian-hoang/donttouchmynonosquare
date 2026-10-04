"""Event study for roll_tas on IN-SAMPLE data: does the TAS flow predict the settlement-window move?

    uv run python research/roll_tas_events.py

Leg A = front-contract return from 14:15 ET to settlement; leg B = settlement to 16:30 ET.
Prints dose-response tables (quintiles of the signal), the index-roll-day split and a by-year view.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import strategies  # noqa: E402
from gqh import research  # noqa: E402
from gqh.analysis import bucket_table  # noqa: E402
from strategies.roll_tas import ET  # noqa: E402

pd.set_option("display.width", 140)


def business_day_of_month(days: pd.DatetimeIndex) -> np.ndarray:
    d = days.tz_localize(None).to_numpy().astype("datetime64[D]")
    start = days.tz_localize(None).to_period("M").start_time.to_numpy().astype("datetime64[D]")
    return np.busday_count(start, d) + 1


def main():
    strat = strategies.get("roll_tas")
    prep = research.prepare(strat)
    t = prep.in_sample
    p = strat.defaults
    ev = pd.DataFrame({
        "legA": t["settle"] / t["pre"] - 1,
        "legB": t["post"] / t["settle"] - 1,
        "z_offset": strat.signal(t, "offset", p["z_window"]),
        "z_imbalance": strat.signal(t, "imbalance", p["z_window"]),
        "offset": t["offset"], "imbalance": t["imbalance"], "tas_volume": t["tas_volume"],
    })
    days = t.index.tz_convert(ET).normalize()
    ev["roll_day"] = (business_day_of_month(days) >= 5) & (business_day_of_month(days) <= 9)
    ev["year"] = days.year
    print(f"In-sample days: {len(ev):,} ({days.min():%Y-%m-%d} to {days.max():%Y-%m-%d}); "
          f"out-of-sample starts {prep.oos_start:%Y-%m-%d} and is not touched here.\n")

    for sig in ("z_offset", "z_imbalance"):
        for leg in ("legA", "legB"):
            print(f"--- {leg} return (bp) by quintile of {sig} ---")
            print(bucket_table(ev[sig], ev[leg]).round(2).to_string(), "\n")

    print("--- Mechanism: correlation of signal with leg A / leg B, roll days (GSCI bd 5-9) vs other days ---")
    rows = {}
    for label, g in (("roll days", ev[ev["roll_day"]]), ("other days", ev[~ev["roll_day"]]), ("all", ev)):
        rows[label] = {f"{s}->{l}": g[s].corr(g[l]) for s in ("z_offset", "z_imbalance") for l in ("legA", "legB")}
        rows[label]["n"] = len(g)
    print(pd.DataFrame(rows).T.round(3).to_string(), "\n")

    print("--- By year: mean signed leg A return, sign(z_offset) x legA (bp) ---")
    signed = np.sign(ev["z_offset"]) * ev["legA"] * 1e4
    print(signed.groupby(ev["year"]).mean().round(2).to_frame("bp").T.to_string())


if __name__ == "__main__":
    main()
