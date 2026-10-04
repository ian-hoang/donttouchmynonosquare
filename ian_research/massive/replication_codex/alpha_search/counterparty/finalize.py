"""Record rule-based exclusions and source review, never returns."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROWS = json.loads((HERE/'cache/candidate_excerpts.json').read_text())
MANUAL = {
 0: ('wrong_direction', 'Customer account compromise; no customer cancellation of committed Google purchases.'),
 1: ('alias_false_positive', 'The string back-ups is not United Parcel Service.'),
 2: ('wrong_action', 'Oracle software vulnerability; no cancellation of committed purchases or supplier inability to deliver to a named large-cap customer.'),
 3: ('wrong_action', 'Duplicate incident excerpt about Oracle software; no qualifying cancellation or delivery failure.'),
 5: ('financing_or_equity', 'Warrant termination on merger, not commercial purchases.'),
 6: ('wrong_direction', 'Bristol Myers is the party declining a license option; no adverse supply consequence to Bristol Myers stated.'),
 7: ('nonrenewal_or_alternate_sourcing', 'Wells Fargo itself issued nonrenewal; term expiration with portfolio transfer.'),
 8: ('unvalidated_committed_purchase_cancellation', 'Actual filing ends a distribution framework; it does not explicitly establish cancellation of committed purchases.'),
16: ('alias_false_positive', 'Emerson Equity LLC is not Emerson Electric.'),
17: ('wrong_direction', 'Lilly subsidiary elects to terminate a development license; no adverse supply consequence to Lilly stated.'),
24: ('financing_or_equity', 'Indenture cancellation under a plan; U.S. Bank is trustee.'),
27: ('wrong_direction', 'Credit-card partnership ends; no documented failed contracted supply to Walmart.'),
33: ('wrong_counterparty', 'BNY is the new agent; terminated agent is Continental.'),
51: ('financing_or_equity', 'GM loan is repaid and terminated, not a supply order.'),
62: ('governance', 'Termination of director nomination rights, not commercial supply.'),
67: ('financing_or_equity', 'Termination of equity issuance distribution agency.'),
69: ('financing_or_equity', 'Unused bridge-loan commitment terminated.'),
74: ('financing_or_equity', 'Termination of at-the-market securities offering.'),
76: ('wrong_direction', 'Pfizer elects to terminate the collaboration; no adverse supply impact on Pfizer established.'),
82: ('wrong_direction', 'AbbVie elects to terminate the license; no adverse supply impact on AbbVie established.'),
87: ('option_expiration', 'Gilead does not exercise an option; committed purchases are not cancelled.'),
88: ('real_estate', 'Mutual sublease cancellation; no committed goods/services purchases or failed contracted delivery.'),
90: ('financing_or_equity', 'Inventory financing agreement termination.'),
95: ('wrong_direction', 'Bank of America elects not to renew a contract; no adverse supply consequence to Bank of America stated.'),
97: ('financing_or_equity', 'AspenTech credit agreement terminated at acquisition by Emerson; neither an operational purchase cancellation nor delivery failure.'),
112: ('wrong_direction', 'Bank of America elects not to renew and requests continuity of service; no interrupted delivery.'),
120: ('issuer_name_not_counterparty', 'Goldman Sachs BDC is the issuer; agreement terminates with Truist.'),
125: ('no_adverse_receiver_consequence', 'Actual joint press release says doughnuts were a small, non-material part of McDonald\'s breakfast business; joint voluntary termination.'),
132: ('liability_settlement', 'Cash payment replaces future indemnification obligations, not supply purchases.'),
135: ('liability_settlement', 'Completion of indemnification buyout, not supply purchases.'),
136: ('nonrenewal_or_alternate_sourcing', 'Mutual decision not to renew at ordinary term end; excluded by frozen rule.'),
148: ('wrong_counterparty', 'BNY is the new agent; terminated agent is Continental.'),
156: ('financing_or_equity', 'Receivables securitization is repaid and terminated.'),
177: ('nonrenewal_or_alternate_sourcing', 'Google initiates nonrenewal; contractual expiry, no failed supply to Google.'),
179: ('wrong_direction', 'Master-services relationship ends in merger context; no involuntary delivery failure or adverse operating consequence to Capital One specified.'),
182: ('alias_false_positive', 'Federal Reserve Bank of New York is not Bank of New York Mellon.'),
}
for n in [28,29,30,31,32,45,47,48,49,50,71,134,151,152,153,154,155,174,175,176,180]:
    MANUAL[n] = ('custody_administration_replacement', 'Custody/administrative agreement termination or replacement; excerpt does not establish cancellation of committed purchases or failed operational delivery under frozen rule.')
FINANCING = re.compile(r'credit agreement|credit facility|credit facilities|revolving credit|capped call|warrants|equity distribution|distribution agreement|loan agreement|letter of credit|lending facility|repurchase agreement|interest rate swap|credit and guaranty|credit commitments|loan and security|loan, guaranty|reimbursement agreement',re.I)
FIN_NAMES = {'AIG','AXP','BAC','BK','BLK','C','COF','GS','JPM','MET','MS','SCHW','USB','WFC'}

SOURCE_REVIEWS = [
 {'candidate_index':8, 'accession_number':'0001571996-24-000004',
  'url':'https://www.sec.gov/Archives/edgar/data/1571996/000157199624000004/dell-20240125.htm',
  'source_type':'Actual contemporaneous SEC 8-K, Item 1.02',
  'evidence_quote':'how the Company will act as a distributor of VMware products and services',
  'assessment':'Confirms Dell distributor role and termination, but no explicit committed-purchase cancellation. Not a qualifying event under SPEC.'},
 {'candidate_index':125, 'accession_number':'0001857154-25-000102',
  'url':'https://www.sec.gov/Archives/edgar/data/1857154/000185715425000102/dnut-20250623.htm',
  'source_type':'Actual contemporaneous SEC 8-K, Items 7.01 and 8.01',
  'assessment':'Confirms joint termination; does not show inability to perform contracted delivery with an adverse consequence to McDonald\'s.'},
 {'candidate_index':125, 'accession_number':'0001857154-25-000102',
  'url':'https://www.sec.gov/Archives/edgar/data/1857154/000185715425000102/a991pressrelease-june2025.htm',
  'source_type':'Actual contemporaneous Exhibit 99.1 joint press release',
  'evidence_quote':"Krispy Kreme represented a small, non-material part of McDonald’s breakfast business.",
  'assessment':'Supports exclusion; speculative material damage to McDonald\'s would contradict this exhibit.'},
]


def main():
    audit=[]
    for i,row in enumerate(ROWS):
        if i in MANUAL:
            reason, detail=MANUAL[i]
        elif set(row['potential_counterparties']) <= FIN_NAMES and FINANCING.search(row['supporting_text']):
            reason, detail='financing_or_equity','Explicit bank credit/financing/equity-distribution relationship, not the frozen operational supply/purchase action.'
        else:
            raise AssertionError(('Unreviewed candidate',i))
        audit.append(dict(candidate_index=i, **row, status='excluded_or_unvalidated',
                          exclusion_reason=reason, explanation=detail,
                          evidence_level='actual_SEC_document_review' if i in [8,125] else 'Massive_supporting_excerpt_screen'))
    for filename, value in [('candidate_audit.json',audit),('source_reviews.json',SOURCE_REVIEWS),('validated_events.json',[])]:
        (HERE/filename).write_text(json.dumps(value,indent=2))
    counts=Counter(a['exclusion_reason'] for a in audit)
    summary={
       'decision':'DO_NOT_PRICE_INSUFFICIENT_SOURCE_VALIDATED_EVENTS',
       'validated_events':0,'minimum_to_price':10,'unresolved_closest_candidate':'DELL -> AVGO, 2024-01-30; no explicit committed-purchase cancellation',
       'total_disclosure_rows':2052,'unique_accessions':len({r['accession_number'] for t in ['deal_termination','deal_breach_default','cybersecurity_incident','natural_disaster_impact','facility_closure'] for r in json.loads((HERE/'cache'/f'{t}.json').read_text())}),
       'potential_third_party_alias_rows':len(audit),'exclusion_counts':dict(counts),
       'actual_filings_reviewed':2,'actual_exhibits_reviewed':1,
       'no_returns_fetched':True,
       'coverage_limitation':'Alias screen searches vendor supporting excerpts, not every complete filing/exhibit. Parent/subsidiary aliases are incomplete. Thus zero validated events is not proof that the entire market contains zero eligible events.',
       'raw_cache':'cache/raw (ignored)',
       'spec_sha256':hashlib.sha256((HERE/'SPEC.txt').read_bytes()).hexdigest(),
    }
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
