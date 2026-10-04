"""The starter notebook's 8-K × options pipeline as an importable module, for research scripts.

Sections 1-7 of `gator-quant-hacks-8k-options-challenge.ipynb`, copied so we can scan many tags without
re-running the notebook. It shares the notebook's `.massive_cache/` (same URLs, same cache keys), so
anything fetched here is free when the notebook runs. Deliberate changes are marked CHANGED:

  1. HTTP sessions are per thread and cache writes are atomic, so events can be priced in parallel.
  2. `t_pre` (where the chain is read) and `t_0` (the "post" entry) are set separately. The
     "next_session" timing enters the session *after* the filing date, which removes the starter's
     after-the-bell look-ahead without needing EDGAR acceptance times.
  3. `evaluate` also records each leg's entry premium and volume, for costs and capacity.
  4. A guard refuses any event window that touches the out-of-sample period unless allow_oos=True.
"""
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, nearest_workday, USMartinLutherKingJr,
                                    USPresidentsDay, GoodFriday, USMemorialDay, USLaborDay, USThanksgivingDay)
from pandas.tseries.offsets import CustomBusinessDay

ROOT = Path(__file__).resolve().parent
BASE_URL = "https://api.massive.com"
CACHE_DIR = ROOT / ".massive_cache"

# ---- The notebook's configuration (section 2), unchanged -----------------------------------------
STUDY_START, STUDY_END = "2024-01-01", "2025-12-31"
OOS_START, OOS_END = "2026-01-01", "2026-08-31"
TOP_100 = """
AAPL ABBV ABT ACN ADBE AIG AMD AMGN AMT AMZN AVGO AXP BA BAC BK BKNG BLK BMY BRK.B C
CAT CHTR CL CMCSA COF COP COST CRM CSCO CVS CVX DE DHR DIS DUK EMR FDX GD GE GILD
GM GOOGL GS HD HON IBM INTC INTU ISRG JNJ JPM KO LIN LLY LMT LOW MA MCD MDLZ MDT
MET META MMM MO MRK MS MSFT NEE NFLX NKE NOW NVDA ORCL PEP PFE PG PLTR PM PYPL QCOM
RTX SBUX SCHW SO T TGT TMO TMUS TSLA TXN UBER UNH UNP UPS USB V VZ WFC WMT XOM
""".split()
EXPIRY_BUCKETS = {"1m": (21, 45, 30), "2m": (46, 80, 60), "3-6m": (90, 180, 120)}
BASELINE_BUCKET = "3-6m"
HORIZONS = [1, 2, 3, 5, 10, 21, 42, 63]
OTM_GRID = [0.03, 0.05, 0.10]
RISK_FREE = 0.04
STRIKE_WINDOW = 0.25
MAX_STALE_SESSIONS = 3

STRATEGIES = ["stock", "long_call", "covered_call", "protective_put", "collar", "cash_secured_put"]
STRATEGY_LABEL = {"stock": "Stock only (synthetic)", "long_call": "1 · Long call", "covered_call": "2 · Covered call",
                  "protective_put": "3 · Protective put", "collar": "4 · Collar", "cash_secured_put": "5 · Cash-secured put"}


# ---- 1 · API client --------------------------------------------------------------------------------
def load_api_key(name: str = "MASSIVE_API_KEY") -> str:
    key = (os.environ.get(name) or "").strip()
    env_file = ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key or key == "your-key-here":
        raise SystemExit(f"No {name}: put it in {env_file}.")
    return key


_local = threading.local()


def _session() -> requests.Session:
    # CHANGED: one session per thread.
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {load_api_key()}"
        _local.session = s
    return s


