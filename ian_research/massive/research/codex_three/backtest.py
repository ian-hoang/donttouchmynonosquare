"""Conservative, development-only event study for the three frozen hypotheses.

Uses existing Massive cache and REST client, without modifying shared harness.
Trade bars are marks, not executable bid/ask quotes. Strict freshness can cause
substantial attrition, reported explicitly. Never downloads 2026 outcome bars.
"""
import argparse
import concurrent.futures
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
import numpy as np
import pandas as pd

from data import HERE, ROOT, disclosures
sys.path.insert(0,str(ROOT))
import eightk as base

CUTOFF=pd.Timestamp('2025-12-31')
START=pd.Timestamp('2024-01-01')
PRIVATE=ROOT/'.massive_cache'/'codex_three'
PRIVATE.mkdir(exist_ok=True)
CAL=base.CAL
OTMS=[.03,.05,.10]
BUCKETS=base.EXPIRY_BUCKETS
OLD_API=base.api_get
OLD_BARS=base.option_bars
OLD_CHAIN=base.fetch_chain
OLD_LOCATE=base.locate_spot
base.MAX_STALE_SESSIONS=0


def safe_api(path,params=None):
    params=params or {}
    if path.startswith('http') and urlparse(path).hostname!='api.massive.com':
        raise ValueError('Unexpected API host')
    if '/aggs/' in path:
        end=path.split('?')[0].rstrip('/').split('/')[-1]
        if pd.Timestamp(end)>CUTOFF:raise ValueError('OOS outcome request refused')
    if '/filings/' in path:raise ValueError('Live filing downloads disabled; use frozen IS cache')
    if 'as_of' in params and pd.Timestamp(params['as_of'])>CUTOFF:raise ValueError('OOS chain refused')
    return OLD_API(path,params)


def safe_bars(ticker,start,end):
    start=max(pd.Timestamp(start),START)
    end=min(pd.Timestamp(end),CUTOFF)
    if start>end:return pd.DataFrame(columns=['close','volume'],index=pd.DatetimeIndex([]))
    frame=OLD_BARS(ticker,start,end)
    return frame[(frame.close>=0)&(frame.volume>0)]


def fresh_close(ticker,day,lookback_days=7):
    b=safe_bars(ticker,day-pd.Timedelta(days=lookback_days),day)
    return float(b.loc[day,'close']) if day in b.index else None


def standard_chain(ticker,as_of,lo,hi):
    rows=base.api_get_all('/v3/reference/options/contracts',{
      'underlying_ticker':ticker,'as_of':as_of.strftime('%Y-%m-%d'),
      'expiration_date.gte':(as_of+pd.Timedelta(days=lo)).strftime('%Y-%m-%d'),
      'expiration_date.lte':(as_of+pd.Timedelta(days=hi)).strftime('%Y-%m-%d'),'limit':1000})
    rows=[r for r in rows if r.get('shares_per_contract')==100 and not r.get('additional_underlyings')
          and r.get('contract_type') in {'call','put'}]
    c=pd.DataFrame(rows)
    if c.empty:return c
    c=c[['ticker','contract_type','strike_price','expiration_date']].copy()
    c['expiration_date']=pd.to_datetime(c.expiration_date)
    c['dte']=(c.expiration_date-as_of).dt.days
    c['strike_price']=c.strike_price.astype(float)
    return c


base.api_get=safe_api
base.option_bars=safe_bars
base.last_close_on_or_before=fresh_close
base.fetch_chain=standard_chain


