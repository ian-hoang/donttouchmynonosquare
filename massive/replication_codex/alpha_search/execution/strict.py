"""Frozen execution diagnostic of already selected acquisition events and peers."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import threading
import time
from zoneinfo import ZoneInfo

from massive.replication_codex.data import session

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / 'cache'
CACHE = HERE / 'cache'
RAW = CACHE / 'raw'
EARLY = {'2024-07-03', '2024-11-29', '2024-12-24',
         '2025-07-03', '2025-11-28', '2025-12-24',
         '2026-11-27', '2026-12-24'}
COMMISSION = .013


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f'.{threading.get_ident()}.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False))
    tmp.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cutoff(day):
    hour = 12 if day in EARLY else 15
    return datetime.fromisoformat(day).replace(hour=hour, minute=55,
                  tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)


def validate_quote(q, at):
    if not q:
        return None, 'no_quote'
    try:
        ts = int(q['sip_timestamp'])
        bid, ask = float(q['bid_price']), float(q['ask_price'])
        bs, az = float(q['bid_size']), float(q['ask_size'])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, 'missing_or_invalid_fields'
    if not all(math.isfinite(v) for v in [bid, ask, bs, az]):
        return None, 'nonfinite_quote'
    age = (int(at.timestamp()) * 1_000_000_000 - ts) / 1e9
    if not 0 <= age <= 300:
        return None, 'quote_stale_or_future'
    if not 0 <= bid <= ask or ask <= 0:
        return None, 'invalid_market'
    if min(bs, az) < 1:
        return None, 'no_displayed_size'
    return dict(bid=bid, ask=ask, bid_size=bs, ask_size=az,
                timestamp=ts, age_seconds=age, cutoff=at.isoformat()), None


def fetch_quote(contract, day):
    at = cutoff(day)
    params = {'timestamp.lte': at.strftime('%Y-%m-%dT%H:%M:%SZ'),
              'order': 'desc', 'sort': 'timestamp', 'limit': 1}
    path = '/v3/quotes/' + contract
    key = hashlib.sha256(json.dumps([path, params], sort_keys=True).encode()).hexdigest()
    dest = RAW / (key + '.json')
    if dest.exists():
        payload = json.loads(dest.read_text())
    else:
        for attempt in range(7):
            try:
                r = session().get('https://api.massive.com' + path, params=params, timeout=40)
            except Exception:
                if attempt == 6:
                    raise RuntimeError('network_failure') from None
                time.sleep(min(2 ** attempt, 8))
                continue
            if r.status_code in [429, 500, 502, 503, 504]:
                if attempt == 6:
                    raise RuntimeError('transient_http_' + str(r.status_code))
                time.sleep(min(2 ** attempt, 8))
                continue
            if r.status_code != 200:
                raise RuntimeError('http_' + str(r.status_code))
            payload = r.json()
            save(dest, payload)
            break
    rows = payload.get('results') or []
    return validate_quote(rows[0] if rows else None, at)


def evaluate(row):
    result = {k: row[k] for k in ['ticker', 'filing_date', 'entry', 'exit',
                                  'sold_call', 'strike', 'expiry', 'entry_spot']}
    result.update(status='dropped', legacy_net=row['net'])
    try:
        entry, er = fetch_quote(row['sold_call'], row['entry'])
        leave, xr = fetch_quote(row['sold_call'], row['exit'])
    except RuntimeError as e:
        result.update(status='api_error', drop_reason=str(e))
        return result
    result.update(entry_quote=entry, exit_quote=leave,
                  entry_rejection=er, exit_rejection=xr)
    if er or xr:
        result['drop_reason'] = ';'.join(x for x in [
            'entry:' + er if er else '', 'exit:' + xr if xr else ''] if x)
        return result
    spot = row['entry_spot']
    if not math.isfinite(spot) or spot <= 0:
        raise ValueError('invalid frozen denominator')
    result.update(status='valid', drop_reason=None,
       short_net=(entry['bid']-leave['ask']-COMMISSION)/spot,
       long_net=(leave['bid']-entry['ask']-COMMISSION)/spot,
       mid_gross=((entry['bid']+entry['ask'])/2-(leave['bid']+leave['ask'])/2)/spot,
       cost=((entry['ask']-entry['bid']+leave['ask']-leave['bid'])/2+COMMISSION)/spot)
    return result


def stats(values):
    if not values:
        return {'n': 0}
    sd = statistics.stdev(values) if len(values) > 1 else None
    return dict(n=len(values), mean=statistics.mean(values), median=statistics.median(values),
                std=sd, per_trade_sharpe=statistics.mean(values)/sd if sd else None,
                win_rate=sum(v > 0 for v in values)/len(values), min=min(values), max=max(values))


def window(row):
    return '2024_2025' if row['filing_date'] < '2026-01-01' else '2026_reused'


def seed_summary(values):
    # Seed means share the same event returns; their dispersion is not a
    # strategy-return distribution and must not receive a Sharpe ratio.
    return dict(n=len(values), mean=statistics.mean(values), median=statistics.median(values),
                min=min(values), max=max(values), positive_seeds=sum(v > 0 for v in values))


def stage(label, workers):
    source = SOURCE / (label + '_results.json')
    rows = [r for r in json.loads(source.read_text()) if r['status'] == 'valid']
    output = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(evaluate, row) for row in rows]
        for future in as_completed(futures):
            output.append(future.result())
            if len(output) % 100 == 0:
                print(f'{label}: {len(output)}/{len(rows)}', flush=True)
    output.sort(key=lambda r: (r['filing_date'], r['ticker']))
    save(HERE / (label + '_results.json'), output)
    summary = {}
    for period in ['2024_2025', '2026_reused']:
        subset = [r for r in output if window(r) == period]
        valid = [r for r in subset if r['status'] == 'valid']
        summary[period] = dict(requested=len(subset), statuses=dict(Counter(r['status'] for r in subset)),
            short=stats([r['short_net'] for r in valid]),
            legacy_same_cohort=stats([r['legacy_net'] for r in valid]),
            dropped=dict(Counter(r['drop_reason'] for r in subset if r['status'] != 'valid')))
    save(HERE / (label + '_summary.json'), summary)
    print(json.dumps({label: summary}, indent=2), flush=True)
    return output


def compare():
    events = [r for r in json.loads((HERE / 'event_results.json').read_text()) if r['status'] == 'valid']
    peers = {(r['ticker'], r['filing_date']): r for r in json.loads((HERE / 'peer_results.json').read_text())
             if r['status'] == 'valid'}
    draws = {(r['seed'], r['filing_date']): r['tickers']
             for r in json.loads((SOURCE / 'peer_draws.json').read_text())}
    pairs = []
    for event in events:
        for seed in range(20):
            names = draws[(seed, event['filing_date'])]
            eligible = [peers[(t, event['filing_date'])] for t in names if (t, event['filing_date']) in peers]
            if not eligible:
                continue
            short_mean = statistics.mean(p['short_net'] for p in eligible)
            long_mean = statistics.mean(p['long_net'] for p in eligible)
            pairs.append(dict(ticker=event['ticker'], filing_date=event['filing_date'], seed=seed,
                 period=window(event), peer_count=len(eligible), peer_tickers=[p['ticker'] for p in eligible],
                 event_short=event['short_net'], peer_short_mean=short_mean, peer_long_mean=long_mean,
                 diagnostic_gap=event['short_net']-short_mean,
                 actual_pair_net=event['short_net']+long_mean,
                 actual_pair_per_gross_notional=(event['short_net']+long_mean)/2))
    save(HERE / 'peer_pairs.json', pairs)
    output = {}
    for period in ['2024_2025', '2026_reused']:
        seeds = []
        for seed in range(20):
            rows = [p for p in pairs if p['period'] == period and p['seed'] == seed]
            seeds.append(dict(seed=seed, diagnostic_gap=stats([r['diagnostic_gap'] for r in rows]),
                        actual_pair_net=stats([r['actual_pair_net'] for r in rows]),
                        actual_pair_per_gross_notional=stats([r['actual_pair_per_gross_notional'] for r in rows]),
                        mean_peer_count=statistics.mean(r['peer_count'] for r in rows) if rows else None))
        output[period] = {'seeds': seeds,
            'diagnostic_seed_means': seed_summary([r['diagnostic_gap']['mean'] for r in seeds if r['diagnostic_gap']['n']]),
            'actual_pair_seed_means': seed_summary([r['actual_pair_net']['mean'] for r in seeds if r['actual_pair_net']['n']])}
    save(HERE / 'comparison_summary.json', output)
    print(json.dumps({k: {m:v for m,v in vals.items() if m != 'seeds'} for k,vals in output.items()}, indent=2))


def freeze():
    path = HERE / 'SPEC.json'
    if path.exists():
        old = json.loads(path.read_text())
        if old['source_hashes'] != {n:digest(SOURCE/n) for n in old['source_hashes']}:
            raise ValueError('Frozen source changed')
        return
    save(path, dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        description='Execution diagnostic of unchanged 45 valid event trades and 2300 valid peer trades.',
        contracts='Preserve selected contract, dates, expiry, strike and original parity denominator. No tuning.',
        execution='Latest SIP quote at or before five minutes before actual session close; age 0..300 seconds; finite 0<=bid<=ask and ask>0, bid_size and ask_size >=1; reject invalid latest without searchback.',
        early_closes=sorted(EARLY), commission_per_option_share_round_trip=COMMISSION,
        short_formula='(entry bid - exit ask - 0.013) / frozen entry parity spot',
        long_formula='(exit bid - entry ask - 0.013) / frozen entry parity spot',
        primary_diagnostic='event short minus average valid quiet-peer short, preserve 20 frozen draw memberships; drop missing peers without replacement; pair only if >=1 valid peer.',
        economic_candidate='event short plus average valid peer long, both bid/ask crossings. Raw net per one event-stock notional plus one peer-stock notional; divide by 2 for total gross notional.',
        caveats=['2026 already seen; no independent holdout claim.',
                 'Peer quiet filter used future filings within five days and is retrospective.',
                 'Underlying notionals do not beta/delta/vega-match options; denominators retain stale parity assumptions.',
                 'Latest quote and displayed size are a small-size crossing simulation, not guaranteed execution.',
                 'No margin funding, dividends, assignment, early exercise or market impact model.',
                 'Conditioned on original valid-event/peer cohort; no recovery of original rejected trades.'],
        source_hashes={n:digest(SOURCE/n) for n in ['event_results.json','peer_results.json','peer_draws.json']},
        code_sha256=digest(Path(__file__))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['events', 'peers', 'compare', 'all', 'freeze'], default='events')
    parser.add_argument('--workers', type=int, default=16)
    args = parser.parse_args()
    freeze()
    if args.stage in ['events', 'all']:
        stage('event', args.workers)
    if args.stage in ['peers', 'all']:
        stage('peer', args.workers)
    if args.stage in ['compare', 'all']:
        compare()
