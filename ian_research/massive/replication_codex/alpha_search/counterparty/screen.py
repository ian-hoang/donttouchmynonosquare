"""Frozen candidate fetch and auditable name screen. Does not fetch returns."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from massive.replication_codex import data

HERE = Path(__file__).resolve().parent
CACHE = HERE / 'cache'
data.RAW = CACHE / 'raw'
data.RAW.mkdir(parents=True, exist_ok=True)
TAGS = ['deal_termination', 'deal_breach_default', 'cybersecurity_incident',
        'natural_disaster_impact', 'facility_closure']


def fetch(tag):
    rows = data.get_all('/stocks/filings/8-K/vX/disclosures', {
        'tertiary_category': tag, 'filing_date.gte': '2024-01-01',
        'filing_date.lte': '2025-12-31', 'limit': 1000,
        'sort': 'filing_date.asc'})
    data.atomic_json(CACHE / (tag + '.json'), rows)
    return tag, rows


def main():
    all_rows = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch, tag) for tag in TAGS]
        for future in as_completed(futures):
            tag, rows = future.result()
            all_rows[tag] = rows
            print(tag, len(rows), flush=True)
    summary = {
        'fetched_utc': datetime.now(timezone.utc).isoformat(),
        'spec_sha256': hashlib.sha256((HERE / 'SPEC.txt').read_bytes()).hexdigest(),
        'category_counts': {t: len(all_rows[t]) for t in TAGS},
        'sample_field_names': {t: sorted(all_rows[t][0]) if all_rows[t] else [] for t in TAGS},
        'no_returns_fetched': True,
    }
    data.atomic_json(HERE / 'fetch_manifest.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