def api_get(path_or_url: str, params: dict | None = None) -> dict:
    """GET one page, cached on disk by the full URL (same scheme as the notebook)."""
    url = path_or_url if path_or_url.startswith("http") else BASE_URL + path_or_url
    full_url = requests.Request("GET", url, params=params).prepare().url
    cache_file = CACHE_DIR / (hashlib.sha1(full_url.encode()).hexdigest() + ".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    for attempt in range(10):
        resp = _session().get(full_url, timeout=60)
        if resp.status_code in (429, 500, 502, 503, 504):
            retry_after = resp.headers.get("Retry-After", "")
            time.sleep(float(retry_after) if retry_after.isdigit() else min(2 ** attempt, 20))
            continue
        break
    resp.raise_for_status()
    payload = resp.json()
    CACHE_DIR.mkdir(exist_ok=True)
    tmp = cache_file.with_suffix(f".{threading.get_ident()}.tmp")     # CHANGED: atomic write
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, cache_file)
    return payload


def api_get_all(path: str, params: dict | None = None, max_pages: int = 500) -> list[dict]:
    payload = api_get(path, params)
    rows = list(payload.get("results") or [])
    pages = 1
    while payload.get("next_url") and pages < max_pages:
        payload = api_get(payload["next_url"])
        rows.extend(payload.get("results") or [])
        pages += 1
    return rows


# ---- 3 · Trading calendar --------------------------------------------------------------------------
class NYSEHolidays(AbstractHolidayCalendar):
    rules = [
        Holiday("New Year's Day", month=1, day=1,
                observance=lambda d: d + pd.Timedelta(days=1) if d.weekday() == 6 else d),
        USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
        Holiday("Independence Day", month=7, day=4, observance=nearest_workday),
        USLaborDay, USThanksgivingDay,
        Holiday("Christmas Day", month=12, day=25, observance=nearest_workday),
        Holiday("National day of mourning, President Carter", year=2025, month=1, day=9),
    ]


def trading_sessions(start, end) -> pd.DatetimeIndex:
    holidays = NYSEHolidays().holidays(pd.Timestamp(start) - pd.Timedelta(days=7), pd.Timestamp(end) + pd.Timedelta(days=7))
    return pd.bdate_range(start, end, freq=CustomBusinessDay(holidays=holidays))


CAL = trading_sessions("2021-06-01", "2027-12-31")
TODAY = pd.Timestamp.today().normalize()
LAST_SESSION = CAL[CAL.searchsorted(TODAY, side="right") - 1]


def session_on_or_after(day) -> pd.Timestamp:
    return CAL[CAL.searchsorted(pd.Timestamp(day), side="left")]


def session_before(day) -> pd.Timestamp:
    return CAL[CAL.searchsorted(pd.Timestamp(day), side="left") - 1]


def session_after(day) -> pd.Timestamp:
    return CAL[CAL.searchsorted(pd.Timestamp(day), side="right")]


def sessions_between(a, b) -> int:
    return int(CAL.searchsorted(pd.Timestamp(b), side="right") - CAL.searchsorted(pd.Timestamp(a), side="right"))


# ---- 4 · Events ------------------------------------------------------------------------------------
def normalize_ticker(t) -> str | None:
    if not isinstance(t, str) or not t.strip():
        return None
    return t.strip().upper().replace("/", ".")


def _check_window(start: str, end: str, allow_oos: bool):
    # CHANGED: the out-of-sample window stays closed until the final rule is frozen.
    if not allow_oos and pd.Timestamp(start) <= pd.Timestamp(OOS_END) and pd.Timestamp(end) >= pd.Timestamp(OOS_START):
        raise RuntimeError(f"{start}..{end} touches the out-of-sample window {OOS_START}..{OOS_END}. "
                           "Pass allow_oos=True only for the single final evaluation.")


def fetch_disclosures(tag: str, start: str, end: str, allow_oos: bool = False) -> pd.DataFrame:
    _check_window(start, end, allow_oos)
    rows = api_get_all("/stocks/filings/8-K/vX/disclosures", {
        "tertiary_category": tag, "filing_date.gte": start, "filing_date.lte": end,
        "limit": 1000, "sort": "filing_date.asc",
    })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["filing_date"] = pd.to_datetime(df["filing_date"])
    return df


