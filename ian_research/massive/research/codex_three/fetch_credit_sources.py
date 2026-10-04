"""Download public original SEC submissions for the 43 in-sample credit updates.

No Massive secret is sent to SEC. Sources are cached under the ignored data cache.
"""
import hashlib
import json
import time
import requests
from data import HERE, ROOT, disclosures

SOURCE_DIR=ROOT/'.massive_cache'/'codex_three_sec'

def main():
    SOURCE_DIR.mkdir(exist_ok=True)
    rows={ (r['ticker'],r['filing_date']):r for r in disclosures()
           if r['ticker'] in {'AXP','COF'} and r['tertiary_category']=='business_update'}
    manifest=[]
    session=requests.Session()
    session.headers.update({'User-Agent':'GQH research contact https://github.com/ian-hoang','Accept-Encoding':'gzip, deflate'})
    for (ticker,date),r in sorted(rows.items()):
        url=r['filing_url']
        if not url.startswith('https://www.sec.gov/Archives/edgar/data/'):
            raise RuntimeError('Unexpected public source host')
        p=SOURCE_DIR/(hashlib.sha256(url.encode()).hexdigest()+'.txt')
        status='cached'
        if not p.exists():
            try:
                response=session.get(url,timeout=20)
                status=response.status_code
                if response.status_code==200 and '<SEC-DOCUMENT>' in response.text[:1000]:
                    p.write_text(response.text)
                else:
                    print(ticker,date,'HTTP',status,flush=True)
                    manifest.append(dict(ticker=ticker,filing_date=date,filing_url=url,status=status))
                    if response.status_code==403:
                        print('Stopping SEC requests after access rejection.',flush=True)
                        break
            except requests.RequestException as e:
                status=type(e).__name__
                print('Network error',status,flush=True)
                break
            time.sleep(.2)
        manifest.append(dict(ticker=ticker,filing_date=date,filing_url=url,status=status,path=str(p),accession_number=r['accession_number']))
        print(ticker,date,status,flush=True)
    (HERE/'credit_source_manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
