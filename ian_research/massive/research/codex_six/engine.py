"""Frozen six-idea research: historical quotes, never 2026 outcomes.

Run from repo root with massive/.venv/bin/python. Secrets remain in the existing
Massive client; requests only target its authenticated API. Raw data is ignored.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import threading

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
_original_path = sys.path.copy()
sys.path.insert(0, str(HERE.parent / 'codex_three'))
import backtest as old
from data import disclosures
sys.path[:] = _original_path

K = old.base
CAL = K.CAL
CACHE = ROOT / '.massive_cache' / 'codex_six'
CACHE.mkdir(exist_ok=True)
START, END = pd.Timestamp('2024-01-01'), pd.Timestamp('2025-12-31')
HALF_DAYS = {'2024-07-03','2024-11-29','2024-12-24','2025-07-03','2025-11-28','2025-12-24'}
SIGNALS = ['governance','compensation','duration','guidance','noncash','buried']
SECTORS = {}
for sector, tickers in {
    'financial':'AIG AXP BAC BK BLK BRK.B C COF GS JPM MA MET MS SCHW USB V WFC',
    'technology':'AAPL ACN ADBE AMD AVGO CRM CSCO IBM INTC INTU MSFT NOW NVDA ORCL PLTR QCOM TXN',
    'communication':'CHTR CMCSA GOOGL META NFLX T TMUS VZ',
    'consumer_discretionary':'AMZN BKNG FDX GM HD LOW MCD NKE SBUX TGT TSLA UBER',
    'consumer_staples':'CL COST KO MDLZ MO PEP PG PM WMT',
    'health':'ABBV ABT AMGN BMY CVS DHR GILD ISRG JNJ LLY MDT MRK PFE TMO UNH',
    'industrial':'BA CAT DE EMR GD GE HON LMT MMM RTX UNP UPS',
    'energy':'COP CVX XOM', 'utility':'DUK NEE SO', 'other':'AMT DIS LIN'
}.items():
    SECTORS.update({t:sector for t in tickers.split()})


def save(path, value):
    temporary=path.with_suffix(path.suffix+f'.{os.getpid()}.{threading.get_ident()}.tmp')
    temporary.write_text(json.dumps(old.clean(value), indent=2))
    os.replace(temporary,path)


def cutoff(day):
    day = pd.Timestamp(day)
    if day < START or day > END:
        raise ValueError('Historical quote outside 2024-25 refused')
    hour = 13 if str(day.date()) in HALF_DAYS else 16
    return (day.tz_localize('America/New_York') + pd.Timedelta(hours=hour, minutes=-5)).tz_convert('UTC')


def validate_quote(q, at):
    if not q or 'sip_timestamp' not in q:
        return None
    ts = pd.Timestamp(q['sip_timestamp'], unit='ns', tz='UTC')
    age = (at-ts).total_seconds()
    bid, ask = q.get('bid_price'), q.get('ask_price')
    if not 0 <= age <= 300 or bid is None or ask is None or not 0 <= bid <= ask or ask <= 0:
        return None
    if q.get('bid_size',0) < 1 or q.get('ask_size',0) < 1:
        return None
    return dict(bid=float(bid),ask=float(ask),mid=(bid+ask)/2,
                bid_size=q['bid_size'],ask_size=q['ask_size'],timestamp=int(q['sip_timestamp']),age_seconds=age)


@lru_cache(maxsize=100000)
def quote(contract, day):
    at = cutoff(day)
    result = K.api_get('/v3/quotes/'+contract, {'timestamp.lte':at.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    'order':'desc','sort':'timestamp','limit':1})
    rows = result.get('results') or []
    return validate_quote(rows[0],at) if rows else None


def simultaneous(quotes):
    return bool(quotes) and all(quotes.values()) and (
        max(q['timestamp'] for q in quotes.values())-min(q['timestamp'] for q in quotes.values())) <= 300e9


def cdf(x):
    return (1+math.erf(x/math.sqrt(2)))/2


def bs_price(s,k,t,v,kind,r=.04):
    if min(s,k,t,v)<=0:return float('nan')
    d1=(math.log(s/k)+(r+.5*v*v)*t)/(v*math.sqrt(t))
    d2=d1-v*math.sqrt(t)
    call=s*cdf(d1)-k*math.exp(-r*t)*cdf(d2)
    return call if kind=='call' else call-s+k*math.exp(-r*t)


def iv(price,s,k,t,kind):
    if min(price,s,k,t)<=0:return None
    lo,hi=.0001,5.
    if not bs_price(s,k,t,lo,kind)<=price<=bs_price(s,k,t,hi,kind):return None
    for _ in range(60):
        mid=(lo+hi)/2
        if bs_price(s,k,t,mid,kind)<price:lo=mid
        else:hi=mid
    return (lo+hi)/2


def spot(strike,expiry,day,qs):
    if not simultaneous({k:qs.get(k) for k in ['C_K','P_K']}):return None
    return strike*math.exp(-.04*max((pd.Timestamp(expiry)-pd.Timestamp(day)).days,0)/365)+qs['C_K']['mid']-qs['P_K']['mid']


def locate_quote_spot(chain, pre):
    # The old trade-based search supplies only a search starting point. Actual
    # strike selection uses fresh pre-event quotes, never that daily last trade.
    seed = old.locate_pre_spot(chain,pre)
    expiries=sorted(chain.loc[(chain.dte>=3)&(chain.dte<=45),'expiration_date'].unique())[:3]
    for expiry in expiries:
        e=chain[chain.expiration_date==expiry]
        strikes=K.paired_strikes(e)
        if len(strikes)<3:continue
        center=seed['spot'] if seed else float(np.median(strikes))
        candidates=sorted(strikes,key=lambda k:abs(k-center))[:6]
        for k in candidates:
            qs={n:quote(K.contract(e,k,kind),str(pre.date())) for n,kind in [('C_K','call'),('P_K','put')]}
            value=spot(k,expiry,pre,qs)
            if value is None or value<=0:continue
            nearest=float(strikes[np.abs(strikes-value).argmin()])
            refined={n:quote(K.contract(e,nearest,kind),str(pre.date())) for n,kind in [('C_K','call'),('P_K','put')]}
            val2=spot(nearest,expiry,pre,refined)
            if val2 is not None and val2>0:return val2
            return value
    return None


def panel(ticker, day, sensitivity=False):
    ident=hashlib.sha256(f'v1:{ticker}:{day}:{sensitivity}'.encode()).hexdigest()
    path=CACHE/('panel_'+ident+'.json')
    if path.exists():return json.loads(path.read_text())
    day=pd.Timestamp(day); pre=K.session_before(day); decision=K.session_after(day)
    out=dict(ticker=ticker,date=str(day.date()),pre=str(pre.date()),decision=str(decision.date()),buckets={},drops=[])
    if pre<START or decision>END:return out
    chain=old.standard_chain(ticker,pre,2,180)
    if chain.empty:
        out['drops'].append('No historical standard option chain');return out
    s=locate_quote_spot(chain,pre)
    if s is None:
        out['drops'].append('No fresh pre-event paired quotes for stock proxy');return out
    out['spot_pre']=s
    for bucket in (['1m','2m','3-6m'] if sensitivity else ['1m','3-6m']):
        expiry=K.pick_expiry(chain,*K.EXPIRY_BUCKETS[bucket])
        if expiry is None:continue
        e=chain[chain.expiration_date==expiry]
        otms=[.03,.05,.10] if sensitivity else [.05]
        strikes=K.select_strikes(e,s,otms)
        if not strikes:continue
        wanted={'C_K':('call',strikes['K']),'P_K':('put',strikes['K'])}
        for pct in otms:
            if strikes[f'L{pct}']>s*(1-pct)+1e-8 or strikes[f'U{pct}']<s*(1+pct)-1e-8:continue
            wanted[f'P_L{pct}']=('put',strikes[f'L{pct}'])
            wanted[f'C_U{pct}']=('call',strikes[f'U{pct}'])
        contracts={name:K.contract(e,k,kind) for name,(kind,k) in wanted.items()}
        exp_session=CAL[CAL.searchsorted(expiry,side='right')-1]
        dates={pre,decision}
        # The near bucket is needed only for the duration signal in primary run.
        traded=sensitivity or bucket=='3-6m'
        if traded:
            for delay in ([1,2,3] if sensitivity else [2]):
                entry=CAL[CAL.searchsorted(day,side='right')+delay-1]
                dates.add(entry)
                dates.update(CAL[CAL.get_loc(entry)+h] for h in K.HORIZONS
                             if CAL[CAL.get_loc(entry)+h]<=exp_session)
            dates.add(exp_session)
        qs={}
        for d in sorted(dates):
            if d>END or d>exp_session:continue
            qs[str(d.date())]={name:quote(c,str(d.date())) for name,c in contracts.items()}
        out['buckets'][bucket]=dict(expiry=str(expiry.date()),expiry_session=str(exp_session.date()),
                 strikes=strikes,contracts=contracts,quotes=qs)
    save(path,out)
    return out


def vol_features(p):
    result={}
    for bucket in ['1m','3-6m']:
        b=p.get('buckets',{}).get(bucket)
        if not b:continue
        for label,date in [('pre',p['pre']),('decision',p['decision'])]:
            qs=b['quotes'].get(date,{})
            s=spot(b['strikes']['K'],b['expiry'],date,qs)
            if s is None or s<=0:continue
            t=(pd.Timestamp(b['expiry'])-pd.Timestamp(date)).days/365
            for leg,kind in [('P_K','put'),('P_L0.05','put')]:
                q=qs.get(leg)
                if not q:continue
                k=b['strikes']['K'] if leg=='P_K' else b['strikes']['L0.05']
                value=iv(q['mid'],s,k,t,kind)
                if value is not None:result[f'{bucket}_{label}_{leg}_iv']=value
    for bucket in ['1m','3-6m']:
        a,b=f'{bucket}_pre_P_K_iv',f'{bucket}_decision_P_K_iv'
        if a in result and b in result:result[bucket+'_change']=result[b]-result[a]
    a,b='3-6m_decision_P_L0.05_iv','3-6m_decision_P_K_iv'
    if a in result and b in result:result['downside_skew']=result[a]-result[b]
    return result


def weights(strategy,otm):
    if strategy=='cash_secured_put':return {f'P_L{otm}':-1}
    w={'C_K':1,'P_K':-1,f'P_L{otm}':1}
    if strategy=='collar':w[f'C_U{otm}']=-1
    elif strategy!='protective_put':raise ValueError(strategy)
    return w


def leg_pnl(w,qe,qx,stress=0):
    value=0
    for name,n in w.items():
        enter=qe[name]['ask' if n>0 else 'bid']
        leave=qx[name]['bid' if n>0 else 'ask']
        value+=n*(leave-enter)-abs(n)*(.013+stress*(abs(enter)+abs(leave)))
    return value


def evaluate(p,event,role,sensitivity=False):
    rows=[]
    for bucket,b in p.get('buckets',{}).items():
        if not sensitivity and bucket!='3-6m':continue
        for delay in ([1,2,3] if sensitivity else [2]):
            # Price-conditioned trades cannot execute before their decision data.
            if event['signal'] in {'duration','noncash'} and delay<2:continue
            entry=CAL[CAL.searchsorted(pd.Timestamp(p['date']),side='right')+delay-1]
            if entry>END or entry>=pd.Timestamp(b['expiry_session']):continue
            ed=str(entry.date()); qe=b['quotes'].get(ed,{})
            s=spot(b['strikes']['K'],b['expiry'],entry,qe)
            if s is None or s<=0:continue
            for otm in ([.03,.05,.10] if sensitivity else [.05]):
                if b['strikes'].get(f'L{otm}',float('inf'))>p['spot_pre']*(1-otm)+1e-8:continue
                if event['strategy']=='collar' and b['strikes'].get(f'U{otm}',0)<p['spot_pre']*(1+otm)-1e-8:continue
                w=weights(event['strategy'],otm)
                if not simultaneous({k:qe.get(k) for k in set(w)|{'C_K','P_K'}}):continue
                exits={str(h):CAL[CAL.get_loc(entry)+h] for h in K.HORIZONS
                       if CAL[CAL.get_loc(entry)+h]<=pd.Timestamp(b['expiry_session'])}
                exits['exp']=pd.Timestamp(b['expiry_session'])
                for h,exit_day in exits.items():
                    if exit_day>END:continue
                    qx=b['quotes'].get(str(exit_day.date()),{})
                    if not simultaneous({k:qx.get(k) for k in w}):continue
                    cash=0
                    if event['strategy']!='cash_secured_put':
                        cash=b['strikes']['K']*(math.exp(-.04*max((pd.Timestamp(b['expiry'])-exit_day).days,0)/365)
                             -math.exp(-.04*(pd.Timestamp(b['expiry'])-entry).days/365))
                    overlay={k:v for k,v in w.items() if k not in {'C_K','P_K'}}
                    mid_pnl=sum(v*(qx[k]['mid']-qe[k]['mid']) for k,v in w.items())+cash
                    net=leg_pnl(w,qe,qx)+cash
                    row=dict(signal=event['signal'],event_id=event['id'],event_ticker=event['ticker'],
                         ticker=p['ticker'],source_date=p['date'],filing_date=event['filing_date'],
                         role=role,strategy=event['strategy'],bucket=bucket,delay=delay,otm=otm,horizon=h,
                         entry=ed,exit=str(exit_day.date()),expiry=b['expiry'],spot_proxy=s,
                         net=net/s,mid=mid_pnl/s,stress_net=(leg_pnl(w,qe,qx,.025)+cash)/s,
                         overlay_net=leg_pnl(overlay,qe,qx)/s,
                         collateral_return=net/b['strikes'][f'L{otm}'] if event['strategy']=='cash_secured_put' else None,
                         contracts={k:b['contracts'][k] for k in w},
                         entry_quotes={k:qe[k] for k in w},exit_quotes={k:qx[k] for k in w})
                    # Bare synthetic holding comparator uses the identical dates.
                    stockw={'C_K':1,'P_K':-1}
                    if simultaneous({k:qx.get(k) for k in stockw}):
                        te=(pd.Timestamp(b['expiry'])-entry).days/365
                        tx=max((pd.Timestamp(b['expiry'])-exit_day).days,0)/365
                        stockcarry=b['strikes']['K']*(math.exp(-.04*tx)-math.exp(-.04*te))
                        row['stock_net']=(leg_pnl(stockw,qe,qx)+stockcarry)/s
                    rows.append(row)
    return rows


def load_events(signals):
    events=[]; audit=[]
    for signal in signals:
        path=HERE/(signal+'_events.json')
        if not path.exists():
            audit.append(dict(signal=signal,status='manifest missing'));continue
        payload=json.loads(path.read_text())
        records=payload.get('events',[]) if isinstance(payload,dict) else payload
        previous={}
        for e in sorted(records,key=lambda x:(x['filing_date'],x['ticker'])):
            if e.get('eligible') is False:continue
            e=dict(e,signal=signal,id=signal+':'+e['ticker']+':'+e['filing_date'])
            if not '2024-01-01'<=e['filing_date']<='2025-12-31':raise ValueError('OOS event refused')
            prior=previous.get(e['ticker'])
            if prior is not None and (pd.Timestamp(e['filing_date'])-prior).days<60:
                audit.append(dict(event_id=e['id'],status='60day issuer cooldown'));continue
            events.append(e);previous[e['ticker']]=pd.Timestamp(e['filing_date'])
    return events,audit


def quiet_before(known_sessions,event_index):
    """Gate peer eligibility only uses filings dated through the event date."""
    return all(not event_index-5<=j<=event_index for j in known_sessions)


def controls(events):
    raw=disclosures()
    known={t:sorted({int(CAL.searchsorted(pd.Timestamp(r['filing_date']))) for r in raw if r['ticker']==t}) for t in K.TOP_100}
    result={}
    for e in events:
        day=pd.Timestamp(e['filing_date']);idx=int(CAL.searchsorted(day));ticker=e['ticker']
        quiet=lambda t,i:all(abs(i-j)>5 for j in known.get(t,[]))
        # Gate inputs must never select peers using future filings. Only filings
        # dated through the event date are known by next-session decision time.
        past_quiet=lambda t:quiet_before(known.get(t,[]),idx)
        peers=[t for t in K.TOP_100 if t!=ticker and past_quiet(t)]
        peers.sort(key=lambda t:(SECTORS.get(t)!=SECTORS.get(ticker),hashlib.sha256((e['id']+t).encode()).hexdigest()))
        picked=[dict(ticker=t,date=e['filing_date'],role='peer') for t in peers[:3]]
        same=[]
        for off in [-42,42,-63,63,-84,84,-105,105,-126,126]:
            d=CAL[idx+off]
            if d.year==day.year and START<d<=END and quiet(ticker,idx+off):
                same.append(dict(ticker=ticker,date=str(d.date()),role='issuer'))
            if len(same)==3:break
        picked+=same
        payload=json.loads((HERE/(e['signal']+'_events.json')).read_text())
        family=payload.get('controls',[]) if isinstance(payload,dict) else []
        family=[c for c in family if c.get('ticker') and c.get('filing_date') and
                '2024-01-01'<=c['filing_date']<='2025-12-31' and
                (c['ticker'],c['filing_date'])!=(ticker,e['filing_date'])]
        family.sort(key=lambda c:(c['ticker']!=ticker,abs((pd.Timestamp(c['filing_date'])-day).days),c['ticker']))
        used=set()
        for c in family:
            key=(c['ticker'],c['filing_date'])
            if key in used:continue
            used.add(key)
            picked.append(dict(ticker=key[0],date=key[1],role='family'))
            if len(used)==3:break
        result[e['id']]=picked
    return result


def gate(e,p,peer_panels):
    f=vol_features(p)
    if e['signal']=='duration':
        vals=[vol_features(x).get('3-6m_decision_P_K_iv') for x in peer_panels]
        vals=[v for v in vals if v is not None]
        near=f.get('1m_change');far=f.get('3-6m_change');v=f.get('3-6m_decision_P_K_iv')
        if near is None or far is None or v is None or len(vals)<2:return False,'missing synchronized IV proxies or two peers',f
        b=p.get('buckets',{}).get('3-6m',{})
        end=e.get('risk_end_date')
        if not end:return False,'no explicit risk_end_date',f
        if b.get('expiry','')<end:return False,'chosen far expiry does not cover stated risk',f
        ok=near>=.05 and far<=min(.5*near,.025) and v<=float(np.median(vals))
        f['peer_far_iv_median']=float(np.median(vals))
        return ok,'passes' if ok else 'term-structure price condition fails',f
    if e['signal']=='noncash':
        vals=[vol_features(x).get('downside_skew') for x in peer_panels]
        vals=[v for v in vals if v is not None]
        skew=f.get('downside_skew')
        if skew is None or len(vals)<2:return False,'missing skew proxy or two peers',f
        f['peer_skew_median']=float(np.median(vals))
        ok=skew>=.05 and skew>float(np.median(vals))
        return ok,'passes' if ok else 'downside-insurance richness condition fails',f
    return True,'text-only signal',f


def primary_attrition(p,event):
    b=p.get('buckets',{}).get('3-6m')
    if not b:return ['No selected 3-6m option panel']
    entry=CAL[CAL.searchsorted(pd.Timestamp(p['date']),side='right')+1]
    leave=CAL[CAL.get_loc(entry)+21]
    if leave>END:return ['21-session exit crosses 2025-12-31 cutoff']
    if leave>pd.Timestamp(b['expiry_session']):return ['Option expires before 21-session exit']
    w=weights(event['strategy'],.05)
    reasons=[]
    for label,day,names in [('entry',entry,set(w)|{'C_K','P_K'}),('exit',leave,set(w))]:
        qs=b['quotes'].get(str(day.date()),{})
        missing=[n for n in sorted(names) if not qs.get(n)]
        if missing:reasons.append(label+' missing qualifying fresh positive-size NBBO: '+','.join(missing))
    return reasons


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--signals',nargs='+',default=SIGNALS)
    ap.add_argument('--workers',type=int,default=8);ap.add_argument('--sensitivity',action='store_true')
    args=ap.parse_args();events,audit=load_events(args.signals);cs=controls(events)
    suffix='_sensitivity' if args.sensitivity else ''
    run='_'.join(args.signals)+suffix
    save(HERE/('manifest_'+run+'.json'),dict(spec_sha256=hashlib.sha256((HERE/'spec.json').read_bytes()).hexdigest(),
         engine_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         text_source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for s in args.signals
                             for p in [HERE/(s+'_events.json'),HERE/(s+'_spec.json')] if p.exists()},
         events=events,controls=cs,exclusions=audit))
    frozen_manifest_hash=hashlib.sha256((HERE/('manifest_'+run+'.json')).read_bytes()).hexdigest()
    jobs={(e['ticker'],e['filing_date']) for e in events}
    jobs.update((c['ticker'],c['date']) for v in cs.values() for c in v)
    print('Events',len(events),'unique issuer-date panels',len(jobs),flush=True)
    panels={};start=time.time()
    with ThreadPoolExecutor(args.workers) as pool:
        fs={pool.submit(panel,t,d,args.sensitivity):(t,d) for t,d in sorted(jobs)}
        for i,future in enumerate(as_completed(fs),1):
            key=fs[future]
            try:panels[key]=future.result()
            except Exception as ex:
                panels[key]=dict(ticker=key[0],date=key[1],buckets={},drops=['request or pricing error: '+type(ex).__name__])
            if i%10==0 or i==len(jobs):print('Priced',i,'/',len(jobs),'elapsed',round(time.time()-start),flush=True)
    rows=[];gate_audit=[]
    for e in events:
        p=panels[(e['ticker'],e['filing_date'])]
        peer_panels=[panels[(c['ticker'],c['date'])] for c in cs[e['id']] if c['role']=='peer']
        ok,reason,features=gate(e,p,peer_panels)
        evrows=evaluate(p,e,'event',args.sensitivity) if ok else []
        gate_audit.append(dict(event_id=e['id'],signal=e['signal'],passed=ok,reason=reason,features=features,
             pricing_drops=p.get('drops',[]),primary_attrition=primary_attrition(p,e),observations=len(evrows),primary_usable=any(r['horizon']=='21' and r['bucket']=='3-6m' and r['delay']==2 and r['otm']==.05 for r in evrows)))
        rows+=evrows
        if ok:
            for c in cs[e['id']]:rows+=evaluate(panels[(c['ticker'],c['date'])],e,c['role'],args.sensitivity)
    save(CACHE/('observations_'+run+'.json'),rows)
    save(HERE/('gates_'+run+'.json'),gate_audit)
    save(HERE/('drops_'+run+'.json'),[dict(ticker=k[0],date=k[1],drops=p.get('drops',[])) for k,p in panels.items() if p.get('drops')])
    save(HERE/('complete_'+run+'.json'),dict(status='complete',manifest_sha256=frozen_manifest_hash,
         observations_sha256=hashlib.sha256((CACHE/('observations_'+run+'.json')).read_bytes()).hexdigest(),
         gates_sha256=hashlib.sha256((HERE/('gates_'+run+'.json')).read_bytes()).hexdigest()))
    print('Completed',len(rows),'observations; gate-passing',sum(x['passed'] for x in gate_audit),
          'primary usable',sum(x['primary_usable'] for x in gate_audit),flush=True)


if __name__=='__main__':main()
