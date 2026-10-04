"""Offline field-signature audit; never reads credentials or prints cached records."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CACHE = ROOT / 'massive/.massive_cache'
counts, keys_seen = Counter(), Counter()
dates = {}
examples = {}
borrow_fields = {'borrow_fee', 'borrow_rate', 'fee_rate', 'rebate_rate',
                 'lendable_inventory', 'lendable_shares', 'shortable_shares',
                 'locate_id', 'recall_date', 'loan_rate', 'loan_quantity'}
matches = []

def date_record(kind, value, divisor):
    try:
        day = datetime.fromtimestamp(value / divisor, timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return
    interval = dates.setdefault(kind, [day, day])
    interval[0] = min(interval[0], day)
    interval[1] = max(interval[1], day)

files = sorted(CACHE.glob('*.json'))
total_bytes = 0
for file in files:
    total_bytes += file.stat().st_size
    try:
        data = json.loads(file.read_bytes())
    except (ValueError, OSError):
        counts['unreadable'] += 1
        continue
    if not isinstance(data, dict):
        counts['non_object'] += 1
        continue
    results = data.get('results', [])
    if isinstance(results, dict): results = [results]
    if not results:
        counts['empty_results'] += 1
        continue
    first = results[0]
    if not isinstance(first, dict):
        counts['non_object_result'] += 1
        continue
    keys = set(first)
    keys_seen.update(keys)
    found = borrow_fields & (keys | set(data))
    if found: matches.append({'path': str(file.relative_to(ROOT)), 'fields': sorted(found)})
    if {'bid_price', 'ask_price'} <= keys:
        # A quote payload does not always retain the request ticker. Do not guess asset class.
        kind = 'nbbo_quote_payloads'
        for row in (first, results[-1]):
            date_record('nbbo_quote_utc_dates', row.get('sip_timestamp'), 1e9)
    elif {'strike_price', 'expiration_date', 'contract_type'} <= keys:
        kind = 'option_contract_payloads'
    elif {'ex_dividend_date', 'cash_amount'} <= keys:
        kind = 'dividend_payloads'
    elif {'split_from', 'split_to'} <= keys:
        kind = 'split_payloads'
    elif {'o', 'h', 'l', 'c', 't'} <= keys:
        kind = 'option_aggregate_payloads' if str(data.get('ticker', '')).startswith('O:') else 'other_aggregate_payloads'
        for row in (first, results[-1]): date_record(kind + '_utc_dates', row.get('t'), 1e3)
    elif 'filing_date' in keys:
        kind = 'filing_payloads'
    elif 'short_interest' in keys:
        kind = 'short_interest_payloads'
    elif 'short_volume' in keys:
        kind = 'short_volume_payloads'
    else:
        kind = 'other_payloads'
    counts[kind] += 1
    examples.setdefault(kind, str(file.relative_to(ROOT)))

out = {
    'as_of': '2026-10-03', 'scope': 'All immediate *.json files in massive/.massive_cache; only first result field signatures classified. Quote/aggregate date bounds inspect first and last records per payload.',
    'files': len(files), 'bytes': total_bytes, 'payload_counts': dict(counts),
    'date_bounds_utc': dates, 'example_paths': examples,
    'borrow_field_matches': matches, 'borrow_fields_searched': sorted(borrow_fields),
    'limitations': ['No credential files or environment variables read.',
                   'Zero recognized borrow fields is an inventory finding, not proof no lending information exists in every possible free-text disclosure.',
                   'Quote date coverage is not a synchronized stock/options panel, does not identify recall events, and does not establish executable size.',
                   'Asset class of quote payloads without request ticker is deliberately not guessed.',
                   'This script makes no network requests.'],
}
(HERE / 'cache_inventory.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps({k: out[k] for k in ['files', 'bytes', 'payload_counts', 'date_bounds_utc', 'borrow_field_matches']}, indent=2))
