"""Collect NBBO execution and liquidity inputs. Does not calculate P&L."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import timedelta
import json

import pandas as pd

from core import HERE,ROOT
from options_audit import cutoff,first_stock_quote,quote


def quote_key(ticker,day,kind):return f'{ticker}|{day}|{kind}'


def one(ticker,day,kind):
    at=cutoff(day)
    if kind=='entry':at+=timedelta(minutes=1)
    return quote(ticker,at,60) if kind=='signal' else first_stock_quote(ticker,day,at)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--workers',type=int,default=6);args=ap.parse_args()
    w=pd.read_csv(HERE/'data/windows.csv')
    cal=pd.DatetimeIndex(pd.read_parquet(ROOT/'data/cache/ai_washing/calendar.parquet')['date'])
    jobs=set()
    for r in w.itertuples():
        for ticker in [r.ticker,'SPY']:
            jobs.add((ticker,r.entry_date,'entry'));jobs.add((ticker,r.exit_date,'exit'))
        jobs.add((r.ticker,r.entry_date,'signal'))
        i=cal.searchsorted(pd.Timestamp(r.entry_date))
        for d in cal[max(0,i-20):i]:jobs.add((r.ticker,str(d.date()),'signal'))
    path=HERE/'data/quotes.json'
    result=json.loads(path.read_text()) if path.exists() else {}
    result={k:v for k,v in result.items() if not (isinstance(v,dict) and 'error' in v)}
    jobs=sorted(j for j in jobs if quote_key(*j) not in result)
    def save():
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(result));temp.replace(path)
    with ThreadPoolExecutor(args.workers) as pool:
        pending={pool.submit(one,*j):j for j in jobs}
        for n,f in enumerate(as_completed(pending),1):
            j=pending[f]
            try:result[quote_key(*j)]=f.result()
            except Exception as exc:result[quote_key(*j)]={'error':type(exc).__name__}
            if n%100==0 or n==len(jobs):
                save();print('Quote inputs collected',n,'/',len(jobs),flush=True)
    save()


if __name__=='__main__':main()
