"""Read-only Massive client, with an isolated licensed-data cache."""
from pathlib import Path
import hashlib
import json
import time
from urllib.parse import urlparse
import requests
from .. import data as auth

HERE=Path(__file__).resolve().parent
CACHE=HERE/'cache'
RAW=CACHE/'raw'

def get_json(path,params=None):
    url=path if path.startswith('https://') else auth.BASE+path
    if urlparse(url).scheme!='https' or urlparse(url).hostname!='api.massive.com':
        raise ValueError('Unexpected API host')
    full=requests.Request('GET',url,params=params).prepare().url
    if any(x in full.lower() for x in ('apikey=','api_key=','authorization=')):
        raise ValueError('Credential query parameter refused')
    name=hashlib.sha256(full.encode()).hexdigest()+'.json'
    for p in (RAW/name,auth.RAW/name):
        if p.exists():return json.loads(p.read_text())
    for attempt in range(5):
        try:r=auth.session().get(full,timeout=40)
        except requests.RequestException:
            if attempt==4:raise RuntimeError('Massive network request failed') from None
            time.sleep(2**attempt);continue
        if r.status_code in (429,500,502,503,504):
            if attempt==4:raise RuntimeError(f'Massive HTTP {r.status_code}')
            time.sleep(2**attempt);continue
        if r.status_code!=200:raise RuntimeError(f'Massive HTTP {r.status_code}')
        value=r.json();auth.atomic_json(RAW/name,value);return value
    raise RuntimeError('Request failed')

def get_all(path,params=None):
    out=[];seen=set()
    while path:
        marker=(path,json.dumps(params,sort_keys=True))
        if marker in seen:raise ValueError('Pagination cycle')
        seen.add(marker)
        value=get_json(path,params);out.extend(value.get('results') or [])
        path=value.get('next_url');params=None
    return out

def bars(contract,start,end):
    return get_all(f'/v2/aggs/ticker/{contract}/range/1/day/{start}/{end}',
                   {'adjusted':'false','sort':'asc','limit':50000})

def chain(ticker,as_of):
    from datetime import date,timedelta
    as_of=date.fromisoformat(str(as_of));out={}
    for spelling in ([ticker,ticker.replace('.','/')] if '.' in ticker else [ticker]):
        for row in get_all('/v3/reference/options/contracts',{
            'underlying_ticker':spelling,'as_of':str(as_of),
            'expiration_date.gte':str(as_of+timedelta(days=2)),
            'expiration_date.lte':str(as_of+timedelta(days=180)),'limit':1000}):
            out.setdefault(row['ticker'],row)
    return list(out.values())