def build_events(tags, start: str, end: str, universe: list[str] = TOP_100, timing: str = "next_session",
                 allow_oos: bool = False) -> pd.DataFrame:
    """One row per (filer, filing date) for one tag or a list of tags (a combined category).

    timing="filing_day" is the notebook's rule (enter at the close of the filing date; look-ahead for
    filings accepted after the bell). timing="next_session" enters one session later. Either way the
    chain is read on t_pre, the session before the filing date, so it cannot know the news.
    """
    tags = [tags] if isinstance(tags, str) else list(tags)
    raw = pd.concat([fetch_disclosures(t, start, end, allow_oos) for t in tags], ignore_index=True)
    if raw.empty:
        return pd.DataFrame(columns=["cik", "filing_date", "ticker", "t_pre", "t_0", "event_date", "tags"])
    ex = raw.explode("tickers").rename(columns={"tickers": "ticker"})
    ex["ticker"] = ex["ticker"].map(normalize_ticker)
    ex = ex[ex["ticker"].isin(universe)]
    ev = (ex.sort_values(["cik", "filing_date"])
            .groupby(["cik", "filing_date"], as_index=False)
            .agg(ticker=("ticker", "first"), accession_number=("accession_number", "first"),
                 filing_url=("filing_url", "first"), supporting_text=("supporting_text", "first"),
                 tags=("tertiary_category", lambda s: ",".join(sorted(set(s)))))
            .sort_values("filing_date").reset_index(drop=True))
    filing_session = ev["filing_date"].map(session_on_or_after)
    ev["t_pre"] = filing_session.map(session_before)
    ev["t_0"] = filing_session if timing == "filing_day" else filing_session.map(session_after)
    ev["event_date"] = ev["filing_date"]
    return ev


# ---- 5 · The chain and the hidden spot --------------------------------------------------------------
def option_bars(opt_ticker: str, start, end) -> pd.DataFrame:
    rows = api_get_all(f"/v2/aggs/ticker/{opt_ticker}/range/1/day/{pd.Timestamp(start):%Y-%m-%d}/{pd.Timestamp(end):%Y-%m-%d}",
                       {"adjusted": "false", "sort": "asc", "limit": 50000})
    if not rows:
        return pd.DataFrame(columns=["close", "volume"], index=pd.DatetimeIndex([], name="session"))
    idx = (pd.to_datetime([r["t"] for r in rows], unit="ms", utc=True)
             .tz_convert("America/New_York").normalize().tz_localize(None))
    return pd.DataFrame({"close": [float(r["c"]) for r in rows], "volume": [float(r.get("v") or 0) for r in rows]},
                        index=pd.DatetimeIndex(idx, name="session"))


def fetch_chain(ticker: str, as_of: pd.Timestamp, dte_lo: int, dte_hi: int) -> pd.DataFrame:
    rows = api_get_all("/v3/reference/options/contracts", {
        "underlying_ticker": ticker, "as_of": as_of.strftime("%Y-%m-%d"),
        "expiration_date.gte": (as_of + pd.Timedelta(days=dte_lo)).strftime("%Y-%m-%d"),
        "expiration_date.lte": (as_of + pd.Timedelta(days=dte_hi)).strftime("%Y-%m-%d"),
        "limit": 1000,
    })
    chain = pd.DataFrame(rows)
    if chain.empty:
        return chain
    if "shares_per_contract" in chain:
        chain = chain[chain["shares_per_contract"].fillna(100) == 100]
    chain = chain[["ticker", "contract_type", "strike_price", "expiration_date"]].copy()
    chain["expiration_date"] = pd.to_datetime(chain["expiration_date"])
    chain["dte"] = (chain["expiration_date"] - as_of).dt.days
    chain["strike_price"] = chain["strike_price"].astype(float)
    return chain.reset_index(drop=True)


def paired_strikes(e: pd.DataFrame) -> np.ndarray:
    both = e.groupby("strike_price")["contract_type"].nunique()
    return both[both == 2].index.to_numpy(dtype=float)


def contract(e: pd.DataFrame, strike: float, kind: str) -> str:
    return e[(e.strike_price == strike) & (e.contract_type == kind)]["ticker"].iloc[0]


