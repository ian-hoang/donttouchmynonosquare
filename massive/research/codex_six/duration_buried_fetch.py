"""Retrieve only public original 2024-25 filings, with no market data requests."""
import hashlib
import json
import time
from pathlib import Path
import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE.parents[1] / '.massive_cache' / 'codex_six'

def main():
    CACHE.mkdir(exist_ok=True)
    candidates = json.loads((HERE/'duration_buried_candidates.json').read_text())['candidates']
    manifest = []
    session=requests.Session()
    session.headers.update({'User-Agent':'GQH research contact https://github.com/ian-hoang', 'Accept-Encoding':'gzip, deflate'})
    for c in candidates:
        url=c['filing_url']
        if not (url.startswith('https://www.sec.gov/Archives/edgar/data/') and '2024-01-01' <= c['filing_date'] <= '2025-12-31'):
            raise ValueError('Unexpected source')
        p=CACHE/('duration_buried_'+hashlib.sha256(url.encode()).hexdigest()+'.txt')
        result=dict(ticker=c['ticker'],filing_date=c['filing_date'],accession_number=c['accession_number'],url=url,path=str(p))
        if p.exists():
            result['status']='cached'
        else:
            try:
                r=session.get(url,timeout=30)
                result['status']=r.status_code
                if r.status_code==200 and '<SEC-DOCUMENT>' in r.text[:1000]:
                    p.write_text(r.text)
                elif r.status_code==403:
                    manifest.append(result)
                    print('Stopping after SEC403',c['ticker'],c['filing_date'],flush=True)
                    break
            except requests.RequestException as e:
                result['status']=type(e).__name__
                manifest.append(result)
                print('Stopping after network failure',result,flush=True)
                break
            time.sleep(.2)
        if p.exists(): result['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
        manifest.append(result)
        (HERE/'duration_buried_source_manifest.json').write_text(json.dumps(manifest,indent=2))
        print(c['ticker'],c['filing_date'],result['status'],flush=True)
    (HERE/'duration_buried_source_manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__': main()
