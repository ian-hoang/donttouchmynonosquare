"""Offline, price-blind liquidity-runway event extraction for the 2024-2025 study.

This is an auditable human-labelled pilot, not an automated language classifier.
Annotations were frozen before reading option prices or returns. The program joins
those annotations to the original supporting text and rejects unannotated filings.
No HTTP requests, credentials, option prices, or 2026 data are used.

Run: python liquidity.py --input /tmp/gqh_massive_2024_2025_disclosures.json
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path('/tmp/gqh_massive_2024_2025_disclosures.json'))
    parser.add_argument('--output-dir', type=Path, default=HERE)
    args = parser.parse_args()
    raw_bytes = args.input.read_bytes()
    raw = json.loads(raw_bytes)
    if isinstance(raw, dict):
        raw = raw['results']
    spec_bytes = (HERE / 'liquidity_spec.json').read_bytes()
    annotations = json.loads((HERE / 'liquidity_annotations.json').read_text())
    grouped = collections.defaultdict(list)
    for r in raw:
        if '2024-01-01' <= r['filing_date'] <= '2025-12-31':
            grouped[r['accession_number']].append(r)
    candidates = {acc: rows for acc, rows in grouped.items()
                  if any(r['tertiary_category'] == 'credit_facility' for r in rows)}
    screened = []
    for accession, rows in sorted(candidates.items(), key=lambda item:(item[1][0]['filing_date'], item[1][0]['universe_ticker'])):
        r = rows[0]
        label = annotations.get(accession, {'eligible':False,'reason_code':'unannotated','reason':'No frozen price-blind annotation; reject.'})
        assert label.get('expected_ticker', r['universe_ticker']) == r['universe_ticker']
        assert label.get('expected_date', r['filing_date']) == r['filing_date']
        sources = []
        for prior_acc in label.get('prior_accessions', []):
            prior_rows = grouped[prior_acc]
            assert all(x['filing_date'] < r['filing_date'] for x in prior_rows), 'Future source prohibited'
            sources.append({'accession_number':prior_acc,'filing_date':prior_rows[0]['filing_date'],
                            'filing_url':prior_rows[0]['filing_url'],
                            'supporting_text':[x['supporting_text'] for x in prior_rows]})
        entry = {'strategy_id':'liquidity_runway_v1','ticker':r['universe_ticker'],
                 'issuer':r['universe_ticker'],'cik':r['cik'],'filing_date':r['filing_date'],
                 'date':r['filing_date'],'accession_number':accession,'source_url':r['filing_url'],
                 'filing_url':r['filing_url'],'supporting_text':[x['supporting_text'] for x in rows],
                 'same_filing_tags':sorted({x['tertiary_category'] for x in rows}),
                 'prior_source_records':sources, **label}
        if entry['eligible']:
            assert entry['facilities']
            assert all(x['new_capacity_usd'] >= x['old_capacity_usd'] > 0 for x in entry['facilities'])
            assert entry['effective_by_filing'] is True
            assert not set(entry['same_filing_tags']) & {'acquisition_agreement','acquisition_completion','merger_agreement'}
        screened.append(entry)
    eligible = [r for r in screened if r['eligible']]
    # Candidate source currently has one accession per issuer/date; never silently double count.
    assert len({(r['ticker'],r['filing_date']) for r in eligible}) == len(eligible)
    meta = {'strategy_id':'liquidity_runway_v1', 'window':['2024-01-01','2025-12-31'],
            'spec_sha256':hashlib.sha256(spec_bytes).hexdigest(),
            'input_sha256':hashlib.sha256(raw_bytes).hexdigest(),
            'input_rows':len(raw),
            'credit_disclosure_rows':sum(x['tertiary_category']=='credit_facility' for rows in candidates.values() for x in rows),
            'screened_filing_events':len(screened),
            'screened_issuers':len({r['ticker'] for r in screened}),
            'eligible_events':len(eligible),'eligible_issuers':len({r['ticker'] for r in eligible}),
            'rejection_counts':dict(collections.Counter(r['reason_code'] for r in screened if not r['eligible'])),
            'price_data_read':False,'out_of_sample_data_read':False,
            'method':'Frozen human annotations joined to historical sponsor excerpts; supporting text is not independently checked against full SEC exhibit.',
            'selected_events_are_not_trade_fills':True}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'liquidity_events.json').write_text(json.dumps({'metadata':meta,'events':eligible}, indent=2)+'\n')
    (args.output_dir / 'liquidity_screened.json').write_text(json.dumps({'metadata':meta,'screened':screened}, indent=2)+'\n')
    print(json.dumps(meta, indent=2))
    for r in eligible:
        print(r['ticker'],r['filing_date'],r['reason'])

if __name__ == '__main__':
    main()
