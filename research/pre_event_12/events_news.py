"""Reconstruct earnings schedules from dated issuer news; no price outcomes used.

The input universe is top 150 by trailing dollar volume at 2022-12-30 from the
existing point-in-time universe cache, not selected for future returns.
News is a retrospectively retrieved archive, not a timestamped vendor snapshot.
We retain historical article publication stamps and original forward statements,
but cannot assert the vendor's historical ingestion latency or revision history.
"""
from __future__ import annotations
import argparse,sys,json,re,time,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from dateutil.parser import parse
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
CACHE=HERE/'events_news_cache'
CACHE.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'alpha_ideas'/'ai_washing'))
from common import massive_get
START='2023-01-01'; END='2026-10-01'
WORDS=re.compile(r'earning|financial result|quarter.*result|annual.*result|year.*result',re.I)
WIRE=re.compile(r'globenewswire|business\s*wire|pr\s*newswire|accesswire|access\s*newswire',re.I)
DATE=re.compile(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?)\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*,?\s*20\d\d)?\b',re.I)
FWD=re.compile(r'\b(?:will|plans? to|expects? to|scheduled to|to)\s+(?:report|release|announce|publish)\b',re.I)
RELEASE=re.compile(r'\b(?:report|release|announce|publish)(?:s|d)?\b.{0,160}?\b(?:results|earnings)\b',re.I)

def universe():
 u=pd.read_parquet(ROOT/'data/cache/ai_washing/universe.parquet')
 u=u[u.month_end<=pd.Timestamp('2022-12-31')]
 u=u[u.month_end==u.month_end.max()].sort_values('rank').head(150)
 p=pd.read_parquet(ROOT/'data/cache/ai_washing/prices.parquet',columns=['date','cik','ticker'])
 p=p[p.date<=pd.Timestamp('2022-12-31')].sort_values('date').groupby('cik').tail(1)
 return u.merge(p,on='cik')[['cik','ticker','rank','dv63']]

def fetch(ticker):
 path=CACHE/f'{ticker}.json'
 if path.exists(): return json.loads(path.read_text())
 url='/v2/reference/news';par={'ticker':ticker,'published_utc.gte':START,'published_utc.lt':END,'limit':1000,'order':'asc'}
 keep=[];pages=0;n=0
 while url and pages<100:
  s,j=massive_get(url,par)
  if s!=200: return {'ticker':ticker,'error':f'HTTP {s}'}
  items=j.get('results',[]);n+=len(items);pages+=1
  for x in items:
   if WIRE.search(x.get('publisher',{}).get('name','')) and WORDS.search(x.get('title','')):
    keep.append(x)
  url=j.get('next_url');par=None
 result={'ticker':ticker,'start':START,'end_exclusive':END,'pages':pages,'total_news':n,'truncated':bool(url),'results':keep}
 path.write_text(json.dumps(result))
 return result

def issuer_match(ticker,x):
 # News ticker associations are not issuer identity: TSXV CVX is CEMATRIX,
 # while NYSE CVX is Chevron, and multi-company tags can be outright wrong.
 title=x.get('title','').strip();desc=x.get('description','')
 univ=universe_cached()
 row=univ.get(ticker,{})
 name=row.get('name','')
 words=re.findall(r"[A-Za-z0-9&]+",name)
 words=[w for w in words if w.lower() not in {'the','inc','corp','corporation','plc','ltd','co'}]
 needles=[ticker] if len(ticker)>=2 else []
 if words and len(words[0])>=4: needles.append(words[0])
 if len(words)>=2: needles.append(' '.join(words[:2]))
 for needle in needles:
  if re.match(r'(?:UPDATE\s*[-:—]\s*)?'+re.escape(needle)+r'\b',title,re.I):return True
 return bool(re.search(r'\b(?:NASDAQ|NYSE)\s*[:：]\s*'+re.escape(ticker)+r'\b',desc,re.I))