def last_close_on_or_before(opt_ticker: str, day: pd.Timestamp, lookback_days: int = 7) -> float | None:
    bars = option_bars(opt_ticker, day - pd.Timedelta(days=lookback_days), day)
    return float(bars["close"].iloc[-1]) if len(bars) else None


def locate_spot(chain: pd.DataFrame, day: pd.Timestamp, max_iter: int = 8) -> dict | None:
    near = chain[chain.dte >= 3]
    if near.empty:
        return None
    near = near[near.dte == near.dte.min()]
    strikes = paired_strikes(near)
    if len(strikes) < 3:
        return None
    T = near.dte.iloc[0] / 365
    k, tried, est = float(np.median(strikes)), set(), None
    k = strikes[np.abs(strikes - k).argmin()]
    for _ in range(max_iter):
        tried.add(k)
        c = last_close_on_or_before(contract(near, k, "call"), day)
        p = last_close_on_or_before(contract(near, k, "put"), day)
        if c is None or p is None:
            rest = [s for s in strikes if s not in tried]
            if not rest:
                break
            k = rest[int(np.abs(np.array(rest) - k).argmin())]
            continue
        est = k * np.exp(-RISK_FREE * T) + c - p
        k_new = strikes[np.abs(strikes - est).argmin()]
        if k_new == k or k_new in tried:
            break
        k = k_new
    if est is None:
        return None
    return {"spot": float(est), "strike": float(k), "expiry": near.expiration_date.iloc[0], "dte": int(near.dte.iloc[0])}


def pick_expiry(chain: pd.DataFrame, lo: int, hi: int, target: int) -> pd.Timestamp | None:
    cand = chain[(chain.dte >= lo) & (chain.dte <= hi)]
    if cand.empty:
        return None
    dte_of = cand.groupby("expiration_date")["dte"].first()
    ok = [x for x, g in cand.groupby("expiration_date") if len(paired_strikes(g)) >= 3]
    if not ok:
        return None
    return min(ok, key=lambda x: abs(dte_of[x] - target))


def select_strikes(e: pd.DataFrame, spot: float, otm_pcts: list[float]) -> dict[str, float] | None:
    both = paired_strikes(e)
    both = both[(both >= spot * (1 - STRIKE_WINDOW)) & (both <= spot * (1 + STRIKE_WINDOW))]
    if len(both) == 0:
        return None
    calls = np.sort(e.loc[e.contract_type == "call", "strike_price"].unique())
    puts = np.sort(e.loc[e.contract_type == "put", "strike_price"].unique())
    out = {"K": float(both[np.abs(both - spot).argmin()])}
    for pct in otm_pcts:
        up, dn = calls[calls >= spot * (1 + pct)], puts[puts <= spot * (1 - pct)]
        out[f"U{pct}"] = float(up.min()) if len(up) else float(calls.max())
        out[f"L{pct}"] = float(dn.max()) if len(dn) else float(puts.min())
    return out


@dataclass
class Leg:
    ticker: str
    kind: str
    strike: float
    bars: pd.DataFrame

    def mark(self, day: pd.Timestamp) -> float:
        b = self.bars.loc[: pd.Timestamp(day)]
        if b.empty or sessions_between(b.index[-1], day) > MAX_STALE_SESSIONS:
            return np.nan
        return float(b["close"].iloc[-1])

    def volume_on(self, day: pd.Timestamp) -> float:
        return float(self.bars["volume"].get(pd.Timestamp(day), 0.0))


@dataclass
class PricedEvent:
    ticker: str
    event_date: pd.Timestamp
    t_pre: pd.Timestamp
    t_0: pd.Timestamp
    bucket: str
    expiry: pd.Timestamp
    expiry_session: pd.Timestamp
    spot_pre: float
    strikes: dict
    legs: dict

    def marks(self, day) -> dict[str, float]:
        return {name: leg.mark(day) for name, leg in self.legs.items()}

    def synthetic_spot(self, day, m: dict | None = None) -> float:
        m = m if m is not None else self.marks(day)
        T = max((self.expiry - pd.Timestamp(day)).days, 0) / 365
        return self.strikes["K"] * np.exp(-RISK_FREE * T) + m["C_K"] - m["P_K"]


