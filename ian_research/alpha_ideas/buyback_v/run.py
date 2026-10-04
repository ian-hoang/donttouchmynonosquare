"""Idea 1 — Treasury buyback "reverse V" (pre-registered in alpha_ideas/PREREGISTRATION.md).

Run from the repo root:  uv run python alpha_ideas/buyback_v/run.py

Since May 2024 the Treasury buys back old coupon bonds on a published schedule (a forced buyer). Prediction: the
matching future richens into the operation (pre-window return > 0) and gives it back afterwards (post < 0).
Primary test: long-end operations only (10Y-20Y -> ZB, 20Y-30Y -> UB), statistic = mean(pre - post) per event minus
the same statistic on placebo days, one-sided > 0. Spec choices are written in results.md before the first run.

Outputs (in this folder): events.csv (one row per event), placebo.csv (one row per placebo contract-day),
run_output.txt (everything printed below).
"""
from __future__ import annotations

import io
import json
import subprocess
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

from gqh import CACHE  # noqa: E402
from gqh import data as gd  # noqa: E402
from strategies.treasury_auction import SPECS, TERM_TO_CONTRACT  # noqa: E402  (read-only import)

ET = "America/New_York"
BDAY = CustomBusinessDay(calendar=USFederalHolidayCalendar())
CONTRACTS = ["ZT", "ZF", "ZN", "ZB", "UB"]
URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/buybacks_operations"
       "?page[size]=10000&sort=operation_date")
RAW = HERE / "buybacks_operations_raw.json"
BUCKET_TO_CONTRACT = {"20Y to 30Y": "UB", "10Y to 20Y": "ZB", "7Y to 10Y": "ZN", "5Y to 7Y": "ZN",
                      "3Y to 5Y": "ZF", "2Y to 3Y": "ZT", "1Mo to 2Y": "ZT"}
LONG_END = ["10Y to 20Y", "20Y to 30Y"]
START = pd.Timestamp("2024-05-01")
PERIOD_END = pd.Timestamp("2026-09-30")  # last calendar day covered by the futures cache (ends 2026-10-01 00:00 UTC)
MODAL_O, MODAL_C = "01:40 PM", "02:00 PM"
NW_LAGS = 2


def per_side_cost(contract: str) -> tuple[float, float]:
    """(dollars, bp of notional at the spec price) per contract per side: 0.5 tick spread + 0.5 tick slip + $1.50."""
    price, tick, mult = SPECS[contract]
    dollars = (0.5 + 0.5) * tick * mult + 1.5
    return dollars, gd.futures_cost_bps(price, tick, mult, fee_per_contract=1.5)


# ----------------------------------------------------------------------------------------------- data loading
def load_buybacks() -> pd.DataFrame:
    if not RAW.exists():  # cached raw download inside this folder (urllib fails on this machine: use curl)
        subprocess.run(["curl", "-sg", "-o", str(RAW), URL], check=True)
    df = pd.DataFrame(json.loads(RAW.read_text())["data"]).replace("null", np.nan)
    df["operation_date"] = pd.to_datetime(df["operation_date"])
    ev = df[(df["security_type"] == "Nominal Coupons") & (df["operation_type"] == "Liquidity Support")
            & (df["operation_date"] >= START)].copy()
    ev["contract"] = ev["maturity_bucket"].map(BUCKET_TO_CONTRACT)
    assert ev["contract"].notna().all(), ev.loc[ev["contract"].isna(), "maturity_bucket"].unique()
    ev["par_accepted_bn"] = pd.to_numeric(ev["total_par_amt_accepted"], errors="coerce") / 1e9
    ev["O"] = ev["operation_start_time_est"]
    ev["C"] = ev["operation_close_time_est"]
    return ev[["operation_date", "maturity_bucket", "contract", "O", "C", "par_accepted_bn"]].reset_index(drop=True)


def load_auctions() -> pd.DataFrame:
    """Nominal coupon auctions (no TIPS, no FRNs) mapped to futures, from the cached Fiscal Data JSON."""
    df = pd.DataFrame(json.loads((CACHE / "treasury_auctions.json").read_text())["data"])
    df = df[(df["inflation_index_security"] == "No") & (df["floating_rate"] == "No")]
    df = df[df["original_security_term"].isin(TERM_TO_CONTRACT)]
    return pd.DataFrame({"date": pd.to_datetime(df["auction_date"]),
                         "contract": df["original_security_term"].map(TERM_TO_CONTRACT)})


