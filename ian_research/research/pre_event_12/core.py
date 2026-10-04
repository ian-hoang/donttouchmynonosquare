"""Small, auditable pre-event stock backtest. No API calls or parameter fitting.

All calendar decisions are made from the advance notice. Observed release dates
are audit fields, never used to retroactively improve an exit. Fill prices are
subsequent NBBO asks/bids, with adverse slippage and commission on both sides.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def dates_for_event(calendar, release_date, hold_sessions):
    cal = pd.DatetimeIndex(calendar)
    d = cal.searchsorted(pd.Timestamp(release_date), side="left")
    # A future event cannot be mapped to the last available trading session.
    if d >= len(cal):
        return None
    # Always liquidate on the session before the advertised calendar date.
    x, e = d - 1, d - 1 - hold_sessions
    if e < 1 or x >= len(cal):
        return None
    return {"signal_date": cal[e-1], "entry_date": cal[e], "exit_date": cal[x]}


def load_panel():
    cache = ROOT / "data/cache/ai_washing"
    px = pd.read_parquet(cache / "prices.parquet")
    cal = pd.DatetimeIndex(pd.read_parquet(cache / "calendar.parquet")["date"])
    # Do not use the cached return series: it bridges gaps up to five sessions.
    # Recompute on a complete calendar. Missing observations remain missing.
    groups = {}
    for ticker, g in px.groupby("ticker", sort=False):
        if g["date"].duplicated().any():
            continue
        g = g.set_index("date").reindex(cal)
        g["factor"] = g["close"] / g["close_raw"]
        g["ret"] = (g["close"] + g["div_adj"].fillna(0)) / g["close"].shift(1) - 1
        groups[ticker] = g
    spy_parts = []
    for p in sorted((ROOT / "data/cache/massive_grouped").glob("grouped_*.parquet")):
        if int(p.stem.split("_")[-1]) >= 2020:
            d = pd.read_parquet(p)
            spy_parts.append(d[d["ticker"] == "SPY"])
    spy = pd.concat(spy_parts).drop_duplicates("date").set_index("date").reindex(cal)
    if "close" not in spy:
        raise ValueError("SPY close missing")
    divs = json.loads((ROOT / "data/cache/world_cup/dividends_SPY.json").read_text())
    div = pd.DataFrame(divs)
    div["date"] = pd.to_datetime(div["ex_dividend_date"])
    amounts = div.groupby("date")["cash_amount"].sum()
    spy["div_adj"] = amounts.reindex(cal).fillna(0)
    spy["ret"] = (spy["close"] + spy["div_adj"]) / spy["close"].shift(1) - 1
    spy["factor"] = 1.0  # SPY has no split in this study's date range.
    groups["SPY"] = spy
    return cal, groups


def prior_jackpot(ticker, signal_date, release_history, panel, min_releases=4):
    """Largest three-session market-adjusted reaction among last four releases.

    The reaction covers closes D-2 to D+1, encompassing daily returns -1,0,+1.
    All three returns and the result publication must already be observable.
    Only verified actual releases are allowed; SEC filing dates are not releases.
    """
    if ticker not in panel:
        return None, []
    g, spy = panel[ticker], panel["SPY"]
    cal = g.index
    signal_date = pd.Timestamp(signal_date)
    hist = release_history[release_history["ticker"].eq(ticker)].copy()
    hist["release_date"] = pd.to_datetime(hist["release_date"])
    hist = hist[hist["release_date"] < signal_date].sort_values("release_date")
    # Retain one quarterly earnings release. Duplicate notices are not events.
    hist = hist.drop_duplicates("release_date")
    eligible = []
    for row in hist.itertuples():
        d = cal.searchsorted(row.release_date)
        # A same-day closing return is not known at the 15:55 feature cutoff.
        if d < 2 or d+1 >= len(cal) or cal[d+1] >= signal_date:
            continue
        if (signal_date-row.release_date).days > 450:
            continue
        if hasattr(row,"sec_accepted_utc") and pd.notna(row.sec_accepted_utc):
            available=pd.Timestamp(row.sec_accepted_utc)
            from options_audit import cutoff
            feature_cutoff=pd.Timestamp(cutoff(str(signal_date.date())))
            if available>feature_cutoff:
                continue
        eligible.append((row,d))
    # Freeze the four actual prior events before checking price completeness.
    eligible=eligible[-4:]
    if len(eligible)==4:
        release_dates=[pd.Timestamp(row.release_date) for row,_ in eligible]
        gaps=np.diff(np.array(release_dates,dtype='datetime64[D]')).astype(int)
        if (signal_date-release_dates[-1]).days>150 or (gaps<40).any() or (gaps>140).any():
            return None, []
    reactions=[]
    for row,d in eligible:
        own = g["ret"].iloc[d-1:d+2]
        market = spy["ret"].iloc[d-1:d+2]
        if own.isna().any() or market.isna().any():
            return None, reactions
        reactions.append({"release_date": str(row.release_date.date()),
                          "known_by": str(cal[d+1].date()),
                          "reaction": float((1+own).prod()-(1+market).prod())})
    if len(reactions) < min_releases:
        return None, reactions
    return max(r["reaction"] for r in reactions), reactions


def event_return(row, entry_quote, exit_quote, spy_entry, spy_exit, panel,
                 slippage_bps=1.0, fee_bps=.5, cost_multiplier=1.0):
    """Executable long-only return; separate matched SPY opportunity cost.

    Cost stress doubles observed half spreads and assumed extra costs. Exit
    quality never determines selection: missing exit data produces an explicit
    unresolved record, not a dropped successful-trades-only sample.
    """
    ticker, e, x = row["ticker"], pd.Timestamp(row["entry_date"]), pd.Timestamp(row["exit_date"])
    if any(q is None for q in (entry_quote, exit_quote, spy_entry, spy_exit)):
        return {"status": "unresolved_missing_quote"}
    if ticker not in panel:
        return {"status": "unresolved_missing_prices"}
    g = panel[ticker]
    window = g.loc[e:x]
    if window["close"].isna().any() or window["factor"].isna().any():
        return {"status": "unresolved_missing_price_or_factor"}
    f0, f1 = g.at[e,"factor"], g.at[x,"factor"]
    q0, q1 = entry_quote, exit_quote
    buy = q0["mid"] + cost_multiplier*(q0["ask"]-q0["mid"])
    sell = q1["mid"] - cost_multiplier*(q1["mid"]-q1["bid"])
    slip, fee = slippage_bps*cost_multiplier/1e4, fee_bps*cost_multiplier/1e4
    buy *= (1+slip)
    sell *= (1-slip)
    div = g.loc[e:x,"div_adj"].iloc[1:].fillna(0).sum()
    capital = buy*f0*(1+fee)
    proceeds = sell*f1*(1-fee) + div
    gross = (q1["mid"]*f1+div)/(q0["mid"]*f0)-1
    net = proceeds/capital-1
    spy_div = panel["SPY"].loc[e:x,"div_adj"].iloc[1:].fillna(0).sum()
    spy_ret = (spy_exit["mid"]+spy_div)/spy_entry["mid"]-1
    before=g.loc[:pd.Timestamp(row.get('signal_date',e)),'ret'].iloc[:-1].tail(252)
    pair=pd.concat([before.rename('stock'),panel['SPY']['ret'].rename('market')],axis=1).loc[before.index].dropna()
    beta=float(pair.stock.cov(pair.market)/pair.market.var()) if len(pair)>=120 and pair.market.var()>0 else np.nan
    return {"status": "ok", "gross": float(gross), "net": float(net),
            "spy": float(spy_ret), "market_adjusted_net": float(net-spy_ret),
            "past_beta":beta,"beta_adjusted_net":float(net-beta*spy_ret),
            "entry_spread_bps": q0["spread_fraction"]*1e4,
            "exit_spread_bps": q1["spread_fraction"]*1e4,
            "dividends_adj": float(div), "entry_factor": float(f0), "exit_factor": float(f1),
            "buy_adj_including_fee": float(capital), "sell_adj_net_fee":float(sell*f1*(1-fee))}


def summarize(frame, field="net", draws=3000):
    """Mean and week-cluster bootstrap CI. No independent-event t-test."""
    if frame.empty:
        return {"n": 0}
    v = frame[field].astype(float)
    weeks = pd.to_datetime(frame["entry_date"]).dt.to_period("W-SUN").astype(str)
    clusters = pd.DataFrame({"x":v.to_numpy(), "week":weeks.to_numpy()}).groupby("week")["x"].agg(["sum","count"])
    rng = np.random.default_rng(20261003)
    if len(clusters) >= 2:
        picks = rng.integers(0,len(clusters),(draws,len(clusters)))
        means = clusters["sum"].to_numpy()[picks].sum(axis=1)/clusters["count"].to_numpy()[picks].sum(axis=1)
        lo,hi = np.quantile(means,[.025,.975])
    else:
        lo=hi=np.nan
    return {"n":len(v), "entry_weeks":len(clusters), "mean":float(v.mean()),
            "median":float(v.median()), "win_rate":float((v>0).mean()),
            "ci95_week_cluster":[float(lo),float(hi)], "worst":float(v.min()), "best":float(v.max())}


def portfolio(events, panel, initial_cash=100000., ticket=10000., start=None, end=None):
    """Fixed-dollar, unlevered cash portfolio. No assumed fully invested returns.

    Trades are entered only if cash and entry ask depth suffice; simultaneous
    entries are ordered by descending signal then ticker. Actual fill timestamps
    order entries/exits, including a delayed exit after another scheduled entry.
    Cash earns zero. Dividend accrual is on ex-date; mark-to-market uses daily
    adjusted closes. Corporate-action factors map actual shares to price units.
    """
    if events.empty:
        return pd.DataFrame(), {"trades":0}
    events = events.copy()
    for col in ["entry_date","exit_date"]:
        events[col] = pd.to_datetime(events[col])
    cal = panel["SPY"].index
    lo = pd.Timestamp(start) if start is not None else events.entry_date.min()
    hi = pd.Timestamp(end) if end is not None else events.exit_date.max()
    if lo > events.entry_date.min() or hi < events.exit_date.max():
        raise ValueError("Portfolio period does not contain all positions")
    cal = cal[(cal>=lo) & (cal<=hi)]
    cash=initial_cash
    positions={}
    path=[]
    skipped=[]
    closed=[]
    shallow_exits=[]
    for day in cal:
        actions=[]
        for key,p in list(positions.items()):
            g=panel[p["ticker"]]
            dividend=float(g.at[day,"div_adj"]) if pd.notna(g.at[day,"div_adj"]) else 0.
            cash += p["units"]*dividend
            if day == p["exit_date"]:
                actions.append((int(p.get('exit_timestamp_ns',0)),0,0.,p['ticker'],key,p))
        today=events[events.entry_date.eq(day)].sort_values(["signal","ticker"],ascending=[False,True])
        for key,r in today.iterrows():
            actions.append((int(r.get('entry_timestamp_ns',1)),1,-float(r.signal),r.ticker,key,r))
        for _,kind,_,_,key,r in sorted(actions,key=lambda a:a[:4]):
            if kind==0:
                required_raw=r['units']*r.get('exit_factor',r['entry_factor'])
                if required_raw>r.get('exit_bid_size',float('inf')):
                    shallow_exits.append({'id':str(key),'shares':required_raw,'bid_size':r['exit_bid_size']})
                cash += r["units"]*r["sell_adj_net_fee"]
                closed.append(key)
                del positions[key]
                continue
            if r.ticker in [p["ticker"] for p in positions.values()]:
                skipped.append((str(key),"overlap_same_stock")); continue
            budget=min(ticket,cash)
            # Round to whole raw shares, then express in adjusted price units.
            raw_allin=r.buy_adj_including_fee/r.entry_factor
            shares=int(np.floor(budget/raw_allin))
            if budget < ticket or shares<1:
                skipped.append((str(key),"capital")); continue
            if shares>r.entry_ask_size:
                skipped.append((str(key),"displayed_size")); continue
            units=shares/r.entry_factor
            cash-=units*r.buy_adj_including_fee
            positions[key]=dict(r)|{"units":units}
        value=cash
        for p in positions.values():
            mark=panel[p["ticker"]].at[day,"close"]
            if pd.isna(mark):
                raise ValueError("Missing portfolio mark; do not silently forward-fill")
            value+=p["units"]*mark
        path.append({"date":day,"equity":value,"cash":cash,"positions":len(positions)})
    d=pd.DataFrame(path).set_index("date")
    returns=d.equity.pct_change()
    returns.iloc[0]=d.equity.iloc[0]/initial_cash-1
    peak=np.maximum.accumulate(np.r_[initial_cash,d.equity.to_numpy()])[1:]
    return d, {"trades":len(closed),"skipped":skipped,"exit_depth_exceeded":shallow_exits,"initial_cash":initial_cash,
               "pnl":float(d.equity.iloc[-1]-initial_cash),
               "total_return":float(d.equity.iloc[-1]/initial_cash-1),
               "max_drawdown":float((d.equity.to_numpy()/peak-1).min()),
               "daily_sharpe_zero_cash_rate":float(returns.mean()/returns.std(ddof=1)*np.sqrt(252)) if returns.std()>0 else None,
               "mean_deployed_fraction":float((1-d.cash/d.equity).mean()),"sessions":len(d)}


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
