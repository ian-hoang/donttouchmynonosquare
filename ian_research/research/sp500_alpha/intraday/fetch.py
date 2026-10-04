"""Read-only SPY aggregate downloads; credentials in headers only, never output."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import gzip, hashlib, json, sys, threading, time
import pandas as pd
import requests

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'massive'))
from eightk import load_api_key
RAW=HERE/'raw'; RAW.mkdir(exist_ok=True)
_local=threading.local()

def fetch(path,params,name):
    dest=RAW/(name+'.json.gz')
    if dest.exists():
        with gzip.open(dest,'rt') as f: j=json.load(f)
        return {'name':name,'cached':True,'rows':len(j.get('results',[])),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}
    if not hasattr(_local,'s'):
        _local.s=requests.Session(); _local.s.headers['Authorization']='Bearer '+load_api_key()
    rows=[];url='https://api.massive.com'+path
    pages=0
    while url:
        if not url.startswith('https://api.massive.com/'): raise ValueError('Unexpected pagination host')
        for attempt in range(5):
            try:
                r=_local.s.get(url,params=params,timeout=45)
            except requests.RequestException:
                if attempt==4: raise RuntimeError('Network error') from None
                time.sleep(2**attempt);continue
            if r.status_code in [429,500,502,503,504]: time.sleep(2**attempt);continue
            break
        if r.status_code!=200: raise RuntimeError(f'HTTP {r.status_code}, {name}')
        j=r.json(); rows.extend(j.get('results',[]));pages+=1
        url=j.get('next_url');params=None
    j['results']=rows;j['download_pages']=pages;j['source_path']=path
    j['retrieved_utc']=datetime.now(timezone.utc).isoformat()
    with gzip.open(dest,'wt') as f:json.dump(j,f,separators=(',',':'))
    return {'name':name,'cached':False,'rows':len(rows),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()}

def main():
    req=[]
    for start in pd.date_range('2015-01-01','2026-10-01',freq='MS'):
        end=min(start+pd.offsets.MonthEnd(0),pd.Timestamp('2026-10-02'))
        req.append((f'/v2/aggs/ticker/SPY/range/1/minute/{start.date()}/{end.date()}',{'adjusted':'true','sort':'asc','limit':50000},'minute_'+start.strftime('%Y_%m')))
    req += [(f'/v2/aggs/ticker/SPY/range/1/day/2014-12-01/2026-10-02',{'adjusted':'true','sort':'asc','limit':50000},'daily'),('/v3/reference/dividends',{'ticker':'SPY','ex_dividend_date.gte':'2015-01-01','ex_dividend_date.lte':'2026-10-02','limit':1000},'dividends'),('/v3/reference/splits',{'ticker':'SPY','execution_date.gte':'2014-12-01','execution_date.lte':'2026-10-02','limit':1000},'splits')]
    out=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs={pool.submit(fetch,*r):r[2] for r in req}
        for fut in as_completed(futs):
            try:out.append(fut.result())
            except Exception as e:out.append({'name':futs[fut],'error':str(e)})
            if len(out)%12==0: print('Completed',len(out),'of',len(req),flush=True)
    (HERE/'manifest.json').write_text(json.dumps(sorted(out,key=lambda r:r['name']),indent=2))
    print('Downloads',len(out),'rows',sum(r.get('rows',0) for r in out),'errors',[r for r in out if 'error' in r],flush=True)
if __name__=='__main__':main()
