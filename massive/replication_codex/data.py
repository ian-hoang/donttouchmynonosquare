"""Independent read-only Massive REST client. Raw responses stay in own ignored cache."""
from datetime import date,timedelta
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlparse
import requests

HERE=Path(__file__).resolve().parent
CACHE=HERE/'cache'
RAW=CACHE/'raw'
RAW.mkdir(parents=True,exist_ok=True)
BASE='https://api.massive.com'
_local=threading.local()


def api_key():
    key=os.environ.get('MASSIVE_API_KEY','').strip()
    if not key:
        for line in (HERE.parent/'.env').read_text().splitlines():
            if line.strip().startswith('MASSIVE_API_KEY='):
                key=line.split('=',1)[1].strip().strip('\"').strip("'")
                break
    if not key:raise RuntimeError('Missing configured Massive credential')
    return key


def session():
    if not hasattr(_local,'session'):
        _local.session=requests.Session()
        _local.session.headers['Authorization']='Bearer '+api_key()
    return _local.session


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+f'.{os.getpid()}.{threading.get_ident()}.tmp')
    tmp.write_text(json.dumps(value,separators=(',',':')))
    os.replace(tmp,path)


def get_json(path,params=None):
    url=path if path.startswith('http') else BASE+path
    if urlparse(url).scheme!='https' or urlparse(url).hostname!='api.massive.com':
        raise ValueError('Refusing credentials to unexpected host')
    full=requests.Request('GET',url,params=params).prepare().url
    # No API credential is ever sent or cached as a query parameter.
    if any(x in full.lower() for x in ['apikey=','api_key=','authorization=']):raise ValueError('Credential in URL refused')
    cache=RAW/(hashlib.sha256(full.encode()).hexdigest()+'.json')
    if cache.exists():return json.loads(cache.read_text())
    for attempt in range(7):
        try:response=session().get(full,timeout=45)
        except requests.RequestException:
            if attempt==6:raise RuntimeError('Massive network request failed') from None
            time.sleep(min(2**attempt,10));continue
        if response.status_code in [429,500,502,503,504]:
            if attempt==6:raise RuntimeError('Massive transient HTTP failure '+str(response.status_code))
            delay=response.headers.get('Retry-After','')
            time.sleep(min(float(delay) if delay.isdigit() else 2**attempt,30));continue
        if response.status_code!=200:raise RuntimeError('Massive HTTP '+str(response.status_code))
        payload=response.json();atomic_json(cache,payload)
        return payload
    raise RuntimeError('Massive request retries exhausted')


def get_all(path,params=None):
    results=[];seen=set();url=path
    while url:
        marker=(url,json.dumps(params,sort_keys=True))
        if marker in seen:raise RuntimeError('Pagination cycle')
        seen.add(marker)
        data=get_json(url,params);results.extend(data.get('results') or [])
        url=data.get('next_url');params=None
    return results


def bars(contract,start,end):
    return get_all(f'/v2/aggs/ticker/{contract}/range/1/day/{start}/{end}',
                   {'adjusted':'false','sort':'asc','limit':50000})


def chain(ticker,as_of):
    as_of=date.fromisoformat(str(as_of)[:10])
    records={}
    for spelling in ([ticker,ticker.replace('.','/')] if '.' in ticker else [ticker]):
        rows=get_all('/v3/reference/options/contracts',{'underlying_ticker':spelling,'as_of':str(as_of),
              'expiration_date.gte':str(as_of+timedelta(days=2)),
              'expiration_date.lte':str(as_of+timedelta(days=180)),'limit':1000})
        for r in rows:records.setdefault(r['ticker'],r)
    return list(records.values())