def locate_pre_spot(chain,day):
    """Keep starter search, then broaden the pre-event-only search on failure.

    Searching eight adjacent strikes near the chain median can miss the actual
    trading region. The fallback uses a fixed strike grid, without future data.
    """
    existing=OLD_LOCATE(chain,day)
    if existing is not None:return existing
    expiries=sorted(chain.loc[(chain.dte>=3)&(chain.dte<=45),'expiration_date'].unique())[:3]
    for expiry in expiries:
        e=chain[chain.expiration_date==expiry]
        strikes=base.paired_strikes(e)
        if len(strikes)<3:continue
        positions=sorted(set(np.linspace(0,len(strikes)-1,min(17,len(strikes))).round().astype(int)),
                         key=lambda i:abs(i-(len(strikes)-1)/2))
        trial=list(strikes[positions])
        used=set()
        for k in trial:
            if k in used:continue
            used.add(k)
            c=fresh_close(base.contract(e,k,'call'),day)
            p=fresh_close(base.contract(e,k,'put'),day)
            if c is None or p is None:continue
            dte=int(e.dte.iloc[0])
            estimate=float(k*math.exp(-base.RISK_FREE*dte/365)+c-p)
            if not np.isfinite(estimate) or estimate<=0:continue
            nearest=float(strikes[np.abs(strikes-estimate).argmin()])
            # Refine at an actually traded strike nearest the implied spot if possible.
            if nearest!=k:
                cn=fresh_close(base.contract(e,nearest,'call'),day)
                pn=fresh_close(base.contract(e,nearest,'put'),day)
                if cn is not None and pn is not None:
                    estimate=float(nearest*math.exp(-base.RISK_FREE*dte/365)+cn-pn)
                    k=nearest
            return {'spot':estimate,'strike':float(k),'expiry':pd.Timestamp(expiry),'dte':dte}
    return None


def price_selected(ticker,pre,entry,event_date):
    chain=standard_chain(ticker,pre,2,180)
    if chain.empty:return [],['no standard historical chain']
    loc=locate_pre_spot(chain,pre)
    if loc is None:return [],['no same-session near-dated pair found after broadened fixed pre-event search']
    result,notes=[],[]
    for bucket,(lo,hi,target) in BUCKETS.items():
        expiry=base.pick_expiry(chain,lo,hi,target)
        if expiry is None:
            notes.append(bucket+': no expiry in fixed bucket');continue
        e=chain[chain.expiration_date==expiry]
        strikes=base.select_strikes(e,loc['spot'],OTMS)
        if strikes is None:
            notes.append(bucket+': no paired strikes near pre-event proxy');continue
        wanted={'C_K':('call',strikes['K']),'P_K':('put',strikes['K'])}
        for otm in OTMS:
            wanted[f'C_U{otm}']=('call',strikes[f'U{otm}'])
            wanted[f'P_L{otm}']=('put',strikes[f'L{otm}'])
        legs={}
        for name,(kind,k) in wanted.items():
            ticker_option=base.contract(e,k,kind)
            legs[name]=base.Leg(ticker_option,kind,k,safe_bars(ticker_option,pre-pd.Timedelta(days=10),expiry))
        # These selected-expiry prices are needed at actual entry and exit, not
        # at the pre-filing selection date. Strikes used only historical chain
        # metadata and the independently recovered pre-event spot above.
        result.append(base.PricedEvent(ticker,event_date,pre,entry,bucket,expiry,
                      CAL[CAL.searchsorted(expiry,side='right')-1],loc['spot'],strikes,legs))
    return result,notes


def clean(obj):
    if isinstance(obj,dict):return {str(k):clean(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)):return [clean(v) for v in obj]
    if isinstance(obj,(pd.Timestamp,np.datetime64)):return str(pd.Timestamp(obj).date())
    if isinstance(obj,np.integer):return int(obj)
    if isinstance(obj,(float,np.floating)):return float(obj) if np.isfinite(obj) else None
    return obj


def load_events():
    all_events=[]
    for signal,strategy in [('liquidity','cash_secured_put'),('departures','collar'),('credit','long_call')]:
        p=HERE/(signal+'_events.json')
        if not p.exists():continue
        data=json.loads(p.read_text())
        data=data.get('events',[]) if isinstance(data,dict) else data
        for r in data:
            d=r.get('filing_date') or r.get('date')
            if not '2024-01-01'<=d<='2025-12-31':raise ValueError('Event outside IS')
            all_events.append(dict(r,signal=signal,strategy=strategy,filing_date=d,
                                   id=signal+':'+r['ticker']+':'+d))
    return all_events


