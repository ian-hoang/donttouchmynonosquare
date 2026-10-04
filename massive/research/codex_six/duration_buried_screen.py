"""Deterministic pre-price candidate screen; full-source annotation is separate."""
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'codex_three'))
from data import disclosures

ADVERSE_TAGS = {
    'asset_impairment', 'goodwill_impairment', 'investment_impairment',
    'material_charge_or_gain', 'material_litigation', 'regulatory_investigation',
    'financial_restatement', 'accounting_error_correction', 'cybersecurity_incident',
    'restructuring_plan', 'workforce_reduction', 'facility_closure',
    'business_line_exit', 'mine_safety_violation', 'voluntary_bankruptcy',
    'regulatory_decision',
    'settlement_agreement',
}
RISK_WORDS = re.compile(r'\b(disrupt\w*|shutdown\w*|outage\w*|cyber\w*|ransom\w*|recall\w*|halt\w*|suspend\w*|suspens\w*|shortage\w*|strike\w*|breach\w*|incident\w*|advers\w*|deteriorat\w*|restat\w*|impair\w*|investigat\w*|litigat\w*|declin\w*|reduc\w*|lower\w*|weak\w*|loss\w*|deficien\w*|noncompli\w*)\b', re.I)
OPERATING_TAGS = {'guidance_issuance_or_update', 'preliminary_results', 'business_update', 'quarterly_earnings', 'annual_earnings', 'strategic_initiative', 'investor_presentation', 'supply_or_distribution_agreement', 'significant_contract_award'}
ROUTINE_TAGS = {'bylaw_amendment', 'charter_amendment', 'annual_meeting_results', 'special_meeting_results', 'shareholder_proposal_outcome', 'executive_compensation_change', 'equity_compensation_grant', 'benefit_plan_blackout', 'fiscal_year_change', 'listing_transfer', 'trading_plan_10b5_1', 'director_appointment', 'director_departure', 'executive_officer_appointment', 'executive_officer_departure', 'ceo_appointment', 'ceo_departure', 'cfo_appointment', 'cfo_departure'}

def main():
    rows = disclosures()
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r['accession_number']].append(r)
    candidates = []
    for accession, records in sorted(groups.items(), key=lambda x:(x[1][0]['ticker'], x[1][0]['filing_date'])):
        adverse = [r for r in records if r['tertiary_category'] in ADVERSE_TAGS or (r['tertiary_category'] in OPERATING_TAGS and RISK_WORDS.search(r['supporting_text']))]
        if not adverse:
            continue
        routine = [r for r in records if r['tertiary_category'] in ROUTINE_TAGS]
        candidates.append(dict(ticker=records[0]['ticker'], filing_date=records[0]['filing_date'], accession_number=accession, filing_url=records[0]['filing_url'], adverse_tags=sorted({r['tertiary_category'] for r in adverse}), routine_tags=sorted({r['tertiary_category'] for r in routine}), records=records))
    result = dict(input_rows=len(rows), input_filings=len(groups), input_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(), adverse_candidate_filings=len(candidates), with_routine_tags=sum(bool(c['routine_tags']) for c in candidates), candidates=candidates)
    (HERE/'duration_buried_candidates.json').write_text(json.dumps(result,indent=2))
    print({k:v for k,v in result.items() if k!='candidates'})
    for i,c in enumerate(candidates):
        print(i,c['ticker'],c['filing_date'],','.join(c['adverse_tags']),'ROUTINE',','.join(c['routine_tags']))

if __name__=='__main__': main()
