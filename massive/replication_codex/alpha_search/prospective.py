"""Fixed prospective sector-control experiment. Never tune from returns."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import numpy as np
from .. import data,events,pricing,trading_calendar as cal
from . import client

HERE=Path(__file__).resolve().parent
CACHE=HERE/'cache'
NY=ZoneInfo('America/New_York')
EARLY={'2024-07-03','2024-11-29','2024-12-24',
       '2025-07-03','2025-11-28','2025-12-24','2026-11-27','2026-12-24'}
SECTORS={}
for sector,tickers in {
    'financial':'AIG AXP BAC BK BLK BRK.B C COF GS JPM MA MET MS PYPL SCHW USB V WFC',
    'technology':'AAPL ACN ADBE AMD AVGO CRM CSCO IBM INTC INTU MSFT NOW NVDA ORCL PLTR QCOM TXN',
    'communication':'CHTR CMCSA DIS GOOGL META NFLX T TMUS VZ',
    'consumer_discretionary':'AMZN BKNG GM HD LOW MCD NKE SBUX TSLA',
    'consumer_staples':'CL COST KO MDLZ MO PEP PG PM TGT WMT',
    'health':'ABBV ABT AMGN BMY CVS DHR GILD ISRG JNJ LLY MDT MRK PFE TMO',
    'industrial':'BA CAT DE EMR FDX GD GE HON LMT MMM RTX UBER UNP UPS',
    'energy':'COP CVX XOM','utility':'DUK NEE SO','real_estate':'AMT','materials':'LIN',
}.items():
    SECTORS.update({t:sector for t in tickers.split()})
assert set(SECTORS)==set(events.UNIVERSE)

def cutoff(day):
    day=date.fromisoformat(str(day))
    return datetime.combine(day,time(12,55) if str(day) in EARLY else time(15,55),NY)

def valid_quote(q,at):
    if not q:return None
    ts=q.get('sip_timestamp')
    if ts is None:return None
    try:
        age_ns=int(at.timestamp())*1_000_000_000-int(ts)
        age=age_ns/1e9
        bid=float(q['bid_price']);ask=float(q['ask_price'])
        bs=float(q.get('bid_size',0));az=float(q.get('ask_size',0))
    except (TypeError,KeyError,ValueError,OverflowError):return None
    if not all(math.isfinite(x) for x in (bid,ask,bs,az)):return None
    if not (0<=age_ns<=300_000_000_000 and 0<=bid<=ask and ask>0 and bs>=1 and az>=1):return None
    return dict(bid=bid,ask=ask,mid=(bid+ask)/2,timestamp=int(ts),
                age_seconds=age,bid_size=bs,ask_size=az)

def quote(contract,day):
    at=cutoff(day)
    payload=client.get_json('/v3/quotes/'+contract,{'timestamp.lte':at.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                  'order':'desc','sort':'timestamp','limit':1})
    rows=payload.get('results') or []
    return valid_quote(rows[0],at) if rows else None

def draw_controls(cohort,histories):
    rng=random.Random(1729);out=[]
    for e in sorted(cohort,key=lambda x:(x['filing_date'],x['ticker'])):
        day=date.fromisoformat(e['filing_date']);lo=day-timedelta(days=5)
        eligible=[t for t in sorted(events.UNIVERSE) if t!=e['ticker'] and SECTORS[t]==SECTORS[e['ticker']]
                  and not any(str(lo)<=f<=str(day) for f in histories[t])]
        peers=rng.sample(eligible,min(3,len(eligible)))
        out.append(dict(ticker=e['ticker'],filing_date=e['filing_date'],sector=SECTORS[e['ticker']],
                        eligible=eligible,peers=peers))
    return out

def select_contract(ticker,day,old):
    pre=cal.session_before(cal.session_on_or_after(date.fromisoformat(day)))
    base=dict(ticker=ticker,filing_date=day,t_pre=str(pre),
              entry=str(cal.session_after(cal.session_on_or_after(date.fromisoformat(day)))))
    base['exit']=str(cal.shift_session(date.fromisoformat(base['entry']),10))
    cached=old.get((ticker,day),{})
    keys=('expiry','atm_strike','strike','atm_call','atm_put','sold_call','pre_spot')
    if all(k in cached for k in keys):return {**base,**{k:cached[k] for k in keys},'status':'selected'}
    chain=pricing._chain_by_expiry(client.chain(ticker,pre))
    spot=pricing.estimate_spot(chain,pre,client)
    if spot['spot'] is None:return {**base,'status':'selection_failed','reason':spot['drop_reason']}
    chosen=pricing.select_expiry_and_strikes(chain,pre,spot['spot'])
    if chosen['drop_reason']:return {**base,'status':'selection_failed','reason':chosen['drop_reason']}
    return {**base,**chosen,'pre_spot':spot['spot'],'status':'selected'}

def price_one(ticker,day,old):
    codehash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]
    path=CACHE/'prospective'/f'{codehash}_{ticker}_{day}.json'
    if path.exists():return json.loads(path.read_text())
    out=select_contract(ticker,day,old)
    if out['status']!='selected':data.atomic_json(path,out);return out
    qs={label:quote(out[label],out['entry']) for label in ('atm_call','atm_put','sold_call')}
    out['entry_quotes']=qs
    if not all(qs.values()):out.update(status='entry_unavailable',reason='fresh_entry_quotes')
    else:
        timestamps=[q['timestamp'] for q in qs.values()]
        expiry=date.fromisoformat(out['expiry']);entry=date.fromisoformat(out['entry'])
        s=out['atm_strike']*math.exp(-.04*max((expiry-entry).days,0)/365)+qs['atm_call']['mid']-qs['atm_put']['mid']
        out['entry_spot']=s
        if s<=0 or max(timestamps)-min(timestamps)>300e9:
            out.update(status='entry_unavailable',reason='entry_parity')
        else:
            qx=quote(out['sold_call'],out['exit']);out['exit_quote']=qx
            if not qx:out.update(status='exit_unavailable',reason='fresh_exit_quote')
            else:
                qe=qs['sold_call']
                out.update(status='valid',short_net=(qe['bid']-qx['ask']-.013)/s,
                           long_net=(qx['bid']-qe['ask']-.013)/s,
                           mid_short=(qe['mid']-qx['mid'])/s,
                           roundtrip_cost=((qe['ask']-qe['bid']+qx['ask']-qx['bid'])/2+.013)/s)
    data.atomic_json(path,out);return out

def summarize(values):
    if not values:return {'n':0}
    mean=statistics.mean(values);sd=statistics.stdev(values) if len(values)>1 else None
    return dict(n=len(values),mean=mean,median=statistics.median(values),std=sd,
                win_rate=sum(x>0 for x in values)/len(values),per_trade_sharpe=mean/sd if sd else None)

def interval(rows,field,cluster,reps=10000):
    groups={}
    for r in rows:
        if r.get(field) is None:continue
        k=r['filing_date'][:7] if cluster=='month' else r['filing_date'] if cluster=='date' else r['ticker']
        groups.setdefault(k,[]).append(r[field])
    if len(groups)<2:return None
    vals=list(groups.values());sums=np.array([sum(v) for v in vals]);counts=np.array([len(v) for v in vals])
    rng=np.random.default_rng(1729);idx=rng.integers(0,len(vals),size=(reps,len(vals)))
    means=sums[idx].sum(axis=1)/counts[idx].sum(axis=1)
    return dict(clusters=len(vals),low=float(np.quantile(means,.025)),high=float(np.quantile(means,.975)))

def assemble(draws,priced):
    bykey={(r['ticker'],r['filing_date']):r for r in priced};out=[]
    for d in draws:
        e=bykey[(d['ticker'],d['filing_date'])]
        r={**d,'event_status':e['status'],'event_short_net':e.get('short_net')}
        peers=[bykey[(t,d['filing_date'])] for t in d['peers']]
        admitted=[p for p in peers if p['status'] in ('valid','exit_unavailable')]
        r['entry_admitted_peers']=[p['ticker'] for p in admitted]
        r['peer_statuses']={p['ticker']:p['status'] for p in peers}
        if e['status']=='valid' and admitted and all(p['status']=='valid' for p in admitted):
            peer_short=statistics.mean(p['short_net'] for p in admitted)
            peer_long=statistics.mean(p['long_net'] for p in admitted)
            r.update(sector_gap=e['short_net']-peer_short,peer_short_net=peer_short,
                     pair_net=e['short_net']+peer_long,pair_per_gross_reference=(e['short_net']+peer_long)/2)
        out.append(r)
    return out

def run(workers):
    prior={}
    for name in ('peer_results.json','event_results.json'):
        for r in json.loads((data.CACHE/name).read_text()):prior[(r['ticker'],r['filing_date'])]=r
    cohort=json.loads((data.CACHE/'cohort.json').read_text())['kept']
    histories=json.loads((data.CACHE/'histories.json').read_text())
    draws=draw_controls(cohort,histories)
    manifest=HERE/'prospective_manifest.json'
    new=dict(spec_sha256=hashlib.sha256((HERE/'PROSPECTIVE_SPEC.txt').read_bytes()).hexdigest(),
             code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             created_at=datetime.now(timezone.utc).isoformat(),sectors=SECTORS,
             cohort_count=len(cohort),seed=1729,
             source_sha256={name:hashlib.sha256((data.CACHE/name).read_bytes()).hexdigest()
                            for name in ('cohort.json','histories.json','event_results.json','peer_results.json')})
    if not manifest.exists():data.atomic_json(manifest,new)
    else:
        saved=json.loads(manifest.read_text())
        for key in ('spec_sha256','code_sha256','source_sha256'):
            if saved.get(key)!=new[key]:raise RuntimeError('Frozen manifest mismatch: '+key)
    data.atomic_json(HERE/'prospective_draws.json',draws)
    jobs=sorted({(d['ticker'],d['filing_date']) for d in draws}|{(t,d['filing_date']) for d in draws for t in d['peers']})
    print('Fixed prospective jobs:',len(jobs),'events:',len(draws),flush=True)
    results=[]
    with ThreadPoolExecutor(workers) as pool:
        fs={pool.submit(price_one,t,d,prior):(t,d) for t,d in jobs}
        for i,f in enumerate(as_completed(fs),1):
            t,d=fs[f]
            try:results.append(f.result())
            except Exception as exc:results.append(dict(ticker=t,filing_date=d,status='error',reason=str(exc)))
            if i%25==0:print('Prospective priced',i,'/',len(jobs),flush=True)
    results.sort(key=lambda r:(r['filing_date'],r['ticker']))
    data.atomic_json(HERE/'prospective_prices.json',results)
    if any(r['status']=='error' for r in results):
        print('API/errors remain:',sum(r['status']=='error' for r in results),flush=True)
        return
    rows=assemble(draws,results);data.atomic_json(HERE/'prospective_rows.json',rows)
    summary={}
    for window in ('2024-25','2026'):
        subset=[r for r in rows if events.window(r['filing_date'])==window]
        out={'event_count':len(subset),'event_statuses':{s:sum(r['event_status']==s for r in subset) for s in sorted({r['event_status'] for r in subset})}}
        for field in ('event_short_net','sector_gap','pair_net','pair_per_gross_reference'):
            valid=[r for r in subset if r.get(field) is not None]
            o=summarize([r[field] for r in valid])
            o['date_cluster_95']=interval(valid,field,'date')
            o['month_block_95']=interval(valid,field,'month')
            o['issuer_cluster_95']=interval(valid,field,'issuer')
            loo=[statistics.mean(r[field] for r in valid if r['ticker']!=t) for t in {r['ticker'] for r in valid} if any(r['ticker']!=t for r in valid)]
            o['leave_one_issuer_out_mean_range']=[min(loo),max(loo)] if loo else None
            out[field]=o
        summary[window]=out
    data.atomic_json(HERE/'prospective_summary.json',summary)
    with (HERE/'prospective_trades.csv').open('w',newline='') as f:
        cols=['ticker','filing_date','sector','event_status','event_short_net','sector_gap','pair_net','pair_per_gross_reference','entry_admitted_peers']
        w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=12)
    run(parser.parse_args().workers)
