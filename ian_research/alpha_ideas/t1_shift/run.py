"""Idea 3 — T+1 shift hunt + replication of Harvey, Mazzoleni & Melone (2025) "front-running rebalancers".

Pre-registered in alpha_ideas/PREREGISTRATION.md (Idea 3). Spec choices are written in results.md before the first run.

Run from the repo root:  uv run python alpha_ideas/t1_shift/run.py

3a. Replication of the paper's trading rule (NBER w33554, Section 4 + Appendix B) on ES / ZN futures with 16:00 ET
    closes: in-sample overlap 2010-07 -> 2023-03-17 and genuine out-of-sample 2023-03-20 -> 2026-09-30.
3b. Does month-end selling pressure in ES move one day later when U.S. equity settlement moved from T+2 to T+1
    (2024-05-28)? Difference-in-differences of 3-day window returns, month-level Welch t-stat.

Outputs (this folder): daily.csv, monthly_windows.csv, profiles.csv, strategy_stats.csv, delta_diagnostics.csv,
roll_checks.csv, replication_equity.png, run_output.txt (everything printed).
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import gqh.data as gd  # noqa: E402
from gqh import CACHE  # noqa: E402

TZ = "America/New_York"

# ---------------------------------------------------------------------------------------------------------------
# Data requests (fixed; the ES one is the approved ~$1.88 purchase, the rates one is already cached)
# ---------------------------------------------------------------------------------------------------------------
ES_REQ = dict(dataset="GLBX.MDP3", symbols=["ES.v.0", "ES.v.1"], schema="ohlcv-1h",
              start="2010-06-07", end="2026-10-01", stype_in="continuous")
RATES_REQ = dict(dataset="GLBX.MDP3", symbols=[f"{c}.v.{k}" for c in ["ZT", "ZF", "ZN", "ZB", "UB"] for k in (0, 1)],
                 schema="ohlcv-1h", start="2010-07-01", end="2026-10-01", stype_in="continuous")
MAX_ES_USD = 2.50

# Sample boundaries
IS_START, IS_END = pd.Timestamp("2010-07-01"), pd.Timestamp("2023-03-17")
OOS_START, OOS_END = pd.Timestamp("2023-03-20"), pd.Timestamp("2026-09-30")

# Settlement regimes (U.S. equities)
T2_START, T1_START = pd.Timestamp("2017-09-05"), pd.Timestamp("2024-05-28")

# Paper parameters (Appendix B / Section 4) — fixed by the pre-registration
TARGET = 0.60
DELTAS = np.round(np.arange(0, 26) * 0.001, 4)  # 0.0%, 0.1%, ..., 2.5%  (26 values)
THRESH_SCALE = 0.015                             # -Threshold / 1.5%
LAST_WEEK = 5                                    # last 5 business days of the month
FIRST_DAY_LAG = 4                                # sign(Calendar_{t-4}) on the first business day

# Costs: per side, per unit of notional traded, in bps (gqh.data.futures_cost_bps, $1.50 fee)
ES_TICK, ES_MULT = 0.25, 50.0
ZN_PRICE, ZN_TICK, ZN_MULT = 111.0, 1 / 64, 1000.0
FEE = 1.5


# ---------------------------------------------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------------------------------------------
def _chunks(start, end):
    """Same calendar-year split as gqh.data.databento_chunked."""
    edges = [pd.Timestamp(start)] + [pd.Timestamp(f"{y}-01-01") for y in
                                     range(pd.Timestamp(start).year + 1, pd.Timestamp(end).year + 1)]
    edges = [e for e in edges if e < pd.Timestamp(end)] + [pd.Timestamp(end)]
    return [(a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")) for a, b in zip(edges[:-1], edges[1:])]


def _fully_cached(req) -> bool:
    for a, b in _chunks(req["start"], req["end"]):
        r = dict(dataset=req["dataset"], symbols=list(req["symbols"]), schema=req["schema"],
                 start=a, end=b, stype_in=req["stype_in"])
        key = hashlib.sha1(json.dumps(r, sort_keys=True).encode()).hexdigest()[:12]
        if not (CACHE / f"{req['dataset']}_{req['schema']}_{key}.dbn.zst").exists():
            return False
    return True


def load_bars():
    if not _fully_cached(ES_REQ):  # only price-check when something would actually be bought
        p = gd.price(**ES_REQ)
        print(f"ES request price: ${p['usd']:.4f} ({p['gb']:.4f} GB)")
        if p["usd"] > MAX_ES_USD:
            raise SystemExit(f"ABORT: ES request costs ${p['usd']:.2f} > ${MAX_ES_USD:.2f}")
    if not _fully_cached(RATES_REQ):
        raise SystemExit("ABORT: the rates request is expected to be cached; refusing to buy it again")
    es = gd.databento_chunked(ES_REQ["dataset"], ES_REQ["symbols"], ES_REQ["schema"], ES_REQ["start"],
                              ES_REQ["end"], stype_in=ES_REQ["stype_in"])
    rates = gd.databento_chunked(RATES_REQ["dataset"], RATES_REQ["symbols"], RATES_REQ["schema"],
                                 RATES_REQ["start"], RATES_REQ["end"], stype_in=RATES_REQ["stype_in"])
    zn = rates[rates["symbol"].isin(["ZN.v.0", "ZN.v.1"])]
    return es, zn


# ---------------------------------------------------------------------------------------------------------------
# NYSE trading calendar (rule-based; validated against the ES/ZN bars in check_calendar)
# ---------------------------------------------------------------------------------------------------------------
NYSE_SPECIAL_CLOSURES = [date(2012, 10, 29), date(2012, 10, 30),  # Hurricane Sandy
                         date(2018, 12, 5),                       # President G.H.W. Bush funeral
                         date(2025, 1, 9)]                        # President Carter funeral


def _observed(d: date) -> date:
    return d - timedelta(1) if d.weekday() == 5 else d + timedelta(1) if d.weekday() == 6 else d


def _nth_weekday(y, m, wd, n) -> date:
    d = date(y, m, 1)
    return d + timedelta((wd - d.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(y, m, wd) -> date:
    d = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(1))
    return d - timedelta((d.weekday() - wd) % 7)


def nyse_holidays(y0: int, y1: int) -> set[date]:
    out = set(NYSE_SPECIAL_CLOSURES)
    for y in range(y0, y1 + 1):
        ny = date(y, 1, 1)
        if ny.weekday() == 6:
            out.add(ny + timedelta(1))
        elif ny.weekday() < 5:
            out.add(ny)  # Saturday New Year: NYSE does not close the Friday before
        out.add(_nth_weekday(y, 1, 0, 3))                       # MLK
        out.add(_nth_weekday(y, 2, 0, 3))                       # Presidents
        easter = (pd.Timestamp(f"{y}-01-01") + pd.offsets.Easter()).date()
        out.add(easter - timedelta(2))                          # Good Friday
        out.add(_last_weekday(y, 5, 0))                         # Memorial
        if y >= 2022:
            out.add(_observed(date(y, 6, 19)))                  # Juneteenth
        out.add(_observed(date(y, 7, 4)))                       # Independence
        out.add(_nth_weekday(y, 9, 0, 1))                       # Labor
        out.add(_nth_weekday(y, 11, 3, 4))                      # Thanksgiving
        out.add(_observed(date(y, 12, 25)))                     # Christmas
    return out


def nyse_days(start, end) -> pd.DatetimeIndex:
    hol = nyse_holidays(pd.Timestamp(start).year, pd.Timestamp(end).year)
    days = pd.bdate_range(start, end)
    return pd.DatetimeIndex([d for d in days if d.date() not in hol])


# ---------------------------------------------------------------------------------------------------------------
# Daily 16:00 ET closes and roll-safe returns
# ---------------------------------------------------------------------------------------------------------------
def last_bar_end(bars: pd.DataFrame, symbol: str) -> pd.Series:
    """ET hour at which the last bar inside the 09:30-16:00 window ENDS, per ET date (16 = a true 16:00 close)."""
    b = bars[bars["symbol"] == symbol]
    loc = b.index.tz_convert(TZ)
    df = pd.DataFrame({"day": loc.normalize().tz_localize(None), "h": loc.hour + loc.minute / 60})
    df = df[(df["h"] >= 9.5) & (df["h"] < 16)]
    return df.groupby("day")["h"].max() + 1


def daily_panel(bars: pd.DataFrame, root: str, days: pd.DatetimeIndex) -> pd.DataFrame:
    """session_daily (bars ending 10:00..16:00 ET) -> keep trading days -> roll-safe close-to-close returns."""
    d = gd.session_daily(bars, open_time="09:30", close_time="16:00")
    d = d[d.index.tz_convert(TZ).normalize().tz_localize(None).isin(days)]
    rets = gd.roll_safe_returns(d)
    front = d[d["symbol"] == f"{root}.v.0"]
    out = pd.DataFrame({"close": front["close"].to_numpy(), "instrument_id": front["instrument_id"].to_numpy()},
                       index=front.index.tz_convert(TZ).normalize().tz_localize(None))
    r = rets[f"{root}.v.0"]
    r.index = pd.DatetimeIndex(r.index).tz_convert(TZ).normalize().tz_localize(None)
    out["ret"] = r.reindex(out.index)
    out["naive_ret"] = out["close"].pct_change()
    out.loc[out.index[0], "ret"] = np.nan
    return out


def build_daily(es_bars, zn_bars):
    """Joint ES/ZN daily frame on the trading-day calendar, plus calendar flags."""
    nyse = nyse_days("2010-06-01", "2026-12-31")
    days_with = {}
    for bars, sym in [(es_bars, "ES.v.0"), (zn_bars, "ZN.v.0")]:
        days_with[sym] = set(last_bar_end(bars, sym).index)
    in_sample = nyse[(nyse >= IS_START) & (nyse <= OOS_END)]
    days = pd.DatetimeIndex([d for d in in_sample if d in days_with["ES.v.0"] and d in days_with["ZN.v.0"]])
    gaps = [d for d in in_sample if d not in days]
    es, zn = daily_panel(es_bars, "ES", days), daily_panel(zn_bars, "ZN", days)
    df = pd.DataFrame({"es_close": es["close"], "zn_close": zn["close"], "es_iid": es["instrument_id"],
                       "zn_iid": zn["instrument_id"], "r_es": es["ret"], "r_zn": zn["ret"]}, index=days)
    df["es_close_hour"] = last_bar_end(es_bars, "ES.v.0").reindex(days).to_numpy()
    df["zn_close_hour"] = last_bar_end(zn_bars, "ZN.v.0").reindex(days).to_numpy()
    # position in month on the trading-day calendar actually used
    ym = df.index.to_period("M")
    df["ym"] = ym.astype(str)
    df["k_from_end"] = df.groupby("ym").cumcount(ascending=False)       # 0 = L
    df["k_from_start"] = df.groupby("ym").cumcount()                    # 0 = F
    df["is_L"], df["is_F"] = df["k_from_end"] == 0, df["k_from_start"] == 0
    # return spans a missing NYSE day (vendor gap)?
    prev_nyse = pd.Series(nyse[:-1], index=nyse[1:])
    df["prev_day"] = pd.Series(df.index, index=df.index).shift(1)
    df["gap_ret"] = df["prev_day"].notna() & (df["prev_day"] != prev_nyse.reindex(df.index))
    # NYSE month-end vs the calendar's L
    nyse_L = pd.Series(nyse, index=nyse).groupby(nyse.to_period("M")).max()
    df["nyse_L_missing"] = df["ym"].map(lambda m: nyse_L.get(pd.Period(m), pd.NaT) not in days)
    return df, gaps


def roll_check_table(df):
    rows = []
    for root in ["es", "zn"]:
        iid = df[f"{root}_iid"]
        for d in df.index[(iid != iid.shift(1)) & iid.shift(1).notna()]:
            i = df.index.get_loc(d)
            rows.append(dict(market=root.upper(), date=d.date(), old_iid=int(iid.iloc[i - 1]), new_iid=int(iid.iloc[i]),
                             close=df[f"{root}_close"].iloc[i], prev_close_old=df[f"{root}_close"].iloc[i - 1],
                             naive_ret=df[f"{root}_close"].iloc[i] / df[f"{root}_close"].iloc[i - 1] - 1,
                             roll_safe_ret=df[f"r_{root}"].iloc[i]))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------------------
# Signals (Appendix B) and the strategy (Section 4)
# ---------------------------------------------------------------------------------------------------------------
def _drift(w, r_eq, r_bd):
    return w * (1 + r_eq) / (w * (1 + r_eq) + (1 - w) * (1 + r_bd))


def threshold_signal(r_es, r_zn, delta):
    """Eq. B.1. Returns (signal, rebalanced-today flag). Reset condition uses w_t (literal)."""
    n = len(r_es)
    sig, reb = np.zeros(n), np.zeros(n, dtype=bool)
    w = TARGET
    for i in range(1, n):
        drifted = _drift(w, r_es[i], r_zn[i])
        sig[i] = drifted - TARGET
        if abs(w - TARGET) >= delta:
            w, reb[i] = TARGET, True
        else:
            w = drifted
    return sig, reb


def calendar_signal(r_es, r_zn, is_L):
    """Eq. B.2: w_{t+1} = 60% if t is the last business day of the month, else drifted."""
    n = len(r_es)
    sig = np.zeros(n)
    w = TARGET
    for i in range(1, n):
        drifted = _drift(w, r_es[i], r_zn[i])
        sig[i] = drifted - TARGET
        w = TARGET if is_L[i - 1] else drifted
    return sig


def add_signals(df):
    r_es, r_zn = df["r_es"].fillna(0).to_numpy(), df["r_zn"].fillna(0).to_numpy()
    sigs, diag = [], []
    years = (df.index[-1] - df.index[0]).days / 365.25
    for d in DELTAS:
        s, reb = threshold_signal(r_es, r_zn, d)
        sigs.append(s)
        diag.append(dict(delta_pct=d * 100, rebalances_per_year=reb.sum() / years))
    df["threshold"] = np.mean(sigs, axis=0)
    df["calendar"] = calendar_signal(r_es, r_zn, df["is_L"].to_numpy())
    cal = df["calendar"].to_numpy()
    mod = np.zeros(len(df))
    last5 = (df["k_from_end"] < LAST_WEEK).to_numpy()
    first = df["is_F"].to_numpy()
    for i in range(len(df)):
        if last5[i]:
            mod[i] = np.sign(-cal[i])
        elif first[i] and i >= FIRST_DAY_LAG:
            mod[i] = np.sign(cal[i - FIRST_DAY_LAG])
    df["mod_calendar"] = mod
    df["w_threshold"] = -df["threshold"] / THRESH_SCALE
    df["w"] = 0.5 * df["w_threshold"] + 0.5 * df["mod_calendar"]
    return df, pd.DataFrame(diag)


def strategy_returns(df, wcol):
    spread = df["r_es"] - df["r_zn"]
    gross = df[wcol].shift(1) * spread
    c_es = df["es_close"].map(lambda p: gd.futures_cost_bps(p, ES_TICK, ES_MULT, fee_per_contract=FEE))
    c_zn = gd.futures_cost_bps(ZN_PRICE, ZN_TICK, ZN_MULT, fee_per_contract=FEE)
    turnover = (df[wcol] - df[wcol].shift(1).fillna(0)).abs()
    cost = turnover * (c_es + c_zn) / 1e4
    gross = gross.fillna(0)
    return gross, gross - cost, cost, turnover


def perf(r: pd.Series) -> dict:
    import statsmodels.api as sm
    r = r.dropna()
    n = len(r)
    eq = (1 + r).cumprod()
    mdd = (eq / eq.cummax() - 1).min()
    nw = sm.OLS(r.to_numpy(), np.ones(n)).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    return dict(n_days=n, ann_ret_pct=r.mean() * 252 * 100, ann_vol_pct=r.std() * np.sqrt(252) * 100,
                sharpe=r.mean() / r.std() * np.sqrt(252), skew=r.skew(), max_dd_pct=mdd * 100,
                t_mean=r.mean() / (r.std() / np.sqrt(n)), t_nw5=float(nw.tvalues[0]))


# ---------------------------------------------------------------------------------------------------------------
# 3b: month-level windows
# ---------------------------------------------------------------------------------------------------------------
def regime_of(L: pd.Timestamp) -> str:
    return "T+3" if L < T2_START else ("T+2" if L < T1_START else "T+1")


def welch(a, b):
    from scipy import stats
    a, b = pd.Series(a).dropna(), pd.Series(b).dropna()
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return dict(diff=a.mean() - b.mean(), t=t, p_two_sided=p, n_a=len(a), n_b=len(b))


def one_sample(x):
    x = pd.Series(x).dropna()
    return dict(mean=x.mean(), t=x.mean() / (x.std() / np.sqrt(len(x))) if len(x) > 1 else np.nan, n=len(x))


def month_windows(df, anchor: str = "L"):
    """Per month: window sums of ES returns and y around the anchor (L, or the mid-month placebo M)."""
    idx = df.index
    es_bp = df["r_es"] * 1e4
    y_bp = df["y"] * 1e4
    bad = df["gap_ret"].to_numpy()
    rows = []
    for ym, g in df.groupby("ym", sort=True):
        if anchor == "L":
            a = idx.get_loc(g.index[-1])
        else:  # placebo: last trading day on or before the 15th
            cand = g.index[g.index.day <= 15]
            if len(cand) == 0:
                continue
            a = idx.get_loc(cand[-1])
        if a - 5 < 1:
            continue
        L = idx[a]
        row = dict(month=ym, anchor=L.date(), regime=regime_of(g.index[-1]))

        def W(series, lo, hi):  # sum of returns dated anchor-lo .. anchor-hi
            pos = range(a - lo, a - hi + 1)
            if any(bad[p] for p in pos):
                return np.nan
            return float(sum(series.iloc[p] for p in pos))
        for name, s in [("es", es_bp), ("y", y_bp)]:
            row[f"{name}_W5_3"] = W(s, 5, 3)
            row[f"{name}_W4_2"] = W(s, 4, 2)
            row[f"{name}_W3_1"] = W(s, 3, 1)
        row["excluded_gap"] = bool(anchor == "L" and (g["nyse_L_missing"].iloc[0] or
                                                     any(bad[a - 5:a])))
        if row["excluded_gap"]:
            for k in list(row):
                if k.startswith(("es_", "y_")):
                    row[k] = np.nan
        rows.append(row)
    m = pd.DataFrame(rows)
    for name in ["es", "y"]:
        m[f"{name}_d_T1vsT2"] = m[f"{name}_W3_1"] - m[f"{name}_W4_2"]   # new (T+1) window minus old (T+2) window
        m[f"{name}_d_T2vsT3"] = m[f"{name}_W4_2"] - m[f"{name}_W5_3"]   # new (T+2) window minus old (T+3) window
    return m


def profiles(df, excluded_months=()):
    """Mean daily return (bp) by k = -10..+2 relative to L, per regime."""
    idx = df.index
    Ls = df.index[df["is_L"]]
    rows = []
    for L in Ls:
        a = idx.get_loc(L)
        reg = regime_of(L)
        excluded = bool(df.loc[L, "nyse_L_missing"]) or str(L.to_period("M")) in set(excluded_months)
        for k in range(-10, 3):
            p = a + k
            if p < 1 or p >= len(idx) or excluded or df["gap_ret"].iloc[p]:
                continue
            rows.append(dict(regime=reg, month=str(L.to_period("M")), k=k,
                             es_bp=df["r_es"].iloc[p] * 1e4, y_bp=df["y"].iloc[p] * 1e4))
    long = pd.DataFrame(rows)
    out = []
    for (reg, k), g in long.groupby(["regime", "k"]):
        e, y = one_sample(g["es_bp"]), one_sample(g["y_bp"])
        out.append(dict(regime=reg, k=k, n=e["n"], es_mean_bp=e["mean"], es_t=e["t"], y_mean_bp=y["mean"], y_t=y["t"]))
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------------------------------------------
def chart(daily, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    surface, ink, ink2, grid = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
    c_gross, c_net = "#2a78d6", "#eb6834"
    eq_g = (1 + daily["gross"]).cumprod()
    eq_n = (1 + daily["net"]).cumprod()
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=150, facecolor=surface)
    ax.set_facecolor(surface)
    ax.axvspan(OOS_START, daily.index[-1], color="#efeee9", zorder=0, lw=0)
    ax.axvline(OOS_START, color=ink2, lw=1, ls=(0, (3, 3)), zorder=1)
    ax.text(OOS_START + pd.Timedelta(days=40), 0.03, "out of sample\n2023-03-20 →", transform=ax.get_xaxis_transform(),
            va="bottom", ha="left", fontsize=9, color=ink2)
    ax.text(OOS_START - pd.Timedelta(days=40), 0.03, "overlap with the paper's sample", transform=ax.get_xaxis_transform(),
            va="bottom", ha="right", fontsize=9, color=ink2)
    mar20 = eq_g.loc["2020-03"]
    m20 = (1 + daily["gross"].loc["2020-03"]).prod() - 1
    ax.annotate(f"March 2020 alone: {m20:+.0%} (gross)", (mar20.index[-1], mar20.iloc[-1]), xytext=(-150, 18),
                textcoords="offset points", fontsize=9, color=ink2,
                arrowprops=dict(arrowstyle="-", color=ink2, lw=0.8))
    ax.plot(eq_g.index, eq_g, color=c_gross, lw=2, label="Gross", zorder=3)
    ax.plot(eq_n.index, eq_n, color=c_net, lw=2, label="Net of costs", zorder=3)
    for s, c, lab in [(eq_g, c_gross, "Gross"), (eq_n, c_net, "Net")]:
        ax.annotate(f"{lab} {s.iloc[-1]:.2f}×", (s.index[-1], s.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9, color=ink)
    ax.axhline(1, color=ink2, lw=0.8, zorder=1)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.2f}×"))
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="y", color=grid, lw=0.8)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(grid)
    ax.tick_params(colors=ink2, labelsize=9)
    ax.set_ylabel("Growth of $1", color=ink2, fontsize=10)
    ax.set_title("Front-running rebalancers (Harvey, Mazzoleni & Melone rule) on ES/ZN, 16:00 ET closes",
                 loc="left", fontsize=11.5, color=ink)
    ax.legend(loc="upper left", bbox_to_anchor=(0, 0.93), frameon=False, fontsize=9, labelcolor=ink)
    ax.set_xlim(daily.index[0], daily.index[-1] + pd.Timedelta(days=330))
    fig.tight_layout()
    fig.savefig(path, facecolor=surface)
    plt.close(fig)


# ---------------------------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------------------------
def fmt(d: dict, keys=None, nd=2):
    keys = keys or list(d)
    return "  ".join(f"{k}={d[k]:.{nd}f}" if isinstance(d[k], (float, np.floating)) else f"{k}={d[k]}" for k in keys)


def main():
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    es_bars, zn_bars = load_bars()
    df, gaps = build_daily(es_bars, zn_bars)
    print(f"Trading days: {len(df)} ({df.index[0].date()} -> {df.index[-1].date()}); "
          f"NYSE days dropped for vendor data gaps: {[str(d.date()) for d in gaps]}")
    early = df[(df["es_close_hour"] < 16) | (df["zn_close_hour"] < 16)][["es_close_hour", "zn_close_hour"]]
    print(f"Days whose close is before 16:00 ET (half-days / data holes): {len(early)}")
    print(early.to_string())
    print("Returns that span a vendor gap:", [str(d.date()) for d in df.index[df["gap_ret"]]])
    assert df["r_es"].iloc[1:].notna().all() and df["r_zn"].iloc[1:].notna().all(), "missing returns"

    rolls = roll_check_table(df)
    rolls.to_csv(HERE / "roll_checks.csv", index=False, float_format="%.6f")
    for mkt, g in rolls.groupby("market"):
        print(f"{mkt}: {len(g)} rolls; max |roll-safe ret| on roll days {g['roll_safe_ret'].abs().max():.4f}, "
              f"max |naive ret| {g['naive_ret'].abs().max():.4f}, mean (naive - roll-safe) "
              f"{(g['naive_ret'] - g['roll_safe_ret']).mean() * 1e4:.1f} bp")
    print(rolls.groupby("market").head(3).to_string(index=False))

    # ---------------- 3a ----------------
    df, diag = add_signals(df)
    diag.to_csv(HERE / "delta_diagnostics.csv", index=False, float_format="%.3f")
    print("\nThreshold rebalancing frequency by delta (per year):")
    print(diag.iloc[[0, 5, 10, 11, 15, 20, 25]].to_string(index=False))
    print(f"Median over the 26 deltas: {diag['rebalances_per_year'].median():.1f}/yr (paper: ~16/yr)")
    df["y"] = -np.sign(df["calendar"].shift(1)) * (df["r_es"] - df["r_zn"])

    sig = df.iloc[1:]
    for c in ["threshold", "calendar"]:
        s = sig[c] * 100
        print(f"{c:9s} signal (% weight): mean {s.mean():.3f}  sd {s.std():.3f}  AR1 {s.autocorr():.2f}  "
              f"skew {s.skew():.2f}  min {s.min():.2f}  max {s.max():.2f}")
    print(f"corr(threshold, calendar) = {sig['threshold'].corr(sig['calendar']):.2f}  (paper ~0.60)")
    print(f"Position w: mean {sig['w'].mean():.3f}, sd {sig['w'].std():.3f}, mean |w| {sig['w'].abs().mean():.3f}, "
          f"mean daily |dw| {sig['w'].diff().abs().mean():.3f}")

    strat = {}
    for name, wcol in [("combined", "w"), ("threshold_only", "w_threshold"), ("calendar_only", "mod_calendar")]:
        g, n, c, to = strategy_returns(df, wcol)
        strat[name] = dict(gross=g, net=n, cost=c, turnover=to)
    df["gross"], df["net"], df["cost"], df["turnover"] = (strat["combined"][k] for k in ["gross", "net", "cost", "turnover"])

    periods = {
        "(i) 2010-07-02 -> 2023-03-17": (pd.Timestamp("2010-07-02"), IS_END, None),
        "(i) excl. Mar 2020": (pd.Timestamp("2010-07-02"), IS_END, "2020-03"),
        "(ii) 2023-03-20 -> 2026-09-30 OOS": (OOS_START, OOS_END, None),
        "full 2010-07-02 -> 2026-09-30": (pd.Timestamp("2010-07-02"), OOS_END, None),
    }
    rows = []
    for pname, (a, b, drop) in periods.items():
        for sname, d in strat.items():
            for kind in ["gross", "net"]:
                r = d[kind][(d[kind].index >= a) & (d[kind].index <= b)]
                if drop:
                    r = r[r.index.to_period("M").astype(str) != drop]
                row = dict(period=pname, strategy=sname, kind=kind, **perf(r))
                to = d["turnover"][(d["turnover"].index >= a) & (d["turnover"].index <= b)]
                row["annual_turnover"] = to.mean() * 252
                row["cost_drag_pct_pa"] = d["cost"][(d["cost"].index >= a) & (d["cost"].index <= b)].mean() * 252 * 100
                rows.append(row)
    stats = pd.DataFrame(rows)
    stats.to_csv(HERE / "strategy_stats.csv", index=False, float_format="%.4f")
    print("\n=== 3a strategy statistics (daily returns; annualised with 252) ===")
    print(stats.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print("Paper (1997-09-10 -> 2023-03-17, gross): ann. ret 10.20%, vol 9.17%, Sharpe 1.11, skew 5.23; "
          "net Sharpe 'close to 1'; ex Sep08-Mar09 and Mar20: Sharpe 0.90")

    # paper's 'both signals have ~11.6% annual vol' check (component strategy vols over the paper overlap)
    for sname in ["threshold_only", "calendar_only"]:
        r = strat[sname]["gross"][(strat[sname]["gross"].index >= "2010-07-02") & (strat[sname]["gross"].index <= IS_END)]
        print(f"{sname} gross vol over (i): {r.std() * np.sqrt(252) * 100:.1f}% (paper: 11.6% for both)")

    # DIAGNOSTIC (not pre-registered): the paper's predictive regression without controls,
    # (R_ES - R_ZN)_{t+1} on Threshold_t, Calendar_t, Calendar_t x week4_t, week4_t; HC1 t-stats
    import statsmodels.api as sm
    nxt = (df["r_es"] - df["r_zn"]).shift(-1)
    wk4 = (df["k_from_end"] < LAST_WEEK).astype(float)
    X = pd.DataFrame({"const": 1.0, "threshold": df["threshold"], "calendar": df["calendar"],
                      "calendar_x_week4": df["calendar"] * wk4, "week4": wk4})
    for pname, (a, b) in {"(i)": ("2010-07-02", IS_END), "(ii)": (OOS_START, OOS_END)}.items():
        sel = (df.index >= a) & (df.index <= b) & nxt.notna()
        fit = sm.OLS(nxt[sel], X[sel]).fit(cov_type="HC1")
        print(f"DIAGNOSTIC regression {pname}: " + "  ".join(
            f"{k} {fit.params[k]:+.3f} (t {fit.tvalues[k]:+.2f})" for k in ["threshold", "calendar", "calendar_x_week4"]))
    yearly = df["gross"].groupby(df.index.year).sum() * 100
    print("Gross P&L by calendar year (sum of daily returns, %): " + ", ".join(f"{y}: {v:+.1f}" for y, v in yearly.items()))

    # 3a verdicts (rules fixed in results.md 4.1, item 12)
    s_is = stats[(stats.period.str.startswith("(i) 2010")) & (stats.strategy == "combined")].set_index("kind")
    s_oos = stats[(stats.period.str.startswith("(ii)")) & (stats.strategy == "combined")].set_index("kind")
    if s_is.loc["gross", "t_mean"] >= 2 and s_is.loc["gross", "sharpe"] >= 0.7:
        v_is = "MATCHES (Sharpe >= 0.7, t >= 2)"
    elif s_is.loc["gross", "t_mean"] >= 2:
        v_is = "WEAKER BUT PRESENT (t >= 2, Sharpe < 0.7)"
    else:
        v_is = "DOES NOT REPLICATE (t < 2)"
    holds = s_oos.loc["gross", "t_mean"] >= 2 and s_oos.loc["net", "ann_ret_pct"] > 0
    v_oos = ("HOLDS" + (" (convincing, t >= 3)" if s_oos.loc["gross", "t_mean"] >= 3 else " (t >= 2, net > 0)")
             if holds else "DOES NOT CLEAR THE BAR (needs gross t >= 2 and net mean > 0)")
    print(f"\n3a in-sample verdict: {v_is}\n3a out-of-sample verdict: {v_oos}")

    # ---------------- 3b ----------------
    m = month_windows(df, "L")
    m.to_csv(HERE / "monthly_windows.csv", index=False, float_format="%.3f")
    print(f"\n=== 3b months: {len(m)}; excluded for data gaps: {m.loc[m.excluded_gap, 'month'].tolist()} ===")
    print(m.groupby("regime").size().to_string())

    def did(frame, col, new, old):
        a, b = frame.loc[frame.regime == new, col], frame.loc[frame.regime == old, col]
        return welch(a, b)

    prim = did(m, "es_d_T1vsT2", "T+1", "T+2")
    print("\nPRIMARY: ES  [mean_T+1(W[L-3,L-1] - W[L-4,L-2])] - [same in T+2]   (bp per 3-day window; prediction < 0)")
    print("  " + fmt(prim))
    t = prim["t"]
    v_3b = "PASS (convincing, t <= -3)" if t <= -3 else ("WORTH A SECOND LOOK (-3 < t <= -2)" if t <= -2 else "FAIL (t > -2)")
    print(f"3b verdict: {v_3b}")

    print("\nWindow means by regime (bp per 3-day window, one-sample t):")
    comp = []
    for reg in ["T+3", "T+2", "T+1"]:
        g = m[m.regime == reg]
        for col in ["es_W5_3", "es_W4_2", "es_W3_1", "es_d_T1vsT2", "es_d_T2vsT3",
                    "y_W5_3", "y_W4_2", "y_W3_1", "y_d_T1vsT2", "y_d_T2vsT3"]:
            o = one_sample(g[col])
            comp.append(dict(regime=reg, quantity=col, mean_bp=o["mean"], t=o["t"], n=o["n"]))
    comp = pd.DataFrame(comp)
    print(comp.pivot(index="quantity", columns="regime", values="mean_bp")[["T+3", "T+2", "T+1"]].round(1).to_string())
    print(comp.pivot(index="quantity", columns="regime", values="t")[["T+3", "T+2", "T+1"]].round(2).to_string())

    rob = []
    rob.append(dict(test="PRIMARY ES: T+1 vs T+2 shift", prediction="< 0", **prim))
    rob.append(dict(test="y (rebalancing-signed): T+1 vs T+2 shift", prediction="> 0",
                    **did(m, "y_d_T1vsT2", "T+1", "T+2")))
    rob.append(dict(test="ES: T+2 vs T+3 shift (2017)", prediction="< 0", **did(m, "es_d_T2vsT3", "T+2", "T+3")))
    rob.append(dict(test="y: T+2 vs T+3 shift (2017)", prediction="> 0", **did(m, "y_d_T2vsT3", "T+2", "T+3")))
    pm = month_windows(df, "M")
    rob.append(dict(test="PLACEBO mid-month anchor, ES: T+1 vs T+2", prediction="none",
                    **did(pm, "es_d_T1vsT2", "T+1", "T+2")))
    rob.append(dict(test="PLACEBO mid-month anchor, y: T+1 vs T+2", prediction="none",
                    **did(pm, "y_d_T1vsT2", "T+1", "T+2")))
    rob.append(dict(test="PLACEBO mid-month anchor, ES: T+2 vs T+3", prediction="none",
                    **did(pm, "es_d_T2vsT3", "T+2", "T+3")))
    rob = pd.DataFrame(rob)
    print("\nDiD tests (bp per 3-day window, Welch t):")
    print(rob.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    pm.to_csv(HERE / "monthly_windows_placebo.csv", index=False, float_format="%.3f")
    rob.to_csv(HERE / "did_tests.csv", index=False, float_format="%.4f")
    comp.to_csv(HERE / "window_means_by_regime.csv", index=False, float_format="%.4f")

    # POST-HOC fragility check (not pre-registered; can only weaken the primary): drop one T+1 month at a time
    t1 = m[m.regime == "T+1"]
    loo = []
    for mo in t1["month"]:
        r = welch(t1.loc[t1.month != mo, "es_d_T1vsT2"], m.loc[m.regime == "T+2", "es_d_T1vsT2"])
        loo.append((mo, r["diff"], r["t"]))
    loo = pd.DataFrame(loo, columns=["dropped_month", "diff", "t"])
    worst = loo.loc[loo["t"].idxmax()]
    print(f"\nPOST-HOC (not pre-registered) leave-one-T+1-month-out: t ranges {loo['t'].min():.2f} .. "
          f"{loo['t'].max():.2f}; weakest when dropping {worst['dropped_month']} (diff {worst['diff']:.1f} bp, "
          f"t {worst['t']:.2f}); {int((loo['t'] > -2).sum())} of {len(loo)} single-month drops push t above -2")

    prof = profiles(df, m.loc[m.excluded_gap, "month"].tolist())
    prof.to_csv(HERE / "profiles.csv", index=False, float_format="%.4f")
    print("\nDay-by-day profiles (k = 0 is the last trading day L; mean bp/day, t):")
    wide = prof.pivot(index="k", columns="regime", values=["es_mean_bp", "es_t", "y_mean_bp", "y_t", "n"])
    print(wide.round(2).to_string())

    # ---------------- outputs ----------------
    out = df[["es_close", "zn_close", "r_es", "r_zn", "threshold", "calendar", "mod_calendar", "w_threshold", "w",
              "gross", "cost", "net", "y", "k_from_end", "is_L", "is_F", "gap_ret"]].copy()
    out.index.name = "date"
    out["period"] = np.where(out.index <= IS_END, "i", "ii")
    out.to_csv(HERE / "daily.csv", float_format="%.6g")
    chart(out.iloc[1:], HERE / "replication_equity.png")
    print("\nWrote daily.csv, monthly_windows.csv, monthly_windows_placebo.csv, profiles.csv, strategy_stats.csv, "
          "did_tests.csv, window_means_by_regime.csv, delta_diagnostics.csv, roll_checks.csv, replication_equity.png")


if __name__ == "__main__":
    buf = io.StringIO()

    class Tee(io.TextIOBase):
        def write(self, s):
            sys.__stdout__.write(s)
            buf.write(s)
            return len(s)

    with redirect_stdout(Tee()):
        main()
    (HERE / "run_output.txt").write_text(buf.getvalue())
