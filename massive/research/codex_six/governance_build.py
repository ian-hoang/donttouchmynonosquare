"""Reproduce price-blind governance selection from primary-source numerical annotations."""
import json,statistics,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
CACHE=HERE.parents[1]/'.massive_cache'/'codex_six'
def main():
 annotations=json.loads((HERE/'governance_annotations.json').read_text());rows=json.loads((CACHE/'governance_candidates_raw.json').read_text());by={}
 for x in annotations['filings']:by.setdefault(x['ticker'],{})[x['filing_date'][:4]]=x
 events=[];controls=[];audit=[]
 for r in rows:
  base={k:r[k] for k in ['ticker','filing_date','accession_number']}
  if r['filing_date'].startswith('2024'):audit.append(dict(base,status='prior_reference_only',reason='2023 prior excluded by fixed 2024-25 window'));continue
  if not r['paired_prior']:audit.append(dict(base,status='excluded',reason='No cached 2024 annual-meeting counterpart'));continue
  pair=by.get(r['ticker'],{})
  if set(pair)!={'2024','2025'} or pair['2025']['accession_number']!=r['accession_number']:
   reason=annotations.get('exclusions',{}).get(r['ticker'],'Duplicate preliminary PG annual-meeting announcement; final numerical vote disclosure on 2025-10-16 is retained.' if r['ticker']=='PG' else 'Full paired vote-table verification incomplete; never treated as a nontrigger')
   audit.append(dict(base,status='excluded',reason=reason,sources=[r['source']]));continue
  a,b=pair['2024'],pair['2025']
  def pay(x):return 100*x['pay_against']/(x['pay_for']+x['pay_against'])
  def board(x):return statistics.mean(100*d['against_or_withheld']/(d['for']+d['against_or_withheld']) for d in x['directors'])
  pa,pb,da,db=pay(a),pay(b),board(a),board(b);score=(pb-pa)-(db-da)
  record=dict(base,signal='shareholder_dissent_increase',strategy='protective_put',score=score/100,score_pp=score,reason=f'Pay dissent {pa:.6f}% to {pb:.6f}%; board mean dissent {da:.6f}% to {db:.6f}%; net increase {score:.6f}pp versus frozen >=10pp cutoff.',sources=[a['source'],b['source']],features={'pay_dissent_before_pct':pa,'pay_dissent_after_pct':pb,'director_dissent_before_pct':da,'director_dissent_after_pct':db,'pay_change_pp':pb-pa,'director_change_pp':db-da,'director_count_before':len(a['directors']),'director_count_after':len(b['directors']),'prior_accession_number':a['accession_number'],'board_composition_changed':set(d['name'] for d in a['directors'])!=set(d['name'] for d in b['directors'])},source_annotations=[a,b])
  (events if score>=10 else controls).append(record);audit.append(dict(base,status='qualifying' if score>=10 else 'verified_nontrigger',score_pp=score,reason=record['reason']))
 result={'status':annotations['status'],'spec':'governance_spec.json','events':events,'controls':controls,'counts':{'cached_filing_days':len(rows),'paired_2025_filing_days':sum(r['filing_date'].startswith('2025') and r['paired_prior'] for r in rows),'fully_verified_pairs':len(events)+len(controls),'qualifying':len(events),'controls':len(controls),'paired_issuers':len(set(r['ticker'] for r in rows if r['filing_date'].startswith('2025') and r['paired_prior'])),'unpaired_current_filings':sum(r['filing_date'].startswith('2025') and not r['paired_prior'] for r in rows),'excluded_paired_current_filings':sum(a['status']=='excluded' and any(r['accession_number']==a['accession_number'] and r['paired_prior'] for r in rows) for a in audit)},'audit':audit,'limitations':['Static sponsor universe; only 2024-25 disclosure-tag candidate coverage.','Director composition can change and staggered boards vote on only one class; baseline is the unweighted mean of candidates actually on that year ballot, as specified.','Board composition differences are flagged; net dissent is not evidence about future prices.','Form8-K timestamps are represented by filing dates in cached metadata; central pricing applies delay.','Only fully source-verified pairs enter events or controls; unavailable tables remain excluded.']}
 result['reproducibility']={'selection_command':'python massive/research/codex_six/governance_build.py','source_reparse_command':'python massive/research/codex_six/governance_finalize.py','annotations_sha256':hashlib.sha256((HERE/'governance_annotations.json').read_bytes()).hexdigest(),'spec_sha256':hashlib.sha256((HERE/'governance_spec.json').read_bytes()).hexdigest(),'return_data_accessed':False,'raw_primary_sources':'massive/.massive_cache/codex_six/governance_*.txt','screening_unit':'issuer filing day; multiple disclosure tags deduplicated'}
 (HERE/'governance_events.json').write_text(json.dumps(result,indent=2)+'\n');print(result['counts']);print([(r['ticker'],r['score_pp']) for r in events])
if __name__=='__main__':main()
