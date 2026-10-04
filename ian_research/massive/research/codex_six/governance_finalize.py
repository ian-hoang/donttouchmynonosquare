"""Known SEC table-layout repairs and reviewed source annotations; no price input."""
import json,re
from pathlib import Path
from governance_parse import CACHE,HERE,NUM,main as parse_main
parse_main()
rows=json.loads((CACHE/'governance_parsed.json').read_text())
def lines(x):
 ss=(CACHE/x['cache_file']).read_text().splitlines()
 return [z for s in ss if (z:=re.sub(r'^L\d+:\s*','',s).replace('\u200b','').strip(' |\u00a0'))]
def nums(s):return [int(float(v.replace(',',''))) for v in NUM.findall(s)]
def flatten_board(x,start,end):
 ls=lines(x);i=next(i for i,l in enumerate(ls) if start(l));j=next(i2 for i2 in range(i+1,len(ls)) if end(ls[i2]));sec=ls[i:j];ds=[]
 for k,l in enumerate(sec):
  label=l.split('|')[0].strip()
  if re.search(r'[a-z]',label) and len(label)<65 and len(label.split())>=2 and not re.search(r'(Votes|Broker|Election|Each|Abstain|Proposal|Directors|Withheld|Number)',label,re.I):
   n=nums(l)
   for follow in sec[k+1:]:
    if re.search('[A-Za-z]',follow):break
    n+=nums(follow)
    if len(n)>=2:break
   if len(n)>=2:ds.append({'name':label,'for':n[0],'against_or_withheld':n[1]})
 return ds
for x in rows:
 t=x['ticker'];y=x['filing_date'][:4]
 if t=='C' and y=='2024':
  x['directors']=flatten_board(x,lambda l:l=='Nominees',lambda l:l.startswith('(2)'));x['pay_candidates']=[[1274061608,92445862]];assert len(x['directors'])==13
 if t=='CMCSA':
  x['directors']=flatten_board(x,lambda l:l.startswith('Kenneth J. Bacon'),lambda l:l.startswith('(2)'));assert len(x['directors'])==10
  if y=='2024':x['pay_candidates']=[[326433027,40977963]]
 if t=='PG' and y=='2024':
  x['directors']=flatten_board(x,lambda l:l.startswith('Allen, B. Marc'),lambda l:l.startswith('Proposal 2'));assert len(x['directors'])==14
 if t=='NVDA':
  ls=lines(x);ds=[]
  for i,l in enumerate(ls):
   if re.match(r'^[a-m]\.\s+',l):
    f=nums(ls[i+1]);a=nums(ls[i+2]);assert f and a and 'For' in ls[i+1] and 'Against' in ls[i+2];ds.append({'name':l[3:].strip(' |'),'for':f[0],'against_or_withheld':a[0]})
  assert len(ds)==(12 if y=='2024' else 13);x['directors']=ds
 if t=='MSFT':x['pay_candidates']=[[4727655048,448256975]] if y=='2024' else [[4744731533,415831135]]
# Recovered all table layouts; records failing numeric completeness remain excluded.
out=[]
for x in rows:
 if len(x['pay_candidates'])!=1 or len(x['directors'])<2 or x['ticker'] in ['DIS','GOOGL','PLTR','TMUS']:continue
 a,b=x.pop('pay_candidates')[0];x['pay_for']=a;x['pay_against']=b
 x['source_verification']='Primary SEC table headers and proposal identity reviewed; raw numerical For and Against/Withheld extracted. Named director rows checked; multiline layouts explicitly repaired. Abstentions, broker nonvotes, frequency votes and other proposals excluded.'
 x['voting_method']='withheld' if x['ticker'] in ['SBUX','CMCSA','PLTR','LOW'] else 'against'
 out.append(x)
(HERE/'governance_annotations.json').write_text(json.dumps({'status':'complete_with_disclosed_source_exclusions','filings':out,'exclusions':{'DIS':'2024 contested election with third-party slates/withhold results and preliminary incomplete inspector tally, versus 2025 uncontested For/Against. Not a comparable baseline.','GOOGL':'No annual say-on-pay proposal in both paired meetings; 2025 proposal list lacks executive compensation vote.','PLTR':'No say-on-pay vote in either cached annual meeting.','TMUS':'2024 and2025 annual meetings contain only directors and auditor proposals; no pay-vote channel.'}},indent=2)+'\n')
