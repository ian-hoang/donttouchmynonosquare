"""Idea 2 — Month-end index extension sized by the auction calendar (pre-registered in alpha_ideas/PREREGISTRATION.md).

Run from the repo root:  uv run python alpha_ideas/month_end_extension/run.py

Bond index funds buy longer bonds when the Treasury index extends at month-end; the extension should be bigger when a
lot of new long-dated supply settles that month. Proxy for month m = sum over nominal coupon auctions issued in m of
offering ($bn) x original term (years). Big month = proxy above the median of the previous 24 months.
Primary test: UB return from the 16:00 close on L-3 to the 15:00 close on L (L = last business day), big minus small
months, Welch t, prediction > 0. Spec choices are written in results.md before the first run.

Outputs (in this folder): months.csv (one row per month), run_output.txt (everything printed below).
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pandas.tseries.holiday import USFederalHolidayCalendar  # noqa: E402
from pandas.tseries.offsets import CustomBusinessDay  # noqa: E402
from scipy import stats  # noqa: E402

from gqh import CACHE  # noqa: E402
from gqh import data as gd  # noqa: E402
from strategies.treasury_auction import DURATION, SPECS  # noqa: E402  (read-only import)

ET = "America/New_York"
BDAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())
CONTRACTS = ["ZT", "ZF", "ZN", "ZB", "UB"]
NOMINAL_TERMS = {"2-Year": 2, "3-Year": 3, "5-Year": 5, "7-Year": 7, "10-Year": 10, "20-Year": 20, "30-Year": 30}
FIRST_MONTH, LAST_MONTH = pd.Period("2010-08", "M"), pd.Period("2026-09", "M")
HISTORY = 24
FLAT_RATIO = DURATION["UB"] / DURATION["ZT"]  # 17.0 / 1.9, as pre-registered
assert abs(FLAT_RATIO - 17.0 / 1.9) < 1e-12


def per_side_cost(contract: str) -> tuple[float, float]:
    """(dollars, bp of notional at the spec price) per contract per side: 0.5 tick spread + 0.5 tick slip + $1.50."""
    price, tick, mult = SPECS[contract]
    return (0.5 + 0.5) * tick * mult + 1.5, gd.futures_cost_bps(price, tick, mult, fee_per_contract=1.5)


# ----------------------------------------------------------------------------------------------- data
def load_auctions() -> pd.DataFrame:
    df = pd.DataFrame(json.loads((CACHE / "treasury_auctions.json").read_text())["data"])
    df = df[(df["inflation_index_security"] == "No") & (df["floating_rate"] == "No")]
    assert set(df["original_security_term"]) <= set(NOMINAL_TERMS), set(df["original_security_term"])
    out = pd.DataFrame({
        "auction_date": pd.to_datetime(df["auction_date"]),
        "announced": (pd.to_datetime(df["announcemt_date"]) + pd.Timedelta(hours=11)).dt.tz_localize(ET),
        "issue_date": pd.to_datetime(df["issue_date"]),
        "term": df["original_security_term"],
        "years": df["original_security_term"].map(NOMINAL_TERMS).astype(float),
        "offering_bn": pd.to_numeric(df["offering_amt"], errors="coerce") / 1e9,
        "reopening": df["reopening"].eq("Yes"),
    })
    assert out["offering_bn"].notna().all()
    out["bn_years"] = out["offering_bn"] * out["years"]
    out["month"] = out["issue_date"].dt.to_period("M")
    return out


class Path_:
    """Cumulative log return of one continuous contract, for fast window returns over bar END times."""

    def __init__(self, r: pd.Series, close: pd.Series):
        self.t = r.index.as_unit("ns").asi8
        self.cum = np.concatenate([[0.0], np.cumsum(np.log1p(r.to_numpy()))])
        self.close_t = close.index.as_unit("ns").asi8
        self.close = close.to_numpy()
        self.last = self.t[-1]

    def window(self, a: pd.Timestamp, b: pd.Timestamp) -> dict:
        """Return over bars whose END time is in (a, b]."""
        ia, ib = a.value, b.value
        if ib > self.last or ia < self.t[0]:
            return {"ret": np.nan, "n": 0}
        ka = np.searchsorted(self.t, ia, side="right")
        kb = np.searchsorted(self.t, ib, side="right")
        if kb - ka <= 0:
            return {"ret": np.nan, "n": 0}
        kc = np.searchsorted(self.close_t, ia, side="right") - 1
        return {"ret": float(np.expm1(self.cum[kb] - self.cum[ka])), "n": int(kb - ka),
                "first": pd.Timestamp(self.t[ka], tz="UTC"), "last": pd.Timestamp(self.t[kb - 1], tz="UTC"),
                "exact": bool(ka > 0 and self.t[ka - 1] == ia and self.t[kb - 1] == ib),
                "px_start": float(self.close[kc])}


def load_futures() -> dict[str, Path_]:
    bars = gd.databento_chunked("GLBX.MDP3", [f"{c}.v.{k}" for c in CONTRACTS for k in (0, 1)], "ohlcv-1h",
                                "2010-07-01", "2026-10-01", stype_in="continuous")
    bars = gd.stamp_bar_end(bars, "1h")
    r = gd.roll_safe_returns(bars)
    return {c: Path_(r[f"{c}.v.0"].dropna(), bars.loc[bars["symbol"] == f"{c}.v.0", "close"].sort_index())
            for c in CONTRACTS}


def et(day: pd.Timestamp, hour: int) -> pd.Timestamp:
    return (pd.Timestamp(day) + pd.Timedelta(hours=hour)).tz_localize(ET).tz_convert("UTC")


def last_bday(month: pd.Period) -> pd.Timestamp:
    return pd.date_range(month.start_time, month.end_time.normalize(), freq=BDAY)[-1]


# ----------------------------------------------------------------------------------------------- statistics
def welch(x: pd.Series, y: pd.Series) -> dict:
    x, y = x.dropna(), y.dropna()
    t, p = stats.ttest_ind(x, y, equal_var=False)
    return {"nb": len(x), "ns": len(y), "mb": x.mean(), "ms": y.mean(), "diff": x.mean() - y.mean(), "t": t,
            "p_one_sided": p / 2 if t > 0 else 1 - p / 2}


def fmt(w: dict, label: str) -> str:
    return (f"{label:<46s} big {w['mb']:+7.2f} bp (n={w['nb']})  small {w['ms']:+7.2f} bp (n={w['ns']})  "
            f"diff {w['diff']:+7.2f} bp  Welch t={w['t']:+5.2f}  p(one-sided)={w['p_one_sided']:.3f}")


def ols_hc1(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    X = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    inv = np.linalg.inv(X.T @ X)
    cov = inv @ (X.T * e**2) @ X @ inv * len(y) / (len(y) - 2)
    return beta[1], beta[1] / np.sqrt(cov[1, 1])


def nw_mean(values: pd.Series, grid: pd.DatetimeIndex, lags: int) -> tuple[float, float]:
    """Mean and Newey-West SE of observations on a business-day grid (missing days contribute zero)."""
    m = values.mean()
    e = (values - m).reindex(grid, fill_value=0.0).to_numpy()
    var = float(e @ e)
    for lag in range(1, lags + 1):
        var += 2 * (1 - lag / (lags + 1)) * float(e[lag:] @ e[:-lag])
    return m, np.sqrt(var) / len(values)


# ----------------------------------------------------------------------------------------------- main
def main():
    auctions = load_auctions()
    paths = load_futures()
    months = pd.period_range(FIRST_MONTH, LAST_MONTH, freq="M")
    proxy = auctions.groupby("month")["bn_years"].sum().reindex(months, fill_value=0.0)
    trailing = proxy.shift(1).rolling(HISTORY, min_periods=HISTORY).median()
    print(f"Nominal coupon auctions used: {len(auctions)} (issue dates {auctions['issue_date'].min().date()} -> "
          f"{auctions['issue_date'].max().date()});  months with zero proxy: {int((proxy == 0).sum())}")

    rows = []
    for m in months:
        L = last_bday(m)
        a, b = et(L - 3 * BDAY, 16), et(L, 15)
        row = {"month": str(m), "L": L.date(), "proxy_bn_years": proxy[m], "trailing_median": trailing[m],
               "window_start": a, "window_end": b}
        for c in ["UB", "ZB", "ZT"]:
            w = paths[c].window(a, b)
            row[f"{c}_bp"] = w["ret"] * 1e4
            if c == "UB":
                row.update({"UB_n_bars": w["n"], "UB_first_bar": w.get("first"), "UB_last_bar": w.get("last"),
                            "UB_exact": w.get("exact"), "UB_px_start": w.get("px_start")})
        row["flat_bp"] = row["UB_bp"] - FLAT_RATIO * row["ZT_bp"]
        row["UB_giveback_bp"] = paths["UB"].window(et(L, 15), et(L + BDAY, 16))["ret"] * 1e4
        row["UB_placebo_L10_bp"] = paths["UB"].window(et(L - 13 * BDAY, 16), et(L - 10 * BDAY, 15))["ret"] * 1e4
        inc = auctions[auctions["month"] == m]
        row["n_auctions"] = len(inc)
        row["latest_announcement"] = inc["announced"].max()
        rows.append(row)
    df = pd.DataFrame(rows)
    df["test"] = df["trailing_median"].notna()
    df["big"] = df["proxy_bn_years"] > df["trailing_median"]
    df["rel_log"] = np.log(df["proxy_bn_years"] / df["trailing_median"])
    t = df[df["test"]].copy()
    print(f"Test months: {t['month'].iloc[0]} -> {t['month'].iloc[-1]} = {len(t)};  big {int(t['big'].sum())}, "
          f"small {int((~t['big']).sum())};  UB window missing: {int(t['UB_bp'].isna().sum())}")

    # ---- sanity & look-ahead
    f = lambda x: x.tz_convert(ET).strftime("%a %Y-%m-%d %H:%M")  # noqa: E731
    print("\n=== Sanity: example months, UB window bar END times (ET) ===")
    for _, r in pd.concat([t.head(3), t.tail(2)]).iterrows():
        print(f"{r['month']} L={r['L']}  window ({f(r['window_start'])}, {f(r['window_end'])}]  bars {r['UB_n_bars']}:"
              f" first ends {f(r['UB_first_bar'])}, last ends {f(r['UB_last_bar'])}  UB {r['UB_bp']:+.1f} bp;  proxy"
              f" {r['proxy_bn_years']:,.0f} vs trailing-24m median {r['trailing_median']:,.0f} -> "
              f"{'BIG' if r['big'] else 'small'}")
    print(f"UB windows whose endpoints lack an exact bar: {int((~t['UB_exact'].astype(bool)).sum())} of {len(t)}: "
          f"{', '.join(t.loc[~t['UB_exact'].astype(bool), 'month'])}")
    late = t[t["latest_announcement"].dt.tz_convert("UTC") > t["window_start"]]
    print(f"Look-ahead: trailing median uses months m-24..m-1 only (shift(1)).  Months where an auction in the proxy"
          f" was announced after the window start: {len(late)}")
    for _, r in late.iterrows():
        print(f"   {r['month']}: latest announcement {r['latest_announcement']}, window starts {f(r['window_start'])}")
    gap = (t["window_start"] - t["latest_announcement"].dt.tz_convert("UTC")).dt.total_seconds() / 86400
    print(f"   min gap between last announcement and window start: {gap.min():.1f} days")
    print("\nProxy by year (mean $bn x years per month) and share of big months:")
    t["year"] = t["month"].str[:4]
    print(t.groupby("year").agg(proxy=("proxy_bn_years", "mean"), big_share=("big", "mean"),
                                n=("big", "size")).round(2).T.to_string())

    big, small = t[t["big"]], t[~t["big"]]

    # ---- primary
    print("\n=== PRIMARY: UB (16:00 L-3, 15:00 L], big minus small months, prediction > 0 ===")
    prim = welch(big["UB_bp"], small["UB_bp"])
    print(fmt(prim, "UB month-end window"))
    print(f"   all test months: mean {t['UB_bp'].mean():+.2f} bp, t {t['UB_bp'].mean() / t['UB_bp'].sem():+.2f}"
          f"  (the unconditional month-end effect)")

    # ---- placebo
    print("\n=== PLACEBO (same clock window, non-month-end days) ===")
    print(fmt(welch(big["UB_placebo_L10_bp"], small["UB_placebo_L10_bp"]), "P1: UB (16:00 L-13, 15:00 L-10]"))
    grid = pd.date_range("2012-08-01", "2026-09-30", freq=BDAY)
    Ls = [last_bday(m) for m in pd.period_range("2012-07", "2026-10", freq="M")]
    excl = set()
    for L in Ls:
        excl.update(L + k * BDAY for k in range(-2, 3))
    p2 = {}
    for d in grid:
        if d in excl:
            continue
        p2[d] = paths["UB"].window(et(d - 3 * BDAY, 16), et(d, 15))["ret"] * 1e4
    p2 = pd.Series(p2).dropna()
    m2, se2 = nw_mean(p2, grid, 3)
    me, se_me = t["UB_bp"].mean(), t["UB_bp"].sem()
    print(f"P2: UB (16:00 d-3, 15:00 d] on {len(p2)} non-month-end days: mean {m2:+.2f} bp (NW3 se {se2:.2f});"
          f"  month-end mean {me:+.2f} bp;  difference {me - m2:+.2f} bp, t {(me - m2) / np.hypot(se_me, se2):+.2f}")

    # ---- trade
    print("\n=== TRADE: long 1 UB over the window in big months only ===")
    cost_usd, cost_bp1 = per_side_cost("UB")
    big = big.copy()
    big["gross_bp"] = big["UB_bp"]
    big["net_bp"] = big["UB_bp"] - 2 * cost_bp1
    big["gross_usd"] = big["UB_bp"] / 1e4 * big["UB_px_start"] * 1000
    big["net_usd"] = big["gross_usd"] - 2 * cost_usd
    years = (LAST_MONTH.end_time - pd.Period(t["month"].iloc[0], "M").start_time).days / 365.25
    per_year = len(big) / years
    print(f"cost per trade: ${2 * cost_usd:.2f} = {2 * cost_bp1:.2f} bp at the spec price;  trades per year "
          f"{per_year:.2f} over {years:.2f} years")
    for lab, col in [("gross bp", "gross_bp"), ("net bp", "net_bp"), ("gross $", "gross_usd"), ("net $", "net_usd")]:
        x = big[col]
        print(f"   {lab:<9s} mean {x.mean():+8.2f}  median {x.median():+8.2f}  sd {x.std():8.2f}  "
              f"t {x.mean() / x.sem():+5.2f}  hit {(x > 0).mean():.0%}")
    print(f"   annualised net: {big['net_bp'].mean() * per_year:+.1f} bp of UB notional, "
          f"${big['net_usd'].mean() * per_year:+,.0f} per contract;  Sharpe (net) "
          f"{big['net_bp'].mean() / big['net_bp'].std() * np.sqrt(per_year):+.2f}")
    small_net = small["UB_bp"] - 2 * cost_bp1
    print(f"   for comparison, the same trade in small months: net mean {small_net.mean():+.2f} bp; in all months: "
          f"{(t['UB_bp'] - 2 * cost_bp1).mean():+.2f} bp")

    # ---- robustness
    print("\n=== ROBUSTNESS (reported only; cannot rescue the primary) ===")
    print(fmt(welch(big["ZB_bp"], small["ZB_bp"]), "ZB, same window"))
    print(fmt(welch(big["flat_bp"], small["flat_bp"]), f"flattener UB - {FLAT_RATIO:.3f} x ZT"))
    flat_cost = 2 * cost_bp1 + FLAT_RATIO * 2 * per_side_cost("ZT")[1]
    fn = big["flat_bp"] - flat_cost
    print(f"   flattener in big months: gross {big['flat_bp'].mean():+.2f} bp, cost {flat_cost:.2f} bp, net "
          f"{fn.mean():+.2f} bp (t {fn.mean() / fn.sem():+.2f})  [bp of UB notional]")
    print(fmt(welch(big["UB_giveback_bp"], small["UB_giveback_bp"]), "give-back UB (15:00 L, 16:00 L+1]"))
    gb = big["UB_giveback_bp"].dropna()
    print(f"   give-back in big months: mean {gb.mean():+.2f} bp (t {gb.mean() / gb.sem():+.2f}, n={len(gb)}); "
          f"all months {t['UB_giveback_bp'].mean():+.2f} bp")
    s1, t1 = ols_hc1(t["UB_bp"].to_numpy(), t["rel_log"].to_numpy())
    print(f"continuous (i): UB_bp on log(proxy / trailing median): slope {s1:+.2f} bp per unit log, t(HC1)={t1:+.2f}"
          f"  (proxy/median ranges {np.exp(t['rel_log'].min()):.2f}-{np.exp(t['rel_log'].max()):.2f})")
    s2, t2 = ols_hc1(t["UB_bp"].to_numpy(), t["proxy_bn_years"].to_numpy() / 1000)
    print(f"continuous (ii): UB_bp on raw proxy ($tn x years): slope {s2:+.2f} bp per $tn-yr, t(HC1)={t2:+.2f}")

    print("\n=== Context: big minus small by sub-period ===")
    for lo, hi in [("2012-08", "2016-12"), ("2017-01", "2020-12"), ("2021-01", "2026-09")]:
        s = t[(t["month"] >= lo) & (t["month"] <= hi)]
        w = welch(s.loc[s["big"], "UB_bp"], s.loc[~s["big"], "UB_bp"])
        print(fmt(w, f"   {lo} -> {hi}"))

    # ---- save
    out = df.copy()
    for col in ["window_start", "window_end"]:
        out[col] = out[col].dt.tz_convert(ET).dt.strftime("%Y-%m-%d %H:%M")
    out["latest_announcement"] = out["latest_announcement"].dt.strftime("%Y-%m-%d %H:%M")
    cols = ["month", "L", "test", "proxy_bn_years", "trailing_median", "big", "n_auctions", "latest_announcement",
            "window_start", "window_end", "UB_n_bars", "UB_bp", "ZB_bp", "ZT_bp", "flat_bp", "UB_giveback_bp",
            "UB_placebo_L10_bp"]
    out[cols].round(3).to_csv(HERE / "months.csv", index=False)


if __name__ == "__main__":
    buf = io.StringIO()
    with redirect_stdout(buf):
        main()
    text = buf.getvalue()
    print(text)
    (HERE / "run_output.txt").write_text(text)
