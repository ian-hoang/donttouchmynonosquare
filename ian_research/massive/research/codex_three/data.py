"""Offline reconstruction of the existing top-100 disclosure survey; never read OOS."""
import hashlib
import json
import sys
from pathlib import Path
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'research'))
from count_events import TOP_100, CACHE_DIR


def disclosures():
    rows, seen = [], set()
    for ticker in TOP_100:
        for query in ([ticker, ticker.replace('.', '/')] if '.' in ticker else [ticker]):
            url = requests.Request('GET', 'https://api.massive.com/stocks/filings/8-K/vX/disclosures',
                params={'tickers': query, 'filing_date.gte': '2022-01-01',
                        'filing_date.lte': '2025-12-31', 'limit': 1000, 'sort': 'filing_date.asc'}).prepare().url
            while url:
                p = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + '.json')
                if not p.exists():
                    raise RuntimeError('Expected survey cache missing for ' + ticker)
                payload = json.loads(p.read_text())
                for r in payload.get('results', []):
                    if not '2024-01-01' <= r.get('filing_date', '')[:10] <= '2025-12-31':
                        continue
                    k = (r['accession_number'], r['tertiary_category'], r['supporting_text'])
                    if k not in seen:
                        seen.add(k)
                        rows.append(dict(r, ticker=ticker, universe_ticker=ticker))
                url = payload.get('next_url')
    return rows


if __name__ == '__main__':
    result = disclosures()
    print('In-sample disclosure rows:', len(result))
