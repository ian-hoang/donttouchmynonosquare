"""Download original issuer earnings press releases and extract historical body only."""
import sys,json,re,hashlib,time
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
import events_news as m
OUT=m.HERE/'events_original_cache';OUT.mkdir(exist_ok=True)
from common import RateLimiter
LIMITER=RateLimiter(1.5)
class Body(HTMLParser):
 def __init__(self):super().__init__();self.active=False;self.depth=0;self.parts=[];self.meta=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='meta' and ('date' in a.get('property','').lower() or 'date' in a.get('itemprop','').lower()):self.meta.append(a)
  if a.get('id')=='main-body-container':self.active=True;self.depth=1;return
  if self.active and tag=='div':self.depth+=1
 def handle_endtag(self,tag):
  if self.active and tag=='div':
   self.depth-=1
   if self.depth==0:self.active=False
 def handle_data(self,s):
  if self.active:self.parts.append(s)
def get(x):
 p=OUT/(hashlib.sha256(x['article_url'].encode()).hexdigest()+'.json')
 if p.exists():
  old=json.loads(p.read_text())
  if old.get('published_utc'):return old
 try:
  LIMITER.wait()
  r=requests.get(x['article_url'],timeout=25)
  b=Body();b.feed(r.text)
  result={'url':x['article_url'],'source_id':x['id'],'http_status':r.status_code,'body':' '.join(' '.join(b.parts).split()),'date_meta':b.meta,'html_sha256':hashlib.sha256(r.content).hexdigest()}
  from html import unescape
  dm=re.search(r'<time[^>]*datetime="([^"]+)"',r.text);tm=re.search(r'<meta property="og:title" content="([^"]+)"',r.text)
  result['published_utc']=dm.group(1) if dm else None
  result['title']=unescape(tm.group(1)) if tm else None
  result['organization_paths']=list(dict.fromkeys(re.findall(r'href="([^"]*search/organization/[^"]+)"',r.text)))
 except requests.RequestException as e:result={'url':x['article_url'],'source_id':x['id'],'error':type(e).__name__}
 p.write_text(json.dumps(result));return result
if __name__=='__main__':
 items={}
 for f in m.CACHE.glob('*.json'):
  j=json.loads(f.read_text())
  for x in j.get('results',[]):
   if m.issuer_match(j['ticker'],x):items[x['article_url']]=x
 print('original issuer candidates',len(items),flush=True)
 counts={}
 with ThreadPoolExecutor(8) as ex:
  for i,fu in enumerate(as_completed([ex.submit(get,x) for x in items.values()]),1):
   r=fu.result();key=str(r.get('http_status',r.get('error')))+'_'+str(bool(r.get('body')));counts[key]=counts.get(key,0)+1
   if i%25==0:print(i,counts,flush=True)
 print(counts)