def price_event(ticker: str, t_pre: pd.Timestamp, t_0: pd.Timestamp, event_date: pd.Timestamp,
                buckets: dict, otm_pcts: list[float]) -> tuple[list[PricedEvent], list[str]]:
    dte_hi = max(b[1] for b in buckets.values())
    chain = fetch_chain(ticker, t_pre, 2, dte_hi)
    if chain.empty:
        return [], ["no option chain as of the pre-event session"]
    loc = locate_spot(chain, t_pre)
    if loc is None:
        return [], ["could not recover spot from the chain (no liquid near-dated pair)"]
    priced, notes = [], []
    for name, (lo, hi, target) in buckets.items():
        expiry = pick_expiry(chain, lo, hi, target)
        if expiry is None:
            notes.append(f"{name}: no expiry {lo}-{hi} days out")
            continue
        e = chain[chain.expiration_date == expiry]
        strikes = select_strikes(e, loc["spot"], otm_pcts)
        if strikes is None:
            notes.append(f"{name}: no paired strikes near spot")
            continue
        wanted = {"C_K": ("call", strikes["K"]), "P_K": ("put", strikes["K"])}
        for pct in otm_pcts:
            wanted[f"C_U{pct}"] = ("call", strikes[f"U{pct}"])
            wanted[f"P_L{pct}"] = ("put", strikes[f"L{pct}"])
        legs = {}
        for key, (kind, k) in wanted.items():
            tk = contract(e, k, kind)
            legs[key] = Leg(tk, kind, k, option_bars(tk, t_pre - pd.Timedelta(days=10), expiry))
        pe = PricedEvent(ticker, event_date, t_pre, t_0, name, expiry, CAL[CAL.searchsorted(expiry, side="right") - 1],
                         loc["spot"], strikes, legs)
        if np.isnan(pe.legs["C_K"].mark(t_pre)) or np.isnan(pe.legs["P_K"].mark(t_pre)):
            notes.append(f"{name}: ATM pair did not trade on or near the pre-event session")
            continue
        priced.append(pe)
    return priced, notes


def price_many(keys: list[tuple], buckets: dict, otm_pcts: list[float], workers: int = 12,
               label: str = "pricing") -> tuple[dict, pd.DataFrame]:
    """CHANGED: price unique (ticker, t_pre, t_0, event_date) keys in parallel. Returns key -> [PricedEvent]."""
    out, drops, t0 = {}, [], time.time()
    with ThreadPoolExecutor(workers) as pool:
        futs = {pool.submit(price_event, k[0], k[1], k[2], k[3], buckets, otm_pcts): k for k in keys}
        for n, f in enumerate(as_completed(futs), 1):
            k = futs[f]
            try:
                got, notes = f.result()
            except Exception as exc:                         # one bad event must not kill a long scan
                got, notes = [], [f"error: {type(exc).__name__}: {exc}"[:200]]
            out[k] = got
            drops += [(k[0], k[2], note) for note in notes]
            if n % 100 == 0 or n == len(keys):
                print(f"  {label}: {n}/{len(keys)} keys, {time.time() - t0:.0f}s", flush=True)
    return out, pd.DataFrame(drops, columns=["ticker", "t_0", "reason"])


# ---- 6 · The P&L engine ----------------------------------------------------------------------------
def strategy_pnl(m_e: dict, m_x: dict, S_e: float, S_x: float, otm: float) -> dict[str, float]:
    dS = S_x - S_e
    dC_U = m_x[f"C_U{otm}"] - m_e[f"C_U{otm}"]
    dP_L = m_x[f"P_L{otm}"] - m_e[f"P_L{otm}"]
    dC_K = m_x["C_K"] - m_e["C_K"]
    return {
        "stock":            dS / S_e,
        "long_call":        dC_K / S_e,
        "covered_call":     (dS - dC_U) / S_e,
        "protective_put":   (dS + dP_L) / S_e,
        "collar":           (dS + dP_L - dC_U) / S_e,
        "cash_secured_put": (-dP_L) / S_e,
    }


