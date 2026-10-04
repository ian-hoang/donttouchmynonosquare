"""Reconcile saved strict quotes, execution formulas and frozen draw memberships."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics

from .strict import HERE, SOURCE, cutoff, digest, save, validate_quote


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), (a,b)


def main():
    spec = json.loads((HERE / 'SPEC.json').read_text())
    for name, expected in spec['source_hashes'].items():
        assert digest(SOURCE/name) == expected
    original_code = digest(HERE/'strict.py') == spec['code_sha256']
    if not original_code:
        amendment = json.loads((HERE/'reporting_amendment.json').read_text())
        assert amendment['original_code_sha256'] == spec['code_sha256']
        assert amendment['updated_code_sha256'] == digest(HERE/'strict.py')
    sets = {}
    valid_count = 0
    quote_count = 0
    for kind in ['event','peer']:
        source = {(r['ticker'],r['filing_date']):r for r in json.loads((SOURCE/(kind+'_results.json')).read_text())
                   if r['status']=='valid'}
        current = {(r['ticker'],r['filing_date']):r for r in json.loads((HERE/(kind+'_results.json')).read_text())}
        assert set(current) == set(source)
        for key,row in current.items():
            assert row['status'] != 'api_error', row
            old = source[key]
            for name in ['ticker','filing_date','entry','exit','sold_call','strike','expiry','entry_spot']:
                assert row[name] == old[name], (key,name)
            for which,day in [('entry',row['entry']),('exit',row['exit'])]:
                q = row[which+'_quote']
                if q is None:
                    assert row[which+'_rejection']
                    continue
                converted=dict(sip_timestamp=q['timestamp'],bid_price=q['bid'],ask_price=q['ask'],
                               bid_size=q['bid_size'],ask_size=q['ask_size'])
                checked, reason = validate_quote(converted,cutoff(day))
                assert reason is None
                close(checked['age_seconds'],q['age_seconds'])
                quote_count += 1
            if row['status'] != 'valid':
                continue
            en,ex,s = row['entry_quote'],row['exit_quote'],row['entry_spot']
            close(row['short_net'],(en['bid']-ex['ask']-.013)/s)
            close(row['long_net'],(ex['bid']-en['ask']-.013)/s)
            close(row['short_net'],row['mid_gross']-row['cost'])
            close(row['short_net']+row['long_net'],-2*row['cost'])
            valid_count += 1
        sets[kind]=current
    draws={(d['seed'],d['filing_date']):d['tickers'] for d in json.loads((SOURCE/'peer_draws.json').read_text())}
    pairs=json.loads((HERE/'peer_pairs.json').read_text())
    for row in pairs:
        ev=sets['event'][(row['ticker'],row['filing_date'])]
        expected=[sets['peer'][(t,row['filing_date'])] for t in draws[(row['seed'],row['filing_date'])]
                  if (t,row['filing_date']) in sets['peer'] and sets['peer'][(t,row['filing_date'])]['status']=='valid']
        assert ev['status']=='valid'
        assert row['peer_tickers']==[p['ticker'] for p in expected]
        assert 1 <= row['peer_count'] == len(expected) <= 6
        close(row['diagnostic_gap'],ev['short_net']-statistics.mean(p['short_net'] for p in expected))
        close(row['actual_pair_net'],ev['short_net']+statistics.mean(p['long_net'] for p in expected))
        close(row['actual_pair_per_gross_notional'],row['actual_pair_net']/2)
    summary=dict(passed=True,checked_at_utc=datetime.now(timezone.utc).isoformat(),
                 events=len(sets['event']),peers=len(sets['peer']),valid_trades=valid_count,
                 valid_quotes=quote_count,event_seed_pairs=len(pairs),
                 frozen_sources_unchanged=True,spec_code_unchanged=original_code,
                 reporting_only_amendment_applied=not original_code)
    save(HERE/'verification.json',summary)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