_UNIVERSE=None
def universe_cached():
 global _UNIVERSE
 if _UNIVERSE is None:
  _UNIVERSE={}
  for r in universe().itertuples():
   p=ROOT/'data/cache/ai_washing/sec/submissions'/f'CIK{str(r.cik).zfill(10)}.json'
   j=json.loads(p.read_text()) if p.exists() else {}
   _UNIVERSE[r.ticker]={'name':j.get('name','')}
 return _UNIVERSE

def extract(ticker,x):
 if not issuer_match(ticker,x):return None
 title=x.get('title','');desc=x.get('description','');original=HERE/'events_original_cache'/(hashlib.sha256(x['article_url'].encode()).hexdigest()+'.json');verified=False
 if original.exists():
  original_data=json.loads(original.read_text())
  if original_data.get('body'):
   desc=original_data['body'];verified=True
   if original_data.get('published_utc'):x={**x,'published_utc':original_data['published_utc']}
 pub=pd.Timestamp(x['published_utc']);day=pub.tz_convert('America/New_York').tz_localize(None).normalize()
 # Match a release promise in title or body. Do not infer reporting date solely
 # from a conference-call notice, earnings-calendar listing or 8-K acceptance.
 if not FWD.search(title+' '+desc) and not (ticker=='NVDA' and 'results are publicly announced' in desc): return None
 # Title promises plus body explicit result/date clauses; prioritize description.
 segs=[]
 for m in FWD.finditer(desc): segs.append(desc[m.start():m.end()+400])
 for m in FWD.finditer(title): segs.append(title[m.start():m.end()+180])
 candidates=[]
 for segment in segs:
  matches=list(DATE.finditer(segment))
  for m in matches:
   ds=re.sub(r'(\d)(st|nd|rd|th)\b',r'\1',m.group())
   try:
    dt=pd.Timestamp(parse(ds,default=day.to_pydatetime())).normalize()
   except (ValueError,OverflowError): continue
   if dt<day and not re.search(r'20\d\d',ds) and day.month==12: dt=dt.replace(year=day.year+1)
   if not 1<=(dt-day).days<=100: continue
   # The nearest date after a release/results phrase is accepted only if the
   # phrase precedes it, and no conf-call phrase intervenes. This avoids making
   # a conference date stand in for the release date.
   prefix=segment[:m.start()]
   if re.search(r'(?:ended|ending|period through)\s*$',prefix,re.I):continue
   if re.search(r'conference call|webcast|earnings call|\bhost\b|\bhold\b',prefix,re.I): continue
   if not re.search(r'results|earnings',prefix,re.I): continue
   candidates.append((dt,segment))
   break
 if not candidates and ticker=='NVDA' and 'results are publicly announced' in desc:
  # Original notice explicitly states results publicly announced before this
  # dated call at1:20PT. The call is a relational anchor, not sole evidence.
  cm=re.search(r'conference call on(.{0,100})',desc,re.I)
  dm=DATE.search(cm.group(1)) if cm else None
  if dm:
   dt=pd.Timestamp(parse(dm.group(),default=day.to_pydatetime())).normalize()
   if 1<=(dt-day).days<=100:candidates=[(dt,desc[:2000])]
 if not candidates:return None
 dates={str(y[0].date()) for y in candidates}
 if len(dates)!=1: return {'rejected':True,'reason':'multiple_forward_dates','ticker':ticker,'id':x['id'],'dates':sorted(dates)}
 dt,quote=candidates[0]
 if re.search(r'after.{0,40}(?:close|closing)|following.{0,25}(?:close|closing)',quote,re.I): timing='after_close'
 elif re.search(r'before.{0,40}(?:open|opening)|prior to.{0,25}(?:open|opening)',quote,re.I):timing='before_open'
 else:timing='unspecified'
 return {'ticker':ticker,'scheduled_date':str(dt.date()),'notice_published_utc':pub.isoformat(),'notice_published_et':pub.tz_convert('America/New_York').isoformat(),'scheduled_timing':timing,'source_title':title,'source_url':x['article_url'],'source_id':x['id'],'source_publisher':x.get('publisher',{}).get('name'),'release_date_evidence':quote,'notice_lead_calendar_days':(dt-day).days,'original_notice_body_verified':verified}