def evaluate(priced: list[PricedEvent], otm_pcts: list[float]) -> pd.DataFrame:
    """One row per (event, bucket, entry, OTM level, horizon) with every strategy's P&L per $1 spot."""
    rows = []
    for pe in priced:
        i0 = CAL.get_loc(pe.t_0)
        exits = {0: pe.t_0}
        exits.update({h: CAL[i0 + h] for h in HORIZONS if i0 + h < len(CAL) and CAL[i0 + h] <= pe.expiry_session})
        exits["exp"] = pe.expiry_session
        for entry, e_day in (("pre", pe.t_pre), ("post", pe.t_0)):
            m_e = pe.marks(e_day)
            S_e = pe.synthetic_spot(e_day, m_e)
            if np.isnan(S_e):
                continue
            implied = (m_e["C_K"] + m_e["P_K"]) / S_e
            dte_sessions = sessions_between(e_day, pe.expiry_session)
            for h, x_day in exits.items():
                if x_day > LAST_SESSION:
                    continue
                m_x = pe.marks(x_day)
                S_x = pe.synthetic_spot(x_day, m_x)
                held = sessions_between(e_day, x_day)
                base = {"ticker": pe.ticker, "event_date": pe.event_date, "t_pre": pe.t_pre, "t_0": pe.t_0,
                        "bucket": pe.bucket, "expiry": pe.expiry, "entry": entry, "entry_date": e_day, "horizon": h,
                        "exit_date": x_day, "sessions_held": held, "dte_sessions": dte_sessions,
                        "S_entry": S_e, "S_exit": S_x, "realized": S_x / S_e - 1, "implied_move": implied,
                        "implied_scaled": implied * np.sqrt(held / dte_sessions) if dte_sessions else np.nan}
                for otm in otm_pcts:
                    # CHANGED: entry premiums (per $1 spot) and volumes of the legs, for costs and capacity.
                    extra = {"otm": otm,
                             "prem_CK": m_e["C_K"] / S_e, "prem_PK": m_e["P_K"] / S_e,
                             "prem_CU": m_e[f"C_U{otm}"] / S_e, "prem_PL": m_e[f"P_L{otm}"] / S_e,
                             "vol_CU": pe.legs[f"C_U{otm}"].volume_on(e_day), "vol_PL": pe.legs[f"P_L{otm}"].volume_on(e_day),
                             "vol_CK": pe.legs["C_K"].volume_on(e_day)}
                    rows.append(dict(base, **extra, **strategy_pnl(m_e, m_x, S_e, S_x, otm)))
    res = pd.DataFrame(rows)
    if not res.empty:
        res["ratio"] = res["realized"].abs() / res["implied_scaled"]
    return res


# ---- Costs -----------------------------------------------------------------------------------------
COST_HAIRCUT = 0.05      # the notebook's assumption: 5% of each option premium paid to get in, 5% to get out
STOCK_COST = 0.0002      # 1 bp each way for real shares in a top-100 name (the stock leg would be real shares)
OPTION_LEGS = {"stock": [], "long_call": ["prem_CK"], "covered_call": ["prem_CU"], "protective_put": ["prem_PL"],
               "collar": ["prem_CU", "prem_PL"], "cash_secured_put": ["prem_PL"]}
OWNS_STOCK = {"stock", "covered_call", "protective_put", "collar"}


def round_trip_cost(res: pd.DataFrame, strategy: str, haircut: float = COST_HAIRCUT) -> pd.Series:
    """Round-trip cost per $1 spot, the notebook's convention (2 × haircut × entry premium) plus shares."""
    c = pd.Series(0.0, index=res.index)
    for leg in OPTION_LEGS[strategy]:
        c = c + res[leg].abs() * 2 * haircut
    return c + (STOCK_COST if strategy in OWNS_STOCK else 0.0)
