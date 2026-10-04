"""Historical ATM option-implied uncertainty from existing Massive entitlement.

This module obtains features only. It never evaluates subsequent stock returns.
Quotes, not last trades, are observed at 15:55 ET (12:55 on early-close days).
The 30-calendar-day volatility interpolates total variance from the two nearest
listed expiries bracketing 30 days within 21..45 days. Each maturity uses an ATM
call/put pair and a parity-implied forward, then inverts Black's option formula.
US equity options are American: this is an explicitly approximate quote-implied
volatility, not a vendor or OptionMetrics volatility surface. Rate is fixed 4%;
the paired forward absorbs much of dividends/carry but not early-exercise premia.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as daytime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
from zoneinfo import ZoneInfo

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = HERE / "options_cache"
EXISTING_CACHE = ROOT / "massive" / ".massive_cache"
API = "https://api.massive.com"
RATE = .04
EARLY = {"2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28",
         "2025-12-24", "2026-11-27", "2026-12-24"}
_local = threading.local()


def session():
    if not hasattr(_local, "session"):
        key = os.environ.get("MASSIVE_API_KEY")
        if not key:
            for row in (ROOT / "massive" / ".env").read_text().splitlines():
                if row.startswith("MASSIVE_API_KEY="):
                    key = row.split("=", 1)[1].strip().strip("\"'")
        if not key:
            raise RuntimeError("Missing existing Massive API credential")
        s = requests.Session()
        s.headers["Authorization"] = "Bearer " + key
        _local.session = s
    return _local.session


def get(path, params=None):
    url = path if path.startswith(API + "/") else API + path
    if not url.startswith(API + "/"):
        raise ValueError("Unsupported API host")
    full_url = requests.Request("GET", url, params=params).prepare().url
    digest = hashlib.sha1(full_url.encode()).hexdigest() + ".json"
    for folder in (CACHE, EXISTING_CACHE):
        cachefile = folder / digest
        if cachefile.exists():
            return json.loads(cachefile.read_text())
    for attempt in range(5):
        response = session().get(full_url, timeout=45)
        if response.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(min(2 ** attempt, 10))
    if response.status_code != 200:
        raise RuntimeError(f"Massive historical request status {response.status_code}")
    obj = response.json()
    CACHE.mkdir(exist_ok=True)
    tmp = CACHE / f"{digest}.{threading.get_ident()}.tmp"
    tmp.write_text(json.dumps(obj))
    os.replace(tmp, CACHE / digest)
    return obj


def cutoff(day: str):
    hour = 12 if day in EARLY else 15
    return datetime.combine(date.fromisoformat(day), daytime(hour, 55), ZoneInfo("America/New_York"))


def quote(ticker, at, maximum_age=60):
    payload = get("/v3/quotes/" + ticker, {
        "timestamp.lte": at.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "order": "desc", "sort": "timestamp", "limit": 1})
    rows = payload.get("results") or []
    if not rows:
        return None
    q = rows[0]
    age = at.timestamp() - q["sip_timestamp"] / 1e9
    bid, ask = q.get("bid_price", -1), q.get("ask_price", -1)
    if not (0 <= age <= maximum_age and 0 < bid <= ask
            and q.get("bid_size", 0) > 0 and q.get("ask_size", 0) > 0):
        return None
    mid = (bid + ask) / 2
    return {"bid": bid, "ask": ask, "mid": mid, "spread_fraction": (ask-bid)/mid,
            "bid_size": q["bid_size"], "ask_size": q["ask_size"],
            "timestamp_ns": q["sip_timestamp"], "age_seconds": age}


def first_stock_quote(ticker, day, at=None):
    """First valid NBBO at/after specified time, by SIP time; no spread filter.

    The normal close snapshot uses [15:55,16:00), early closes [12:55,13:00).
    Displayed stock sizes are shares per Massive's stocks quotes documentation.
    This is a quote-based hypothetical fill, not a guaranteed order execution.
    """
    at = cutoff(day) if at is None else at
    session_close=cutoff(day)+timedelta(minutes=5)
    stop = min(at+timedelta(minutes=5),session_close)
    if at>=stop:
        return None
    payload = get("/v3/quotes/" + ticker, {
        "timestamp.gte": at.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timestamp.lt": stop.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "order": "asc", "sort": "timestamp", "limit": 100})
    while True:
        for q in payload.get("results") or []:
            lag = q["sip_timestamp"]/1e9 - at.timestamp()
            bid,ask=q.get("bid_price",-1),q.get("ask_price",-1)
            if not (0<=lag<(stop-at).total_seconds() and 0<bid<=ask and q.get("bid_size",0)>0 and q.get("ask_size",0)>0):
                continue
            mid=(bid+ask)/2
            return {"ticker": ticker, "date": day, "decision_at": at.isoformat(),
                    "timestamp_ns":q["sip_timestamp"],"delay_seconds":lag,"bid":bid,"ask":ask,
                    "mid":mid,"spread_fraction":(ask-bid)/mid,
                    "bid_size":q["bid_size"],"ask_size":q["ask_size"],"size_unit":"shares"}
        if not payload.get("next_url"):
            return None
        payload=get(payload["next_url"])


def normal_cdf(x):
    return (1 + math.erf(x / math.sqrt(2))) / 2


def black_price(fwd, strike, maturity, vol, kind):
    scale = vol * math.sqrt(maturity)
    d1 = math.log(fwd / strike) / scale + scale / 2
    d2 = d1 - scale
    discount = math.exp(-RATE * maturity)
    call = discount * (fwd * normal_cdf(d1) - strike * normal_cdf(d2))
    return call if kind == "call" else call - discount * (fwd - strike)


def implied_vol(premium, fwd, strike, maturity, kind):
    if min(premium, fwd, strike, maturity) <= 0:
        return None
    low, high = .0001, 5.
    if not black_price(fwd,strike,maturity,low,kind) <= premium <= black_price(fwd,strike,maturity,high,kind):
        return None
    for _ in range(60):
        middle = (low + high) / 2
        if black_price(fwd,strike,maturity,middle,kind) < premium:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def feature(ticker, signal_date):
    """Return quote-derived IV and its full provenance; missingness is explicit."""
    at = cutoff(signal_date)
    out = {"ticker": ticker, "signal_date": signal_date, "observed_at": at.isoformat(),
           "iv30": None, "method": "ATM parity-forward Black IV; 30D total variance interpolation",
           "risk_free_rate": RATE, "max_quote_age_seconds": 60}
    stock = quote(ticker, at, maximum_age=60)
    if not stock:
        return out | {"drop_reason": "No valid equity quote within 60 seconds"}
    out["stock_quote"] = stock
    spot = stock["mid"]
    day = date.fromisoformat(signal_date)
    params = {"underlying_ticker": ticker, "as_of": signal_date,
              "expiration_date.gte": str(day+timedelta(days=21)),
              "expiration_date.lte": str(day+timedelta(days=45)),
              "strike_price.gte": spot * .9, "strike_price.lte": spot * 1.1, "limit": 1000}
    payload = get("/v3/reference/options/contracts", params)
    chain = list(payload.get("results") or [])
    while payload.get("next_url"):
        payload = get(payload["next_url"])
        chain.extend(payload.get("results") or [])
    chain = [r for r in chain if r.get("shares_per_contract") == 100
             and not r.get("additional_underlyings") and r.get("contract_type") in ("call", "put")]
    expiries = sorted({r["expiration_date"] for r in chain})
    times = {exp: (datetime.combine(date.fromisoformat(exp), daytime(16), ZoneInfo("America/New_York"))-at).total_seconds()/86400
             for exp in expiries}
    lower = [exp for exp in expiries if times[exp] <= 30]
    upper = [exp for exp in expiries if times[exp] >= 30]
    if not lower or not upper:
        return out | {"drop_reason": "No expiries bracketing 30 days within 21..45D"}
    selected = sorted({max(lower), min(upper)})
    surfaces = []
    for exp in selected:
        contracts = {}
        for row in chain:
            if row["expiration_date"] == exp:
                contracts.setdefault(row["strike_price"], {})[row["contract_type"]] = row["ticker"]
        paired = sorted([k for k,pair in contracts.items() if len(pair)==2], key=lambda k:abs(k-spot))
        observation = None
        # Only nearest paired strike: do not introduce a liquidity-driven strike search.
        for strike in paired[:1]:
            cq = quote(contracts[strike]["call"], at)
            pq = quote(contracts[strike]["put"], at)
            if not cq or not pq or max(cq["spread_fraction"], pq["spread_fraction"]) > .25:
                continue
            maturity = times[exp] / 365
            discount = math.exp(-RATE * maturity)
            fwd = strike + (cq["mid"] - pq["mid"]) / discount
            if not .9 <= fwd/spot <= 1.1 or abs(strike/fwd-1) > .05:
                continue
            kind = "call" if strike >= fwd else "put"
            iv = implied_vol((cq if kind=="call" else pq)["mid"],fwd,strike,maturity,kind)
            if iv is None:
                continue
            observation = {"expiry": exp, "days_to_expiry": times[exp], "strike": strike,
                           "forward": fwd, "iv": iv, "option_type": kind,
                           "call_contract": contracts[strike]["call"], "put_contract": contracts[strike]["put"],
                           "call_quote": cq, "put_quote": pq}
        if observation is None:
            return out | {"drop_reason": "Missing/faulty/too-wide ATM option quote", "expiry_missing": exp}
        surfaces.append(observation)
    out["maturities"] = surfaces
    if len(surfaces)==1:
        variance30 = surfaces[0]["iv"]**2
    else:
        first,second = surfaces
        d1,d2 = first["days_to_expiry"],second["days_to_expiry"]
        weight=(30-d1)/(d2-d1)
        variance30=((1-weight)*first["iv"]**2*d1 + weight*second["iv"]**2*d2)/30
    out["iv30"] = math.sqrt(variance30)
    out["max_actual_quote_age_seconds"] = max(q["age_seconds"] for row in surfaces
                                               for q in (row["call_quote"],row["put_quote"]))
    out["max_option_spread_fraction"] = max(q["spread_fraction"] for row in surfaces
                                            for q in (row["call_quote"],row["put_quote"]))
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input", help="JSON list with ticker and signal_date")
    parser.add_argument("--output",default=str(HERE/"options_features.json"))
    parser.add_argument("--ticker",default="AAPL")
    parser.add_argument("--date",default="2025-01-02")
    parser.add_argument("--workers",type=int,default=6)
    args=parser.parse_args()
    rows=json.loads(Path(args.input).read_text()) if args.input else [{"ticker":args.ticker,"signal_date":args.date}]
    out=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending={pool.submit(feature,row["ticker"],row["signal_date"]):row for row in rows}
        for future in as_completed(pending):
            row=pending[future]
            try:
                out.append(future.result())
            except Exception as exc:
                out.append({"ticker":row["ticker"],"signal_date":row["signal_date"],"iv30":None,
                            "drop_reason":type(exc).__name__+": "+str(exc)[:150]})
            if len(out)%25==0 or len(out)==len(rows):
                print(f"Options features {len(out)}/{len(rows)}; valid {sum(r.get('iv30') is not None for r in out)}",flush=True)
                Path(args.output).write_text(json.dumps(out,indent=2))


if __name__=="__main__":
    main()
