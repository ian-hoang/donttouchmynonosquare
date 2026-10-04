from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,requests
HERE=Path(__file__).resolve().parent
OUT=HERE/'data';OUT.mkdir(exist_ok=True)
spec=json.loads((HERE/'PROTOCOL.json').read_text())
def fetch(symbol):
 p=OUT/(symbol+'.json');url='https://query1.finance.yahoo.com/v8/finance/chart/'+symbol
 params={'period1':int(datetime(2004,1,1,tzinfo=timezone.utc).timestamp()),'period2':int(datetime(2026,10,3,tzinfo=timezone.utc).timestamp()),'interval':'1d','events':'div,splits','includeAdjustedClose':'true'}
 try:
  if not p.exists():
   r=requests.get(url,params=params,headers={'User-Agent':'Mozilla/5.0'},timeout=40);r.raise_for_status();p.write_text(json.dumps(r.json()))
  j=json.loads(p.read_text())['chart']['result'][0]
  return {'symbol':symbol,'rows':len(j['timestamp']),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'url':url,'params':params,'retrieved_utc':datetime.now(timezone.utc).isoformat()}
 except Exception as e:return {'symbol':symbol,'error_type':type(e).__name__}
with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,spec['assets']))
try:
 p=OUT/'DGS3MO.csv';url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO&cosd=2003-12-01&coed=2026-10-02'
 if not p.exists():
  r=requests.get(url,timeout=40);r.raise_for_status();p.write_text(r.text)
 rows.append({'symbol':'DGS3MO','url':url,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
except Exception as e:rows.append({'symbol':'DGS3MO','error_type':type(e).__name__})
(HERE/'manifest.json').write_text(json.dumps({'fetched_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':hashlib.sha256((HERE/'PROTOCOL.json').read_bytes()).hexdigest(),'data':rows},indent=2))
print(json.dumps(rows,indent=2))
