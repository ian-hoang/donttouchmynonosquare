"""Treasury auction concession: short the matching Treasury future into each coupon auction, long after it.

Hypothesis: hypotheses/treasury_auction.md. Dealers absorb pre-announced supply and demand a price concession;
prices cheapen before the 13:00 ET auction and recover after.

Rows are hourly bar END times. The position for an auction on day D:
  pre leg:  -w from 16:00 ET, k business days before D, until 13:00 ET on D (covered just before the result)
  post leg: +w from 13:00 ET on D until 16:00 ET the next business day
Positions are known in advance from the published auction calendar, so nothing depends on the result.
"""
import json
import urllib.request

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay

from gqh import CACHE
from gqh import data as gd
from strategies.base import BaseStrategy

ET = "America/New_York"
CONTRACTS = ["ZT", "ZF", "ZN", "ZB", "UB"]
TERM_TO_CONTRACT = {"2-Year": "ZT", "3-Year": "ZT", "5-Year": "ZF", "7-Year": "ZN",
                    "10-Year": "ZN", "20-Year": "ZB", "30-Year": "UB"}
# Approximate futures durations (years), to give every auction trade the same rate risk (DV01).
DURATION = {"ZT": 1.9, "ZF": 4.1, "ZN": 6.3, "ZB": 11.5, "UB": 17.0}
BDAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())
AUCTIONS_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
                "?filter=auction_date:gte:2010-06-01,security_type:in:(Note,Bond)&page[size]=10000&sort=auction_date")


def treasury_auctions() -> pd.DataFrame:
    """Coupon auctions (notes and bonds, no TIPS/FRNs) from the U.S. Treasury Fiscal Data API, cached locally."""
    path = CACHE / "treasury_auctions.json"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(AUCTIONS_URL, timeout=60) as resp:
            path.write_bytes(resp.read())
    df = pd.DataFrame(json.loads(path.read_text())["data"])
    df = df[(df["inflation_index_security"] == "No") & (df["floating_rate"] == "No")]
    df = df[df["original_security_term"].isin(TERM_TO_CONTRACT)]
    out = pd.DataFrame({
        # Indexed by announcement time (~11:00 ET) so truncating the data also hides auctions not yet announced
        "announced": pd.to_datetime(df["announcemt_date"]) + pd.Timedelta(hours=11),
        "date": pd.to_datetime(df["auction_date"]),
        "term": df["original_security_term"],
        "contract": df["original_security_term"].map(TERM_TO_CONTRACT),
        "offering_bn": pd.to_numeric(df["offering_amt"], errors="coerce") / 1e9,
        "reopening": df["reopening"].eq("Yes"),
    })
    years = out["term"].str.split("-").str[0].astype(float)
    out["dv01_proxy"] = out["offering_bn"] * years  # $bn x maturity: how much rate risk is being sold
    out["announced"] = out["announced"].dt.tz_localize(ET).dt.tz_convert("UTC")
    return out.sort_values("announced").set_index("announced")


# Per-side cost per contract: half a tick of spread + half a tick of slippage + $1.50 fees, at typical prices.
# (price, tick size in points, $ per point) from CME contract specs.
SPECS = {"ZT": (104, 1 / 256, 2000), "ZF": (108, 1 / 128, 1000), "ZN": (111, 1 / 64, 1000),
         "ZB": (118, 1 / 32, 1000), "UB": (125, 1 / 32, 1000)}


class TreasuryAuction(BaseStrategy):
    # post=False: the event study showed the post-auction rally is just as large in placebo windows,
    # so it isn't an auction effect. min_size keeps auctions above that quantile of PAST auction sizes.
    defaults = {"k": 2, "post": False, "size": "equal", "min_size": 0.0, "placebo_shift": 0}
    cost_bps = {f"{c}.v.0": gd.futures_cost_bps(p, t, m, fee_per_contract=1.5) for c, (p, t, m) in SPECS.items()}

    def load(self):
        bars = gd.databento_chunked("GLBX.MDP3", [f"{c}.v.{k}" for c in CONTRACTS for k in (0, 1)], "ohlcv-1h",
                            "2010-07-01", "2026-10-01", stype_in="continuous")
        return {"bars": gd.stamp_bar_end(bars, "1h"), "auctions": treasury_auctions()}

    def asset_returns(self, data) -> pd.DataFrame:
        r = gd.roll_safe_returns(data["bars"])
        return r[[f"{c}.v.0" for c in CONTRACTS]]

    def weights(self, data, k, post, size, min_size, placebo_shift) -> pd.DataFrame:
        returns = self.asset_returns(data)
        rows = returns.index
        local = rows.tz_convert(ET)
        day = local.normalize().tz_localize(None)
        hour = local.hour
        auctions = data["auctions"]  # everything announced so far, including auctions still to come
        w = pd.DataFrame(0.0, index=rows, columns=returns.columns)
        # Size relative to the median auction, using only auctions announced so far (no future sizes)
        median_dv01 = auctions["dv01_proxy"].expanding().median().to_numpy()
        cutoff = auctions["dv01_proxy"].expanding().quantile(min_size).to_numpy()
        for i, (announced, a) in enumerate(auctions.iterrows()):
            if a["dv01_proxy"] < cutoff[i]:
                continue
            s = a["dv01_proxy"] / median_dv01[i] if size == "dv01" else 1.0
            d = a["date"] + placebo_shift * BDAY
            col = f"{a['contract']}.v.0"
            size_c = s * DURATION["ZN"] / DURATION[a["contract"]]
            announced_day = announced.tz_convert(ET).normalize().tz_localize(None)
            start = max(d - k * BDAY, announced_day)  # can't position before the auction is announced
            pre = ((day == start) & (hour >= 16)) | ((day > start) & (day < d)) | ((day == d) & (hour < 13))
            w.loc[pre, col] -= size_c
            if post:
                nxt = d + BDAY
                after = ((day == d) & (hour >= 13)) | ((day == nxt) & (hour < 16))
                w.loc[after, col] += size_c
        return w


STRATEGY = TreasuryAuction
