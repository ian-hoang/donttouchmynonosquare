"""Complete issuer primary-source archives for GN issuers found in fixed150 universe.
Coverage-driven selection only; no stock returns read.
"""
import json,re,hashlib,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from urllib.parse import urljoin
from html import unescape
import requests
import events_news as m
import events_original as orig
ARCH=m.HERE/'events_archive_cache';ARCH.mkdir(exist_ok=True)
def run(ticker,seed):
 first=orig.get(seed)
 paths=first.get('organization_paths',[])
 if not paths:return {'ticker':ticker,'error':'no organization path'}
 org=unescape(paths[0]).split('?')[0];links={};pages=0;earliest='';error=None
 for page in range(1,81):
  cp=ARCH/f'{ticker}_{page:03d}.json'
  if cp.exists():cache=json.loads(cp.read_text())
  else:
   url='https://www.globenewswire.com'+org+f'?page={page}'
   try:
    orig.LIMITER.wait()
    r=requests.get(url,timeout=30)
    if r.status_code!=200:error=f'HTTP{r.status_code}';break
    found=list(dict.fromkeys(unescape(s) for s in re.findall(r'href="([^"]*news-release/[^\"]+)"',r.text)))
    cache={'url':url,'links':found};cp.write_text(json.dumps(cache))
   except requests.RequestException as e:error=type(e).__name__;break
  pages+=1;found=cache['links']
  if not found:break
  dates=[]
  for link in found:
   md=re.search(r'news-release/(\d{4})/(\d{2})/(\d{2})/',link)
   if not md:continue
   d='-'.join(md.groups());dates.append(d)
   if not ('2022-01-01'<=d<'2026-10-01'):continue
   if re.search(r'results|earnings|conference-call',link,re.I):links[urljoin('https://www.globenewswire.com',link)]=d
  earliest=min(dates) if dates else ''
  if earliest and earliest<'2022-01-01':break
 # Metadata from original article; we do not take mutable search-page timestamps.
 items=[]
 for url,d in links.items():
  x={'article_url':url,'id':'gn_'+hashlib.sha256(url.encode()).hexdigest()}
  body=orig.get(x)
  if not body.get('published_utc') or not body.get('body'):continue
  items.append({**x,'title':body['title'],'description':body['body'],'published_utc':body['published_utc'],'publisher':{'name':'GlobeNewswire Inc.'},'tickers':[ticker],'source_method':'original_issuer_archive'})
 result={'ticker':ticker,'start':'2022-01-01','end_exclusive':'2026-10-01','pages':pages,'total_news':len(links),'truncated':pages==80,'earliest_archive_date':earliest,'error':error,'results':items}
 (m.CACHE/f'{ticker}__direct.json').write_text(json.dumps(result))
 return {k:v for k,v in result.items() if k!='results'}|{'result_count':len(items)}
if __name__=='__main__':
 candidates={}
 for f in m.CACHE.glob('*.json'):
  if '__' in f.name:continue
  j=json.loads(f.read_text());xs=[x for x in j.get('results',[]) if m.issuer_match(j['ticker'],x)]
  if len(xs)>=3:candidates[j['ticker']]=xs[0]
 print('issuer count',len(candidates),sorted(candidates),flush=True)
 with ThreadPoolExecutor(6) as ex:
  for fu in as_completed([ex.submit(run,t,x) for t,x in candidates.items()]):print(json.dumps(fu.result()),flush=True)
 m.build()
