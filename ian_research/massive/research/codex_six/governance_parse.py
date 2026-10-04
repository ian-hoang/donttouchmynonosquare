"""Conservative candidate extraction from cached primary-source text. Human QA required."""
import json,re,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
CACHE=HERE.parents[1]/'.massive_cache'/'codex_six'
NUM=re.compile(r'(?<![\w,.])\d{1,3}(?:,\d{3})+(?:\.0+)?(?![\w,.])')
PAY=re.compile(r'(advisory.*compens|compens.*advisory|say.on.pay|approve.*compensation.*executive|compensation.*named executive.*approved)',re.I)
def parse(r):
 p=CACHE/('governance_'+r['accession_number']+'_resolved.txt')
 if not p.exists():p=CACHE/('governance_'+r['accession_number']+'.txt')
 if not p.exists() or p.stat().st_size<1000:return None
 text=p.read_text();lines=[re.sub(r'^L\d+:\s*','',x) for x in text.splitlines()]
 def nums(l):return [int(float(v.replace(',',''))) for v in NUM.findall(l)]
 directors=[]
 for l in lines:
  n=nums(l);label=next((c.strip() for c in l.split('|') if re.search(r'[A-Za-z]',c)), '')
  if len(n)>=2 and re.search(r'[A-Za-z]',label) and len(label)<65 and len(label.split())>=2 and not re.search(r'(ratif|approv|advisory|proposal|compensation|audit|votes|voted|shares|election|stock|plan|director|requesting|broker|amend|say on pay|board chairman|approved|202[45])',label,re.I):
   directors.append({'name':label,'for':n[0],'against_or_withheld':n[1]})
 pays=[]
 for i,l in enumerate(lines):
  if not PAY.search(l) or re.search(r'(frequency|stockholder proposal|shareholder proposal)',l,re.I):continue
  for j in range(i,min(i+22,len(lines))):
   n=nums(lines[j]);label=re.sub(r'^[\d.\s|()]+','',lines[j][:NUM.search(lines[j]).start()] if NUM.search(lines[j]) else lines[j]).replace('|',' ').strip()
   if len(n)>=2:
    if re.search('[A-Za-z]',label) and not PAY.search(label) and label.lower()!='approved':break
    pays.append(n[:2]);break
   if len(n)==1 and re.search(r'\bFor\b',lines[j],re.I) and not re.search(r'\bAgainst\b',lines[j],re.I):
    for k in range(j+1,min(j+6,len(lines))):
     nn=nums(lines[k])
     if nn and re.search(r'\bAgainst\b',lines[k],re.I):pays.append([n[0],nn[0]]);break
    break
 pays=list(dict.fromkeys(tuple(x) for x in pays));url=re.search(r'https://www.sec.gov/[^\s)]+',text)
 return {'ticker':r['ticker'],'filing_date':r['filing_date'],'accession_number':r['accession_number'],'source':url.group() if url else r['guess_url'],'pay_candidates':pays,'directors':directors,'cache_file':p.name}
def main():
 rows=json.loads((CACHE/'governance_candidates_raw.json').read_text());out=[p for r in rows if (p:=parse(r))]
 (CACHE/'governance_parsed.json').write_text(json.dumps(out,indent=2))
 for x in out:
  pa=x['pay_candidates'];ds=x['directors'];pay=round(100*pa[0][1]/sum(pa[0]),2) if len(pa)==1 else str(pa)
  dm=round(statistics.mean(100*d['against_or_withheld']/(d['for']+d['against_or_withheld']) for d in ds),2) if ds else None
  print(x['ticker'],x['filing_date'],'pay',pay,'directors',len(ds),'mean',dm)
if __name__=='__main__':main()