def load_futures():
    bars = gd.databento_chunked("GLBX.MDP3", [f"{c}.v.{k}" for c in CONTRACTS for k in (0, 1)], "ohlcv-1h",
                                "2010-07-01", "2026-10-01", stype_in="continuous")
    bars = gd.stamp_bar_end(bars, "1h")
    r = gd.roll_safe_returns(bars)
    out = {}
    for c in CONTRACTS:
        s = r[f"{c}.v.0"].dropna()
        close = bars.loc[bars["symbol"] == f"{c}.v.0", "close"].sort_index()
        out[c] = Path_(s, close)
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
        n = kb - ka
        if n <= 0:
            return {"ret": np.nan, "n": 0}
        kc = np.searchsorted(self.close_t, ia, side="right") - 1
        return {"ret": float(np.expm1(self.cum[kb] - self.cum[ka])), "n": int(n),
                "first": pd.Timestamp(self.t[ka], tz="UTC"), "last": pd.Timestamp(self.t[kb - 1], tz="UTC"),
                "a_exact": bool(ka > 0 and self.t[ka - 1] == ia), "b_exact": bool(self.t[kb - 1] == ib),
                "px_start": float(self.close[kc])}


# ----------------------------------------------------------------------------------------------- windows
def et(day: pd.Timestamp, hour: int, minute: int = 0) -> pd.Timestamp:
    return (pd.Timestamp(day) + pd.Timedelta(hours=hour, minutes=minute)).tz_localize(ET).tz_convert("UTC")


def clock(o: str, c: str) -> tuple[int, int]:
    """(pre end hour, post start hour): last full hour <= O, first full hour >= C + 1h."""
    O = pd.Timestamp(f"2000-01-01 {o}")
    C = pd.Timestamp(f"2000-01-01 {c}") + pd.Timedelta(hours=1)
    pre_end = O.floor("h").hour
    post_start = C.ceil("h").hour
    return pre_end, post_start


def measure(path: Path_, day: pd.Timestamp, o: str, c: str) -> dict:
    pre_end, post_start = clock(o, c)
    pre_a, pre_b = et(day - BDAY, 16), et(day, pre_end)
    post_a, post_b = et(day, post_start), et(day + BDAY, 16)
    pre, post = path.window(pre_a, pre_b), path.window(post_a, post_b)
    row = {"pre_a": pre_a, "pre_b": pre_b, "post_a": post_a, "post_b": post_b,
           "pre_bp": pre["ret"] * 1e4, "post_bp": post["ret"] * 1e4,
           "n_pre_bars": pre["n"], "n_post_bars": post["n"]}
    if pre["n"] and post["n"]:
        row.update({"pre_first_bar": pre["first"], "pre_last_bar": pre["last"],
                    "post_first_bar": post["first"], "post_last_bar": post["last"],
                    "endpoints_exact": pre["a_exact"] and pre["b_exact"] and post["a_exact"] and post["b_exact"],
                    "px_pre_start": pre["px_start"], "px_post_start": post["px_start"],
                    "pre_ret": pre["ret"], "post_ret": post["ret"]})
    row["y_bp"] = row["pre_bp"] - row["post_bp"]
    return row


# ----------------------------------------------------------------------------------------------- statistics
def event_vs_placebo(ev: pd.DataFrame, pl: pd.DataFrame, col: str, lags: int = NW_LAGS) -> dict:
    """mean over events of (y_i - placebo mean of contract(i)), with a Driscoll-Kraay / Newey-West SE.

    Each event and placebo observation's influence on the statistic is summed by date; Bartlett NW over dates.
    """
    ev = ev.dropna(subset=[col])
    pl = pl[pl["contract"].isin(ev["contract"].unique())].dropna(subset=[col])
    N = len(ev)
    pmean = pl.groupby("contract")[col].mean()
    pcount = pl.groupby("contract")[col].count()
    abn = ev[col] - ev["contract"].map(pmean)
    stat = abn.mean()
    n_c = ev["contract"].value_counts()
    psi_ev = (abn - stat) / N
    psi_pl = -(pl["contract"].map(n_c) / N) * (pl[col] - pl["contract"].map(pmean)) / pl["contract"].map(pcount)
    psi = pd.concat([pd.Series(psi_ev.to_numpy(), index=ev["date"].to_numpy()),
                     pd.Series(psi_pl.to_numpy(), index=pl["date"].to_numpy())]).groupby(level=0).sum()
    days = pd.date_range(min(psi.index), max(psi.index), freq=BDAY)
    x = psi.reindex(days, fill_value=0.0).to_numpy()
    var = float(x @ x)
    for lag in range(1, lags + 1):
        var += 2 * (1 - lag / (lags + 1)) * float(x[lag:] @ x[:-lag])
    se = np.sqrt(var)
    naive_se = abn.std(ddof=1) / np.sqrt(N)
    return {"N": N, "n_placebo": len(pl), "event_mean": ev[col].mean(), "placebo_mean": pl[col].mean(),
            "stat": stat, "se": se, "t": stat / se, "t_naive": stat / naive_se,
            "placebo_by_contract": pmean.round(2).to_dict()}


