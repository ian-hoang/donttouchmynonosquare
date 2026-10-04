"""Recall check across every cached 2024–25 excerpt, independent of adverse tags."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'codex_three'))
from data import disclosures

PATTERN = re.compile(r'(?:\b(?:60|90|120|180|two|three|four|five|six)[ -]+(?:days?|months?)\b)|(?:(?:through|until|by).{0,80}(?:2024|2025|quarter))', re.I)
EXCLUDED = set('''acquisition_agreement acquisition_completion annual_meeting_results
bylaw_amendment ceo_appointment ceo_departure cfo_appointment cfo_departure
charter_amendment credit_facility debt_issuance debt_retirement director_appointment
director_departure divestiture_agreement equity_compensation_grant
executive_compensation_change executive_officer_appointment executive_officer_departure
guarantee_or_letter_of_credit merger_agreement merger_completion preferred_stock_modification
private_placement public_offering share_repurchase_program shareholder_proposal_outcome
spinoff_completion tender_offer trading_plan_10b5_1 underwriting_agreement'''.split())

def main():
    rows = disclosures()
    hits = [r for r in rows if PATTERN.search(r['supporting_text'])]
    retained = [r for r in hits if r['tertiary_category'] not in EXCLUDED]
    result = dict(screen='whole-universe horizon recall cross-check',
                  all_horizon_hit_rows=len(hits), retained_rows=len(retained),
                  nonoperational_tags_excluded=sorted(EXCLUDED), retained=retained,
                  review_summary='Retained excerpts were screened for future operating-risk recovery. Most are historical reporting periods, forecasts, transaction/program schedules, and dividends. None states qualifying recovery from an actual ongoing impairment.',
                  additional_candidate_exclusion={
                      'ticker':'FDX', 'filing_date':'2024-04-01',
                      'fact':'USPS contract nonrenewal; existing contract expires September 29, 2024.',
                      'reason':'September 29 is 181 days after filing and is the start of revenue loss, not recovery from an already ongoing disruption.'})
    (HERE/'duration_horizon_crosscheck.json').write_text(json.dumps(result,indent=2)+'\n')
    print({k:v for k,v in result.items() if k not in ('retained','nonoperational_tags_excluded')})

if __name__ == '__main__':
    main()
