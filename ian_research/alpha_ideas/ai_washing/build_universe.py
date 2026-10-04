"""Step 1 — company-level (CIK) daily prices, total returns and the monthly top-1,000 universe.

Run from the repo root:  uv run python alpha_ideas/ai_washing/build_universe.py
Inputs: cached Massive grouped daily bars + tickers_cs.parquet (data/cache/massive_grouped/), and from Massive:
ticker-change events (to follow renames like FB -> META), cash dividends and splits.
Outputs in data/cache/ai_washing/: entity_intervals.parquet, prices.parquet, universe.parquet, dividends_adj.parquet.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from common import CACHE, GROUPED, PRICE_END, PRICE_START, massive_all, massive_get, write_json

EVENTS = CACHE / "events"
EVENTS.mkdir(exist_ok=True)
EARLY, FAR = pd.Timestamp("1900-01-01"), pd.Timestamp("2100-01-01")
MAX_GAP_MISSING = 5          # returns spanning more than 5 missing trading days are dropped
MAX_ABS_RET = 1.0            # |daily return| > 100% treated as a bad print
TOP_N = 1000
MIN_PRICE = 5.0


# ------------------------------------------------------------------------------------------- reference rows
def load_reference() -> pd.DataFrame:
    ref = pd.read_parquet(GROUPED / "tickers_cs.parquet")
    ref = ref[ref["cik"].notna() & (ref["cik"].astype(str).str.len() > 0)].copy()
    ref["cik"] = ref["cik"].astype(str).str.zfill(10)
    d = pd.to_datetime(ref["delisted_utc"], utc=True, errors="coerce")
    ref["delisted"] = d.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    ref = ref[ref["active"] | (ref["delisted"] >= pd.Timestamp(PRICE_START))].copy()
    has_figi = ref["composite_figi"].notna() & (ref["composite_figi"].astype(str).str.len() > 0)
    ref["entity"] = np.where(has_figi, ref["composite_figi"].astype(str),
                             "T:" + ref["ticker"].astype(str) + ":" + ref["cik"])
    # One row per entity: prefer the active row, then the latest delisting.
    ref = (ref.assign(_d=ref["delisted"].fillna(FAR))
              .sort_values(["entity", "active", "_d"], ascending=[True, False, False])
              .drop_duplicates("entity").drop(columns="_d"))
    # Event lookups: by FIGI when we have one; by ticker only for active rows without FIGI (an inactive ticker may
    # now belong to someone else).
    ref["event_id"] = np.where(has_figi.loc[ref.index], ref["composite_figi"],
                               np.where(ref["active"], ref["ticker"], None))
    return ref.reset_index(drop=True)


def fetch_events(ids: list[str]) -> dict[str, dict]:
    def one(i):
        path = EVENTS / f"{i.replace('/', '_')}.json"
        if path.exists():
            return i, json.loads(path.read_text())
        status, j = massive_get(f"/vX/reference/tickers/{i}/events")
        res = j.get("results", {}) if status == 200 else {}
        write_json(path, res)
        return i, res
    with ThreadPoolExecutor(8) as pool:
        return dict(pool.map(one, ids))


def build_intervals(ref: pd.DataFrame, events: dict[str, dict]) -> pd.DataFrame:
    rows, mismatched_cik, last_ticker_mismatch = [], 0, 0
    for r in ref.itertuples(index=False):
        end_final = r.delisted if pd.notna(r.delisted) else FAR
        res = events.get(r.event_id) or {} if r.event_id else {}
        if res and res.get("cik") and str(res["cik"]).zfill(10) != r.cik:
            mismatched_cik += 1
            res = {}
        evs = sorted((pd.Timestamp(e["date"]), e["ticker_change"]["ticker"])
                     for e in res.get("events", []) if e.get("type") == "ticker_change" and e.get("ticker_change"))
        if evs and evs[-1][1] != r.ticker:
            # Massive's ticker events are per company, not per share class: GOOGL's FIGI returns GOOG's history,
            # LEN.B's returns LEN's. Events only describe this row if they end in this row's own ticker.
            last_ticker_mismatch += 1
            evs = []
        if not evs:
            rows.append((r.entity, r.cik, r.ticker, EARLY, end_final, False, True))
            continue
        # Before the first recorded event we assume the first ticker was already in use (weaker evidence, so it
        # loses every conflict). Needed for re-organisations that got a new FIGI but kept the ticker (XOM moved to
        # ExxonMobil Holdings in 2026-07 and the old Exxon entity is not in Massive's list). Risk: an earlier user of
        # the ticker that is not a common stock (ETF/ADR) gets attached; that can only touch peer benchmarks, not
        # events, because events need several years of the company's own 8-Ks.
        rows.append((r.entity, r.cik, evs[0][1], EARLY, evs[0][0] - pd.Timedelta(days=1), False, evs[0][1] == r.ticker))
        if evs[0][1] != r.ticker:
            # Some histories only hold recent oddities (Honeywell: a two-week "HONI" in 2026-06, then HON again), so
            # the company's own ticker also gets a weak claim before its first recorded event.
            rows.append((r.entity, r.cik, r.ticker, EARLY, evs[0][0] - pd.Timedelta(days=1), False, True))
        for k, (d, tk) in enumerate(evs):
            end = evs[k + 1][0] - pd.Timedelta(days=1) if k + 1 < len(evs) else end_final
            rows.append((r.entity, r.cik, tk, d, end, True, tk == r.ticker))
    iv = pd.DataFrame(rows, columns=["entity", "cik", "ticker", "start", "end", "explicit", "own"])
    iv = iv[iv["end"] >= iv["start"]]
    print(f"intervals: {len(iv):,} for {iv['entity'].nunique():,} entities; events with mismatched CIK ignored: "
          f"{mismatched_cik}; events ignored because they end in another ticker (other share class): "
          f"{last_ticker_mismatch}")
    return iv


# ------------------------------------------------------------------------------------------- prices
def load_grouped() -> pd.DataFrame:
    years = range(pd.Timestamp(PRICE_START).year, pd.Timestamp(PRICE_END).year + 1)
    g = pd.concat([pd.read_parquet(GROUPED / f"grouped_{y}.parquet",
                                   columns=["date", "ticker", "close", "volume", "close_raw"]) for y in years])
    g["date"] = pd.to_datetime(g["date"]).dt.normalize()
    g = g[(g["date"] >= PRICE_START) & (g["date"] <= PRICE_END)]
    g["ticker"] = g["ticker"].astype(str)
    return g


def map_prices(g: pd.DataFrame, iv: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for _, gy in g.groupby(g["date"].dt.year):  # year by year to keep the merge small
        my = gy.merge(iv, on="ticker", how="inner")
        parts.append(my[(my["date"] >= my["start"]) & (my["date"] <= my["end"])])
    m = pd.concat(parts, ignore_index=True)
    # A (ticker, date) claimed by several entities. A ticker belongs to one listed company at a time, so:
    # 1) an event-dated (explicit) claim beats an open-ended default claim;
    # 2) among the rest, the claim that ends first wins (a delisted company held the ticker until its delisting,
    #    a later company re-using the ticker only started after that);
    # 3) still tied -> ambiguous, dropped.
    n = m.groupby(["ticker", "date"])["entity"].transform("size")
    multi = m[n > 1].copy()
    n_multi = multi[["ticker", "date"]].drop_duplicates().shape[0]
    multi["_rank_explicit"] = ~multi["explicit"]
    multi = multi.sort_values(["ticker", "date", "_rank_explicit", "end"])
    first = multi.groupby(["ticker", "date"]).head(1)
    second = multi.groupby(["ticker", "date"]).nth(1)
    tie = first.merge(second[["ticker", "date", "_rank_explicit", "end"]], on=["ticker", "date"],
                      suffixes=("", "_2"))
    tie = tie[(tie["_rank_explicit"] == tie["_rank_explicit_2"]) & (tie["end"] == tie["end_2"])]
    resolved = first.merge(tie[["ticker", "date"]], on=["ticker", "date"], how="left", indicator=True)
    resolved = resolved[resolved["_merge"] == "left_only"].drop(columns=["_merge", "_rank_explicit"])
    m = pd.concat([m[n == 1], resolved], ignore_index=True)
    print(f"ticker-days claimed by >1 entity: {n_multi:,}; resolved: {len(resolved):,}; "
          f"dropped as ambiguous: {n_multi - len(resolved):,}")
    m["dv"] = m["close"] * m["volume"]  # split-adjusted close x split-adjusted volume = raw dollar volume
    # A company trades under one ticker per day. If weak claims gave it two (its own ticker and a placeholder from
    # its event history), keep: event-dated claim first, then its own ticker, then the more traded one.
    before = len(m)
    m = (m.sort_values(["entity", "date", "explicit", "own", "dv"], ascending=[True, True, False, False, False])
           .drop_duplicates(["entity", "date"]))
    print(f"same company, same day, two tickers: {before - len(m):,} rows dropped")
    return m.drop(columns=["start", "end", "explicit", "own"])


def primary_entities(m: pd.DataFrame) -> pd.DataFrame:
    """One share class per CIK: the entity with the most dollar volume over the sample."""
    tot = m.groupby(["cik", "entity"])["dv"].sum().reset_index().sort_values(["cik", "dv"], ascending=[True, False])
    prim = tot.drop_duplicates("cik")
    multi = tot.groupby("cik").size()
    print(f"CIKs: {len(prim):,}; with >1 share-class entity: {(multi > 1).sum():,} (kept the most traded one)")
    out = m[m["entity"].isin(prim["entity"])].copy()
    dup = out.duplicated(["cik", "date"]).sum()
    assert dup == 0, f"{dup} duplicate (cik, date) rows after picking primary entities"
    return out.sort_values(["cik", "date"]).reset_index(drop=True)


# ------------------------------------------------------------------------------------------- dividends
def fetch_dividends(tickers: list[str]) -> pd.DataFrame:
    """Cash dividends for the given (current/last) tickers only; Massive files dividends under the current ticker."""
    ddir = CACHE / "dividends"
    ddir.mkdir(exist_ok=True)

    def one(t):
        path = ddir / f"{t.replace('/', '_')}.json"
        if path.exists():
            return json.loads(path.read_text())
        rows = massive_all("/v3/reference/dividends", {"ticker": t, "ex_dividend_date.gte": PRICE_START,
                                                        "ex_dividend_date.lte": PRICE_END, "limit": 1000})
        write_json(path, rows)
        return rows
    with ThreadPoolExecutor(8) as pool:
        rows = [r for rs in pool.map(one, tickers) for r in rs]
    return pd.DataFrame(rows)


def fetch_splits() -> pd.DataFrame:
    spath = CACHE / "splits_raw.parquet"
    if not spath.exists():
        rows = massive_all("/v3/reference/splits", {"execution_date.gte": PRICE_START, "limit": 1000})
        pd.DataFrame(rows).to_parquet(spath, index=False)
    return pd.read_parquet(spath)


def adjust_dividends(div: pd.DataFrame, spl: pd.DataFrame) -> pd.DataFrame:
    div = div[(div["currency"].fillna("USD") == "USD") & div["dividend_type"].isin(["CD", "SC"])].copy()
    div["ex"] = pd.to_datetime(div["ex_dividend_date"])
    div = div.drop_duplicates(["ticker", "ex", "cash_amount", "dividend_type"])
    spl = spl.copy()
    spl["exec"] = pd.to_datetime(spl["execution_date"])
    spl["ratio"] = spl["split_to"] / spl["split_from"]
    spl = spl.drop_duplicates(["ticker", "exec", "ratio"])
    by_t = {t: g[["exec", "ratio"]].to_numpy() for t, g in spl.groupby("ticker")}
    factors = []
    for t, ex in zip(div["ticker"], div["ex"]):
        f = 1.0
        for e, ratio in by_t.get(t, []):
            if e > ex:
                f *= ratio
        factors.append(f)
    div["factor"] = factors
    div["div_adj"] = div["cash_amount"] / div["factor"]
    return div


def attach_dividends(px: pd.DataFrame, div: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    # Massive files dividends under the company's current ticker, so match on the reference ticker of the entity
    # and require the ex-date to fall inside that entity's trading life.
    ent = ref[["entity", "ticker"]].rename(columns={"ticker": "ref_ticker"})
    life = px.groupby("entity")["date"].agg(first="min", last="max").reset_index().merge(ent, on="entity")
    d = div.merge(life, left_on="ticker", right_on="ref_ticker", how="inner")
    d = d[(d["ex"] >= d["first"]) & (d["ex"] <= d["last"])]
    amb = d.groupby(["ticker", "ex", "cash_amount"])["entity"].transform("nunique") > 1
    print(f"dividends matched to traded entities: {len(d):,}; ambiguous (dropped): {int(amb.sum())}")
    d = d[~amb]
    # Put each dividend on the first trading row of that entity on/after the ex-date.
    dates_by_entity = {e: g["date"].to_numpy() for e, g in px[["entity", "date"]].groupby("entity")}
    out = []
    for e, g in d.groupby("entity"):
        dates = dates_by_entity[e]  # px is sorted by (cik, date) and has one entity per CIK, so dates are sorted
        pos = np.searchsorted(dates, g["ex"].to_numpy())
        ok = pos < len(dates)
        out.append(pd.DataFrame({"entity": e, "date": dates[pos[ok]], "div_adj": g["div_adj"].to_numpy()[ok]}))
    da = pd.concat(out).groupby(["entity", "date"], as_index=False)["div_adj"].sum()
    return px.merge(da, on=["entity", "date"], how="left").fillna({"div_adj": 0.0})


def add_returns(px: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.DataFrame:
    idx = pd.Series(np.arange(len(cal)), index=cal)
    px = px.sort_values(["cik", "date"]).copy()
    px["di"] = idx.reindex(px["date"]).to_numpy()
    prev_close = px.groupby("cik")["close"].shift(1)
    prev_di = px.groupby("cik")["di"].shift(1)
    gap_missing = px["di"] - prev_di - 1
    ret_px = px["close"] / prev_close - 1
    ret_tot = (px["close"] + px["div_adj"]) / prev_close - 1
    bad = prev_close.isna() | (gap_missing > MAX_GAP_MISSING) | (ret_tot.abs() > MAX_ABS_RET) | (prev_close <= 0)
    print(f"daily returns: {len(px):,} rows; set missing: first-day {int(prev_close.isna().sum()):,}, "
          f"gap>{MAX_GAP_MISSING}d {int((gap_missing > MAX_GAP_MISSING).sum()):,}, "
          f"|r|>100% {int((ret_tot.abs() > MAX_ABS_RET).sum()):,}")
    px["ret_px"] = ret_px.where(~bad)
    px["ret"] = ret_tot.where(~bad)
    return px


# ------------------------------------------------------------------------------------------- universe
def monthly_universe(px: pd.DataFrame, cal: pd.DatetimeIndex) -> pd.DataFrame:
    dv = px.pivot(index="date", columns="cik", values="dv").reindex(cal)
    raw = px.pivot(index="date", columns="cik", values="close_raw").reindex(cal).ffill(limit=5)
    dv63 = dv.rolling(63, min_periods=40).mean()
    month_ends = pd.Series(cal, index=cal).groupby(cal.to_period("M")).max()
    month_ends = month_ends[(month_ends >= "2020-06-01") & (month_ends <= "2026-08-31")]
    rows = []
    for me in month_ends:
        s = dv63.loc[me]
        p = raw.loc[me]
        ok = s.notna() & (p >= MIN_PRICE)
        top = s[ok].sort_values(ascending=False).head(TOP_N)
        rank = np.arange(1, len(top) + 1)
        tercile = np.where(rank <= len(top) / 3, 3, np.where(rank <= 2 * len(top) / 3, 2, 1))  # 3 = most traded
        rows.append(pd.DataFrame({"month_end": me, "cik": top.index, "dv63": top.to_numpy(), "rank": rank,
                                  "tercile": tercile, "close_raw": p[top.index].to_numpy()}))
    return pd.concat(rows, ignore_index=True)


# ------------------------------------------------------------------------------------------- audit
def audit(px: pd.DataFrame, uni: pd.DataFrame, g: pd.DataFrame, iv: pd.DataFrame, mapped_all: pd.DataFrame):
    print("\n=== audit ===")
    def show(cik, d0, d1, label):
        x = px[(px["cik"] == cik) & (px["date"] >= d0) & (px["date"] <= d1)]
        print(f"{label}:\n" + x[["date", "ticker", "close", "close_raw", "div_adj", "ret_px", "ret"]].to_string(index=False))
    show("0001326801", "2022-06-06", "2022-06-13", "META (FB until 2022-06-08)")
    show("0000320193", "2020-08-26", "2020-09-01", "AAPL 4:1 split on 2020-08-31")
    show("0001045810", "2024-06-05", "2024-06-12", "NVDA 10:1 split 2024-06-10, $0.01 dividend ex 2024-06-11")
    for cik, name in [("0002115436", "XOM"), ("0000773840", "HON"), ("0000019617", "JPM"), ("0000021344", "KO"),
                      ("0000320193", "AAPL")]:
        x = px[(px["cik"] == cik) & (px["date"].dt.year == 2023)]
        if len(x):
            print(f"{name} 2023: {len(x)} trading days, dividends/avg price = {x['div_adj'].sum() / x['close'].mean():.2%}; "
                  f"total-minus-price return = {(1 + x['ret']).prod() - (1 + x['ret_px']).prod():+.2%}")
        else:
            print(f"{name} 2023: NO PRICE ROWS")
    sizes = uni.groupby("month_end").size()
    print(f"universe months {sizes.index.min().date()} -> {sizes.index.max().date()}, size min/max "
          f"{sizes.min()}/{sizes.max()}, unique CIKs {uni['cik'].nunique():,}")
    # Mapping coverage: of the 1,500 most-traded tickers that look like common stock (they appear in a CS interval),
    # how many map to no company at all? Checked on the full mapped set, not just universe members.
    for me in [pd.Timestamp("2021-12-31"), pd.Timestamp("2024-06-28"), pd.Timestamp("2026-06-30")]:
        gg = g[(g["date"] > me - pd.Timedelta(days=92)) & (g["date"] <= me)].copy()
        gg["dv"] = gg["close"] * gg["volume"]
        top = gg.groupby("ticker")["dv"].mean().sort_values(ascending=False).head(1500)
        win = mapped_all[(mapped_all["date"] > me - pd.Timedelta(days=92)) & (mapped_all["date"] <= me)]
        mapped = set(win["ticker"])
        cs = set(iv["ticker"])
        un = [t for t in top.index if t in cs and t not in mapped]
        print(f"{me.date()}: top-1,500 tickers that look like CS but map to no company: {len(un)} -> {un[:30]}")


def main():
    ref = load_reference()
    ids = sorted({i for i in ref["event_id"].dropna()})
    print(f"reference entities: {len(ref):,}; fetching ticker-change events for {len(ids):,} ids (cached)")
    events = fetch_events(ids)
    iv = build_intervals(ref, events)
    iv.to_parquet(CACHE / "entity_intervals.parquet", index=False)

    g = load_grouped()
    cal = pd.DatetimeIndex(sorted(g["date"].unique()))
    m = map_prices(g[g["ticker"].isin(set(iv["ticker"]))], iv)
    px = primary_entities(m)

    uni = monthly_universe(px, cal)
    uni.to_parquet(CACHE / "universe.parquet", index=False)
    px = px[px["cik"].isin(set(uni["cik"]))].copy()  # returns are only needed for companies that enter the universe
    tickers = sorted(ref.loc[ref["entity"].isin(set(px["entity"])), "ticker"].unique())
    print(f"universe companies: {uni['cik'].nunique():,}; fetching dividends for {len(tickers):,} tickers (cached)")
    div = adjust_dividends(fetch_dividends(tickers), fetch_splits())
    div.to_parquet(CACHE / "dividends_adj.parquet", index=False)
    px = attach_dividends(px, div, ref)
    px = add_returns(px, cal)
    px[["date", "cik", "entity", "ticker", "close", "close_raw", "volume", "dv", "div_adj", "ret_px", "ret"]] \
        .to_parquet(CACHE / "prices.parquet", index=False)
    pd.Series(cal).to_frame("date").to_parquet(CACHE / "calendar.parquet", index=False)
    audit(px, uni, g, iv, m[["date", "ticker"]])


if __name__ == "__main__":
    main()