def choose_controls(events):
    families={'liquidity':{'credit_facility','debt_issuance'},
              'departures':{'ceo_departure','cfo_departure','executive_officer_departure'},
              'credit':{'business_update'}}
    raw=disclosures()
    out=[]
    for event in events:
        day=pd.Timestamp(event['filing_date'])
        i=int(CAL.searchsorted(day,side='left'))
        blocked=[int(CAL.searchsorted(pd.Timestamp(r['filing_date']))) for r in raw
                 if r['ticker']==event['ticker'] and r['tertiary_category'] in families[event['signal']]]
        picked=[]
        for offset in [-42,42,-63,63,-84,84,-105,105,-126,126]:
            j=i+offset
            d=CAL[j]
            if d.year!=day.year or d<START or d>CUTOFF or any(abs(j-b)<=10 for b in blocked):continue
            picked.append(str(d.date()))
            if len(picked)==5:break
        out.append(dict(event,controls=picked))
    return out


def evaluate_one(pe,event,strategy,control_for,source_day):
    rows=[]
    for delay in [1,2,3]:
        index=int(CAL.searchsorted(pd.Timestamp(source_day),side='right'))+delay-1
        entry=CAL[index]
        if entry>CUTOFF or entry>=pe.expiry_session:continue
        exits={h:CAL[index+h] for h in base.HORIZONS if CAL[index+h]<=pe.expiry_session and CAL[index+h]<=CUTOFF}
        if pe.expiry_session<=CUTOFF:exits['exp']=pe.expiry_session
        for otm in OTMS:
            if strategy=='cash_secured_put':weights={f'P_L{otm}':-1}
            elif strategy=='long_call':weights={'C_K':1}
            elif strategy=='collar':weights={'C_K':1,'P_K':-1,f'P_L{otm}':1,f'C_U{otm}':-1}
            else:raise ValueError(strategy)
            # ATM pair is needed only at entry to normalize call/put exposure.
            needed=set(weights)|{'C_K','P_K'}
            me={k:pe.legs[k].mark(entry) for k in needed}
            if any(not np.isfinite(v) for v in me.values()):continue
            if any(pe.legs[k].volume_on(entry)<1 for k in needed):continue
            if any(me[k]<=0 for k in weights):continue
            spot=pe.synthetic_spot(entry,me)
            if not np.isfinite(spot) or spot<=0:continue
            if strategy!='long_call':
                if pe.strikes[f'L{otm}']>=pe.spot_pre:continue
                if strategy=='collar' and pe.strikes[f'U{otm}']<=pe.spot_pre:continue
            for horizon,exit_day in exits.items():
                mx={k:pe.legs[k].mark(exit_day) for k in weights}
                if any(not np.isfinite(v) for v in mx.values()):continue
                if any(pe.legs[k].volume_on(exit_day)<1 for k in weights):continue
                option_pnl=sum(w*(mx[k]-me[k]) for k,w in weights.items())
                cash_carry=0.
                if strategy=='collar':
                    # Fund the strike payment with a bond, so C-P+PV(K) is the
                    # challenge's synthetic-stock approximation. American/dividend
                    # limitations remain explicit; no real-share prices are claimed.
                    te=max((pe.expiry-entry).days,0)/365
                    tx=max((pe.expiry-exit_day).days,0)/365
                    cash_carry=pe.strikes['K']*(math.exp(-base.RISK_FREE*tx)-math.exp(-base.RISK_FREE*te))
                gross=(option_pnl+cash_carry)/spot
                premium_sum=sum(abs(w)*(abs(me[k])+abs(mx[k])) for k,w in weights.items())
                commission=.0065*2*sum(abs(w) for w in weights.values())
                collateral=pe.strikes[f'L{otm}'] if strategy=='cash_secured_put' else me['C_K'] if strategy=='long_call' else spot
                base_row=dict(signal=event['signal'],event_id=event['id'],ticker=event['ticker'],
                    filing_date=event['filing_date'],source_date=source_day,control_for=control_for,
                    role='control' if control_for else 'event',strategy=strategy,bucket=pe.bucket,
                    expiry=str(pe.expiry.date()),entry=str(entry.date()),exit=str(exit_day.date()),
                    delay=delay,otm=otm,horizon=str(horizon),spot_proxy=spot,spot_pre=pe.spot_pre,
                    gross=gross,entry_min_volume=min(pe.legs[k].volume_on(entry) for k in weights),
                    exit_min_volume=min(pe.legs[k].volume_on(exit_day) for k in weights),
                    leg_tickers={k:pe.legs[k].ticker for k in weights},entry_marks={k:me[k] for k in weights},exit_marks=mx,
                    capital_basis='option premium plus entry costs' if strategy=='long_call' else
                                  'strike collateral' if strategy=='cash_secured_put' else 'stock-equivalent notional')
                for haircut in [0.,.025,.05,.10]:
                    costs=(premium_sum*haircut+commission)
                    funded=collateral+(haircut*me['C_K']+.0065 if strategy=='long_call' else 0.)
                    rows.append(dict(base_row,haircut=haircut,costs_per_share=costs,net=(option_pnl+cash_carry-costs)/spot,
                                     return_on_capital=(option_pnl+cash_carry-costs)/funded if funded>0 else None))
    return rows


