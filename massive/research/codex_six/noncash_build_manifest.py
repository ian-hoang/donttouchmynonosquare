"""Replay frozen manual source annotations; never reads outcome data."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Reviewed against every candidate's contemporaneous supporting text. Full SEC
# originals were additionally reviewed for the two accepted cases and BSBY.
DECISIONS = {
 '0001140361-24-040659': ('control', 'Actual tax charge following legal decision; no affirmative mechanical/no-new-cash evidence.'),
 '0001551152-25-000002': ('unclassified', 'Acquired R&D/milestone expense; supporting text does not establish mechanical cause or no new cash obligation.'),
 '0001551152-25-000006': ('control', 'Drug intangible impairment explicitly follows revised cash flows; not merely accounting presentation.'),
 '0001551152-25-000023': ('unclassified', 'Acquired R&D/milestone expense; supporting text does not establish mechanical cause or no new cash obligation.'),
 '0000012927-25-000041': ('control', 'Criminal monetary penalty includes remaining cash payment.'),
 '0000070858-24-000006': ('unclassified', 'Full 8-K confirms technical BSBY hedge-accounting cessation and later income reversal, but only nominal economic impact is stated, cash terms change, and CET1 falls 8bp. Strict unchanged-cash/no-new-obligation evidence is insufficient.'),
 '0000070858-24-000027': ('control', 'Repeats previously disclosed BSBY charge alongside an actual FDIC special assessment; not a new isolated mechanical charge.'),
 '0001104659-24-002981': ('control', 'FX translation loss accompanies actual FDIC assessment; Argentina devaluation changes economics. Not an isolated harmless accounting adjustment.'),
 '0001104659-25-092977': ('control', 'Goodwill write-down follows a transaction bid below carrying value; actual asset-value evidence, not purely mechanical.'),
 '0001104659-25-124865': ('unclassified', 'Mixed held-for-sale loss includes translation and actual disposal economics; no affirmative unchanged-obligation statement in available evidence.'),
 '0000093410-24-000002': ('control', 'Lower expected investment and inherited decommissioning obligations imply real operating/cash effects.'),
 '0000093410-25-000098': ('control', 'Severance and transaction costs explicitly generate cash outflows.'),
 '0001193125-24-049404': ('control', 'Business fair-value and goodwill write-downs associated with disposal; noncash alone does not establish harmlessness.'),
 '0001193125-24-270298': ('control', 'New China JV forecast, plant closures and restructuring reflect explicit deterioration.'),
 '0001467858-25-000136': ('control', 'EV demand/capacity realignment and contract cancellation fees include explicit cash impact.'),
 '0001652044-25-000074': ('control', 'Actual regulatory fine and cease-and-desist order.'),
 '0000050863-24-000147': ('control', 'Exit of manufacturing capabilities and leased assets; explicit operating restructuring.'),
 '0000050863-25-000107': ('control', 'Exit of business lines and real estate; explicit operating change.'),
 '0000200406-24-000048': ('control', 'Incremental reserve funds actual litigation settlements.'),
 '0000019617-24-000330': ('unclassified', 'Gain rather than loss; outside frozen signal.'),
 '0000066740-25-000046': ('control', 'Settlement payments explicitly extend through 2050; real future cash obligations.'),
 '0001193125-24-275524': ('control', 'Cruise investment impaired because development funding ceased; real deterioration.'),
 '0000080424-24-000015': ('control', 'Gillette intangible carrying value reduced; available evidence does not establish purely technical cause.'),
 '0000080424-25-000050': ('control', 'Restructuring program explicitly includes predominantly cash charges.'),
 '0001413329-24-000160': ('control', 'Actual disposal loss with working-capital adjustments; no purely technical/no-new-cash support.'),
 '0000101829-24-000031': ('control', 'Settlement installments are cash payments.'),
 '0000101829-24-000033': ('control', 'Penalties, forfeiture and restitution require specified near-term payments.'),
 '0000829224-25-000067': ('control', 'Store closures, employee separations and lease costs; explicit operating/cash consequences.'),
 '0000316709-24-000011': ('control', 'Mixed restructuring/acquisition integration costs and amortization; not isolated technical loss.'),
 '0000092122-24-000091': ('control', 'Impairment of discontinued development project.'),
 '0000732717-24-000004': ('unclassified', 'Mixed pension remeasurement and restructuring/impairment; available evidence lacks affirmative unchanged-cash statement for an isolated adjustment.'),
 '0000732717-24-000016': ('control', 'Held-for-sale and equity-investment impairment accompanies deployment restructuring; no isolated mechanical cause.'),
 '0000732717-25-000005': ('control', 'Mixed prior goodwill impairment, restructuring and pension remeasurement; not new isolated mechanical disclosure.'),
 '0000732712-24-000003': ('control', 'Business-unit fair value below carrying value; noncash designation alone does not pass.'),
 '0000732712-24-000007': ('control', 'Previously disclosed cessation of asset use and transformation; real operating change and repeated event.'),
 '0000732712-24-000015': ('unclassified', 'Pension settlement credit rather than loss; outside frozen signal.'),
 '0000732712-24-000025': ('control', 'Repeats prior asset-use cessation; not a new mechanical charge.'),
 '0000732712-24-000062': ('control', 'Employee separations and business exits have operating/cash implications.'),
 '0000732712-25-000003': ('control', 'Repeats prior employee separations and business exits.'),
 '0000320187-25-000053': ('unclassified', 'Correction of overstated product purchase obligations, not an actual noncash loss.'),
}


def main():
    rows = json.loads((HERE / 'noncash_candidates.json').read_text())
    groups = {}
    for r in rows:
        groups.setdefault(r['accession_number'], []).append(r)
    doc = json.loads((HERE / 'noncash_events.json').read_text())
    accepted = {r['accession_number'] for r in doc['events']}
    assert set(groups) == set(DECISIONS) | accepted
    doc['controls'], doc['unclassified'] = [], []
    audit = []
    for acc, g in sorted(groups.items()):
        r = g[0]
        if acc in accepted:
            d = next(x for x in doc['events'] if x['accession_number'] == acc)
            status = 'economic_signal'
        else:
            status, reason = DECISIONS[acc]
            d = {k: r[k] for k in ('ticker','filing_date','accession_number')}
            d.update(signal='other_charge_control' if status == 'control' else 'unclassified',
                     strategy='cash_secured_put', reason=reason,
                     sources=[r['filing_url']],
                     supporting_text=[x['supporting_text'] for x in g],
                     review_scope='All cached contemporaneous supporting-text rows reviewed; rejection may be established directly from this evidence. Full source required for any accepted event.')
            if acc == '0000070858-24-000006':
                d['sources'].append('https://www.sec.gov/Archives/edgar/data/70858/000007085824000006/bac-20240108.htm')
                d['review_scope'] = 'Full contemporaneous SEC 8-K reviewed via web.'
            doc['controls' if status == 'control' else 'unclassified'].append(d)
        audit.append(dict(d, classification=status))
    doc['status'] = 'economic_signal_audit_complete_price_gate_not_applied'
    doc['audit_counts'] = {'candidate_rows':len(rows),'candidate_filings':len(groups),'economic_signals':len(doc['events']),'controls':len(doc['controls']),'unclassified':len(doc['unclassified'])}
    doc['limitations'] = ['Two economic events cannot establish statistical alpha.', 'Richness gate not applied here.', 'No quotes, prices, or 2026 outcomes accessed.', 'Controls are heterogeneous and some repeat previous announcements; do not treat as an exchangeable causal-control sample without additional matching.']
    (HERE / 'noncash_events.json').write_text(json.dumps(doc,indent=2))
    (HERE / 'noncash_audit.json').write_text(json.dumps(audit,indent=2))
    print(doc['audit_counts'])


if __name__ == '__main__':
    main()