def fmt(res: dict, label: str) -> str:
    return (f"{label:<52s} N={res['N']:>3d}  events {res['event_mean']:+7.2f} bp  placebo {res['placebo_mean']:+6.2f} bp"
            f" (n={res['n_placebo']})  diff {res['stat']:+7.2f} bp  t(DK-NW{NW_LAGS})={res['t']:+5.2f}"
            f"  t(naive)={res['t_naive']:+5.2f}")


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


# ----------------------------------------------------------------------------------------------- main
def main():
    events = load_buybacks()
    auctions = load_auctions()
    paths = load_futures()
    last_bar = pd.Timestamp(max(p.last for p in paths.values()), tz="UTC")
    print(f"Futures cache: last bar ends {last_bar.tz_convert(ET)} ET")
    print(f"Buyback events (Nominal Coupons, Liquidity Support, >= {START.date()}): {len(events)}")
    print(events["maturity_bucket"].value_counts().to_string(), "\n")
    assert all(BDAY.is_on_offset(d) for d in events["operation_date"]), "event on a non-business day"

    # ---- events
    rows = []
    for _, e in events.iterrows():
        m = measure(paths[e["contract"]], e["operation_date"], e["O"], e["C"])
        near = auctions[(auctions["contract"] == e["contract"])
                        & auctions["date"].between(e["operation_date"] - BDAY, e["operation_date"] + BDAY)]
        rows.append({"date": e["operation_date"], "bucket": e["maturity_bucket"], "contract": e["contract"],
                     "O": e["O"], "C": e["C"], "par_accepted_bn": e["par_accepted_bn"],
                     "near_same_contract_auction": len(near) > 0,
                     "near_auction_dates": ";".join(near["date"].dt.strftime("%Y-%m-%d")), **m})
    ev = pd.DataFrame(rows)
    ev["long_end"] = ev["bucket"].isin(LONG_END)
    dropped = ev[ev["y_bp"].isna()]
    print(f"Events without data (window past the cache end or no bars): {len(dropped)}")
    for _, d in dropped.iterrows():
        print(f"   dropped {d['date'].date()} {d['bucket']} -> {d['contract']}")
    ev = ev.dropna(subset=["y_bp"]).reset_index(drop=True)

    # ---- placebo: all other business days for that contract, same (modal) clock windows
    rows = []
    days = pd.date_range(START, PERIOD_END, freq=BDAY)
    for c in CONTRACTS:
        ev_days = set(ev.loc[ev["contract"] == c, "date"]) | set(dropped.loc[dropped["contract"] == c, "date"])
        for d in days:
            if d in ev_days:
                continue
            rows.append({"date": d, "contract": c, **measure(paths[c], d, MODAL_O, MODAL_C)})
    pl = pd.DataFrame(rows).dropna(subset=["y_bp"]).reset_index(drop=True)
    print(f"Placebo contract-days (buyback era, {START.date()} -> {pl['date'].max().date()}): {len(pl)}\n")

    # ---- sanity: example events with window bar timestamps
    print("=== Sanity: example long-end events, window bar END times (ET) ===")
    for _, e in ev[ev["long_end"]].head(4).iterrows():
        f = lambda t: t.tz_convert(ET).strftime("%a %Y-%m-%d %H:%M")  # noqa: E731
        print(f"{e['date'].date()} {e['bucket']} -> {e['contract']}  O={e['O']} C={e['C']}")
        print(f"   pre  window ({f(e['pre_a'])}, {f(e['pre_b'])}]  bars {e['n_pre_bars']:>2d}: first ends "
              f"{f(e['pre_first_bar'])}, last ends {f(e['pre_last_bar'])}  -> {e['pre_bp']:+.1f} bp")
        print(f"   post window ({f(e['post_a'])}, {f(e['post_b'])}]  bars {e['n_post_bars']:>2d}: first ends "
              f"{f(e['post_first_bar'])}, last ends {f(e['post_last_bar'])}  -> {e['post_bp']:+.1f} bp")
    odd = ev[ev["O"].ne(MODAL_O) | ev["C"].ne(MODAL_C)]
    for _, e in odd.iterrows():
        f = lambda t: t.tz_convert(ET).strftime("%a %Y-%m-%d %H:%M")  # noqa: E731
        print(f"non-modal clock {e['date'].date()} {e['bucket']} O={e['O']} C={e['C']}: pre ({f(e['pre_a'])}, "
              f"{f(e['pre_b'])}], post ({f(e['post_a'])}, {f(e['post_b'])}]")
    print(f"Events whose window endpoints lack an exact bar: {int((~ev['endpoints_exact'].astype(bool)).sum())}"
          f" of {len(ev)};  placebo: {int((~pl['endpoints_exact'].astype(bool)).sum())} of {len(pl)}")
    print("Look-ahead: event dates/times come from the published operation schedule (announced ahead); the pre"
          " window ends at the last full hour before the operation opens, the post window starts >= 1h after close.\n")

    le = ev[ev["long_end"]].copy()
    le_pl = pl[pl["contract"].isin(["ZB", "UB"])]

    # ---- primary
    print("=== PRIMARY: long-end events (ZB, UB), (pre - post) minus placebo, prediction > 0 ===")
    prim = event_vs_placebo(le, le_pl, "y_bp")
    print(fmt(prim, "long-end pre-post vs placebo"))
    print(f"   placebo mean by contract: {prim['placebo_by_contract']}")
    for c in ["ZB", "UB"]:
        r = event_vs_placebo(le[le["contract"] == c], le_pl, "y_bp")
        print(fmt(r, f"   {c} only"))
    pmean = le_pl.groupby("contract")["y_bp"].mean()
    le["abnormal_bp"] = le["y_bp"] - le["contract"].map(pmean)
    print(f"   share of events with abnormal > 0: {(le['abnormal_bp'] > 0).mean():.0%};  median abnormal "
          f"{le['abnormal_bp'].median():+.2f} bp")
    print()

    # ---- trade
    print("=== TRADE: long pre window, short post window, 1 contract, every long-end event ===")
    cost_d = le["contract"].map(lambda c: 4 * per_side_cost(c)[0])
    cost_bp = le["contract"].map(lambda c: 4 * per_side_cost(c)[1])
    le["gross_usd"] = (le["pre_ret"] * le["px_pre_start"] - le["post_ret"] * le["px_post_start"]) * 1000
    le["net_usd"] = le["gross_usd"] - cost_d
    le["gross_bp"] = le["y_bp"]
    le["net_bp"] = le["y_bp"] - cost_bp
    years = (PERIOD_END - START).days / 365.25
    per_year = len(le) / years
    print(f"cost per event: ${cost_d.iloc[0]:.2f} (4 sides), {cost_bp[le['contract'] == 'ZB'].iloc[0]:.2f} bp ZB /"
          f" {cost_bp[le['contract'] == 'UB'].iloc[0]:.2f} bp UB")
    for lab, col in [("gross bp", "gross_bp"), ("net bp", "net_bp"), ("gross $", "gross_usd"), ("net $", "net_usd")]:
        x = le[col]
        print(f"   {lab:<9s} mean {x.mean():+9.2f}  median {x.median():+9.2f}  sd {x.std():8.2f}  t {tstat(x):+5.2f}"
              f"  hit {(x > 0).mean():.0%}")
    print(f"   events per year {per_year:.1f};  annualised net ${le['net_usd'].mean() * per_year:+,.0f} per contract;"
          f"  annualised Sharpe (net) {le['net_usd'].mean() / le['net_usd'].std() * np.sqrt(per_year):+.2f}")
    print(f"   total net over {len(le)} events: ${le['net_usd'].sum():+,.0f};  the same trade on every placebo day "
          f"would average {le_pl['y_bp'].mean():+.2f} bp gross")
    print()

    # ---- robustness
    print("=== ROBUSTNESS (reported only; cannot rescue the primary) ===")
    print(fmt(event_vs_placebo(ev, pl, "y_bp"), "all buckets, pre-post vs placebo"))
    for c in CONTRACTS:
        sub = ev[ev["contract"] == c]
        if len(sub) > 1:
            print(fmt(event_vs_placebo(sub, pl, "y_bp"), f"   {c} events ({', '.join(sorted(sub['bucket'].unique()))})"))
    print(fmt(event_vs_placebo(le, le_pl, "pre_bp"), "long-end PRE leg vs placebo (pred > 0)"))
    print(fmt(event_vs_placebo(le, le_pl, "post_bp"), "long-end POST leg vs placebo (pred < 0)"))
    print(fmt(event_vs_placebo(ev, pl, "pre_bp"), "all-bucket PRE leg vs placebo (pred > 0)"))
    print(fmt(event_vs_placebo(ev, pl, "post_bp"), "all-bucket POST leg vs placebo (pred < 0)"))
    far = le[~le["near_same_contract_auction"]]
    print(f"long-end events within 1 bday of a same-contract coupon auction: "
          f"{int(le['near_same_contract_auction'].sum())} -> dropped")
    print(fmt(event_vs_placebo(far, le_pl, "y_bp"), "long-end, no same-contract auction within 1 bday"))
    sc = le.dropna(subset=["par_accepted_bn"]).copy()
    sc["scaled_bp"] = sc["abnormal_bp"] * sc["par_accepted_bn"] / sc["par_accepted_bn"].mean()
    print(f"{'long-end abnormal scaled by accepted par / mean par':<52s} N={len(sc):>3d}  mean "
          f"{sc['scaled_bp'].mean():+7.2f} bp  t(naive)={tstat(sc['scaled_bp']):+5.2f}  (par range "
          f"{sc['par_accepted_bn'].min():.2f}-{sc['par_accepted_bn'].max():.2f} $bn, mean {sc['par_accepted_bn'].mean():.2f})")
    print("   (also as a regression: abnormal_bp on par_accepted_bn)")
    X = np.column_stack([np.ones(len(sc)), sc["par_accepted_bn"]])
    beta, *_ = np.linalg.lstsq(X, sc["abnormal_bp"].to_numpy(), rcond=None)
    resid = sc["abnormal_bp"].to_numpy() - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    hc1 = XtX_inv @ (X.T * resid**2) @ X @ XtX_inv * len(sc) / (len(sc) - 2)
    print(f"   slope {beta[1]:+.2f} bp per $bn accepted, t(HC1)={beta[1] / np.sqrt(hc1[1, 1]):+.2f}")
    print()

    # ---- side note, not pre-registered: full-history placebo
    rows = []
    hist_days = pd.date_range("2010-07-02", START - pd.Timedelta(days=1), freq=BDAY)
    for c in ["ZB", "UB"]:
        for d in hist_days:
            rows.append({"date": d, "contract": c, **measure(paths[c], d, MODAL_O, MODAL_C)})
    hist = pd.DataFrame(rows).dropna(subset=["y_bp"])
    print("=== SIDE NOTE (not pre-registered, cannot change the verdict): 2010-07 -> 2024-04 placebo ===")
    print(fmt(event_vs_placebo(le, hist, "y_bp"), "long-end pre-post vs pre-buyback-era placebo"))
    print()

    # ---- year split, for context
    print("=== Context: long-end abnormal by year ===")
    print(le.groupby(le["date"].dt.year)["abnormal_bp"].agg(["count", "mean", "std"]).round(2).to_string())

    # ---- save
    keep = ["date", "bucket", "contract", "O", "C", "par_accepted_bn", "near_same_contract_auction",
            "near_auction_dates", "pre_a", "pre_b", "post_a", "post_b", "n_pre_bars", "n_post_bars",
            "pre_bp", "post_bp", "y_bp", "long_end"]
    out = ev[keep].merge(le[["date", "contract", "abnormal_bp", "gross_usd", "net_usd", "net_bp"]],
                         on=["date", "contract"], how="left")
    for col in ["pre_a", "pre_b", "post_a", "post_b"]:
        out[col] = out[col].dt.tz_convert(ET).dt.strftime("%Y-%m-%d %H:%M")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.round(3).to_csv(HERE / "events.csv", index=False)
    pl_out = pl[["date", "contract", "pre_bp", "post_bp", "y_bp"]].copy()
    pl_out["date"] = pl_out["date"].dt.strftime("%Y-%m-%d")
    pl_out.round(3).to_csv(HERE / "placebo.csv", index=False)


if __name__ == "__main__":
    buf = io.StringIO()
    with redirect_stdout(buf):
        main()
    text = buf.getvalue()
    print(text)
    (HERE / "run_output.txt").write_text(text)