def primary_price_audit(pe,event,day,role):
    entry=CAL[int(CAL.searchsorted(pd.Timestamp(day),side='right'))+1]
    exit_day=CAL[CAL.get_loc(entry)+21]
    strategy=event['strategy']
    traded={'cash_secured_put':['P_L0.05'],'long_call':['C_K'],
            'collar':['C_K','P_K','P_L0.05','C_U0.05']}[strategy]
    entry_needed=set(traded)|{'C_K','P_K'}
    missing_entry=[k for k in entry_needed if not np.isfinite(pe.legs[k].mark(entry)) or pe.legs[k].volume_on(entry)<1]
    missing_exit=[k for k in traded if not np.isfinite(pe.legs[k].mark(exit_day)) or pe.legs[k].volume_on(exit_day)<1]
    reasons=[]
    if missing_entry:reasons.append('missing same-session entry marks: '+','.join(sorted(missing_entry)))
    if exit_day>CUTOFF:reasons.append('21-session exit beyond development cutoff')
    elif missing_exit:reasons.append('missing same-session exit marks: '+','.join(sorted(missing_exit)))
    if exit_day>pe.expiry_session:reasons.append('contract expires before 21-session exit')
    return dict(event_id=event['id'],ticker=event['ticker'],signal=event['signal'],source_date=day,
                role=role,bucket=pe.bucket,entry=str(entry.date()),exit=str(exit_day.date()),reasons=reasons,
                entry_missing=missing_entry,exit_missing=missing_exit)


def price_request(job):
    ticker,source_day=job
    d=pd.Timestamp(source_day)
    pre=base.session_before(d)
    entry=base.session_after(base.session_after(d))
    if pre<START:return [],['pre-event history outside development window']
    return price_selected(ticker,pre,entry,d)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workers',type=int,default=6)
    parser.add_argument('--signals',nargs='*')
    args=parser.parse_args()
    events=choose_controls(load_events())
    if args.signals:events=[e for e in events if e['signal'] in args.signals]
    stamp=hashlib.sha256((HERE/'spec.json').read_bytes()).hexdigest()
    (HERE/'run_manifest.json').write_text(json.dumps(clean(dict(spec_sha256=stamp,
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),events=events)),indent=2))
    jobs={ (e['ticker'],d) for e in events for d in [e['filing_date']]+e['controls']}
    results,drops={},[]
    start=time.time()
    print('Frozen events',len(events),'unique event/control dates',len(jobs),flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(price_request,j):j for j in sorted(jobs)}
        for n,f in enumerate(concurrent.futures.as_completed(futures),1):
            j=futures[f]
            try:priced,notes=f.result()
            except Exception as error:priced,notes=[],['error '+type(error).__name__]
            results[j]=priced
            drops += [dict(ticker=j[0],date=j[1],reason=note) for note in notes]
            print('Pricing',n,'/',len(jobs),'elapsed',round(time.time()-start),'seconds',flush=True)
    rows=[]
    audits=[]
    for e in events:
        for d in [e['filing_date']]+e['controls']:
            for pe in results.get((e['ticker'],d),[]):
                rows.extend(evaluate_one(pe,e,e['strategy'],e['id'] if d!=e['filing_date'] else None,d))
                if pe.bucket=='3-6m':audits.append(primary_price_audit(pe,e,d,'event' if d==e['filing_date'] else 'control'))
    (PRIVATE/'observations.json').write_text(json.dumps(clean(rows)))
    (HERE/'primary_price_audit.json').write_text(json.dumps(clean(audits),indent=2))
    (HERE/'pricing_drops.json').write_text(json.dumps(clean(drops),indent=2))
    print('Fresh marked observations including sensitivity combinations:',len(rows),flush=True)


if __name__=='__main__':main()
