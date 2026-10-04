"""Run only the independently implemented frozen rule; no old-harness imports."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import date,datetime,timezone
import hashlib
import json
from pathlib import Path
import time
from . import data,events,pricing

HERE=Path(__file__).resolve().parent


def fingerprint():
    return hashlib.sha256(b''.join((HERE/name).read_bytes() for name in
        ['pricing.py','trading_calendar.py','data.py','conventions.json'])).hexdigest()


def one_trade(job,completed,signature):
    ticker,day=job
    ident=hashlib.sha256(f'{signature}:{completed}:{ticker}:{day}'.encode()).hexdigest()
    path=data.CACHE/'priced'/(ident+'.json')
    if path.exists():
        r=json.loads(path.read_text())
        if r.get('status')!='error':return r
    try:r=pricing.price_trade(ticker,date.fromisoformat(day),completed_session=completed)
    except Exception as error:
        r=dict(ticker=ticker,filing_date=day,status='error',drop_reason=type(error).__name__,
               error=str(error) if isinstance(error,RuntimeError) else type(error).__name__)
    data.atomic_json(path,r)
    return r


def price_many(jobs,completed,workers,label):
    jobs=sorted(set(jobs));out=[];signature=fingerprint();start=time.monotonic()
    with ThreadPoolExecutor(workers) as pool:
        fs={pool.submit(one_trade,j,completed,signature):j for j in jobs}
        for n,f in enumerate(as_completed(fs),1):
            out.append(f.result())
            if n%50==0 or n==len(jobs):
                print(label,n,'/',len(jobs),'elapsed',round(time.monotonic()-start),'sec',flush=True)
    return sorted(out,key=lambda r:(r['filing_date'],r['ticker']))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['prepare','events','peers','all'],default='all')
    ap.add_argument('--workers',type=int,default=16)
    ap.add_argument('--completed-session',default='2026-10-02')
    args=ap.parse_args();completed=date.fromisoformat(args.completed_session)
    if not (data.CACHE/'cohort.json').exists():data.atomic_json(data.CACHE/'cohort.json',events.fetch_events())
    cohort=json.loads((data.CACHE/'cohort.json').read_text())
    if args.stage in ['prepare','peers','all'] and not (data.CACHE/'histories.json').exists():
        data.atomic_json(data.CACHE/'histories.json',events.fetch_histories(args.workers))
    manifest=dict(frozen_spec_sha256=hashlib.sha256((HERE/'FROZEN_SPEC.txt').read_bytes()).hexdigest(),
         started_at_utc=datetime.now(timezone.utc).isoformat(),completed_session=str(completed),
         universe=events.UNIVERSE,universe_size=len(events.UNIVERSE),pricing_fingerprint=fingerprint(),
         code_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.py')},
         conventions=json.loads((HERE/'conventions.json').read_text()),
         source_cohort_sha256=hashlib.sha256((data.CACHE/'cohort.json').read_bytes()).hexdigest(),
         original_code_read_before_own_results=False)
    data.atomic_json(HERE/'run_manifest.json',manifest)
    print('Cohort before',dict(Counter(e['window'] for e in cohort['before'])),
          'kept',dict(Counter(e['window'] for e in cohort['kept'])),flush=True)
    if args.stage=='prepare':return
    # Reassemble through the fingerprinted per-trade cache even for --stage
    # peers; never relabel an aggregate from an older code/cutoff as current.
    event_results=price_many([(e['ticker'],e['filing_date']) for e in cohort['kept']],completed,args.workers,'Events')
    data.atomic_json(data.CACHE/'event_results.json',event_results)
    print('Event statuses',dict(Counter(r['status'] for r in event_results)),flush=True)
    if any(r['status']=='error' for r in event_results):raise RuntimeError('Event request errors remain; inspect ignored result cache and rerun')
    if args.stage=='events':return
    histories=json.loads((data.CACHE/'histories.json').read_text())
    draws,eligible=events.draw_peers(cohort['kept'],histories)
    data.atomic_json(data.CACHE/'peer_draws.json',draws)
    data.atomic_json(data.CACHE/'peer_eligible.json',eligible)
    valid_dates={r['filing_date'] for r in event_results if r['status']=='valid'}
    jobs={(t,d['filing_date']) for d in draws if d['filing_date'] in valid_dates for t in d['tickers']}
    print('Independent peer jobs',len(jobs),'over',len(valid_dates),'valid event dates',flush=True)
    peers=price_many(jobs,completed,args.workers,'Peers')
    data.atomic_json(data.CACHE/'peer_results.json',peers)
    if any(r['status']=='error' for r in peers):raise RuntimeError('Peer request errors remain; rerun rather than silently dropping API failures')
    from .report import report
    report()


if __name__=='__main__':main()