def actual(ticker,x):
 if not issuer_match(ticker,x):return None
 title=x.get('title','')
 if re.search(r'\b(?:to\s+(?:report|announce|release)|will\s+(?:report|announce|release)|announces\s+date|sets|schedules|schedule|conference|webcast|preliminary)\b',title,re.I):return None
 if not re.search(r'\b(?:reports|announces|releases)\b.{0,100}\b(?:results|earnings)\b',title,re.I):return None
 if not re.search(r'quarter|full.year|annual|fiscal\s+(?:year|20\d\d)',title,re.I):return None
 original=HERE/'events_original_cache'/(hashlib.sha256(x['article_url'].encode()).hexdigest()+'.json')
 if original.exists():
  oj=json.loads(original.read_text())
  if oj.get('published_utc'):x={**x,'published_utc':oj['published_utc']}
 pub=pd.Timestamp(x['published_utc'])
 return {'ticker':ticker,'actual_release_utc':pub.isoformat(),'actual_release_et':pub.tz_convert('America/New_York').isoformat(),'actual_date':str(pub.tz_convert('America/New_York').date()),'actual_title':title,'actual_url':x['article_url'],'actual_id':x['id']}

def build():
 u=universe();rows=[];acts=[];reject=[];meta=[]
 for f in sorted(CACHE.glob('*.json')):
  j=json.loads(f.read_text());meta.append({k:v for k,v in j.items() if k!='results'})
  for x in j.get('results',[]):
   e=extract(j['ticker'],x)
   if e and e.get('rejected'):reject.append(e)
   elif e:rows.append(e)
   a=actual(j['ticker'],x)
   if a:acts.append(a)
 d=pd.DataFrame(rows);a=pd.DataFrame(acts)
 if len(d):
  d=d.sort_values('notice_published_utc').drop_duplicates(['ticker','scheduled_date'])
  if len(a):
   a=a.sort_values('actual_release_utc').drop_duplicates(['ticker','actual_date'])
   d=d.merge(a,left_on=['ticker','scheduled_date'],right_on=['ticker','actual_date'],how='left')
  d=d.merge(u,on='ticker',how='left')
  d['eligible_calendar_period']=d['scheduled_date'].between('2023-01-01','2026-09-30')
  d['scheduled_release_date']=d['scheduled_date']
  d['notice_url']=d['source_url']
  d['notice_id']=d['source_id']
  d['historical_ingestion_verified']=False
  d['actual_release_matched']=d['actual_release_utc'].notna() if 'actual_release_utc' in d else False
  d.to_csv(HERE/'events_confirmed.csv',index=False)
  d.to_parquet(HERE/'events_confirmed.parquet',index=False)
 if len(a):a.to_csv(HERE/'events_actual_releases.csv',index=False)
 audit={'definition':'Issuer press-wire notices explicitly promise report/release results on future date; earliest notice per ticker/date. Dates of calls alone are excluded. Actual release timestamp from dated issuer results press release, not 8-K acceptance.','universe_rule':'Top150 trailing-dollar-volume on 2022-12-30 existing point-in-time cache','historical_ingestion_latency_and_revisions_verified':False,'queries':meta,'notice_count':len(d),'ticker_count':d.ticker.nunique() if len(d) else 0,'actual_matched':int(d.actual_release_matched.sum()) if len(d) else 0,'years':d.groupby(d.scheduled_date.str[:4]).size().to_dict() if len(d) else {},'rejections':reject}
 (HERE/'events_audit.json').write_text(json.dumps(audit,indent=2))
 print(json.dumps({k:v for k,v in audit.items() if k not in ['queries','rejections']},indent=2))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--fetch',action='store_true');ap.add_argument('--limit',type=int,default=150);args=ap.parse_args()
 u=universe();u.to_csv(HERE/'events_universe.csv',index=False)
 if args.fetch:
  with ThreadPoolExecutor(8) as ex:
   fs=[ex.submit(fetch,t) for t in u.ticker.head(args.limit)]
   for i,fu in enumerate(as_completed(fs),1):
    j=fu.result();print(i,j.get('ticker'),j.get('total_news'),len(j.get('results',[])),j.get('error',''),flush=True)
 build()
