"""Retrieve only public, contemporaneous 2024-25 SEC source documents.

The input universe is frozen candidate manifests; this never fetches prices,
Massive authenticated endpoints, or 2026 disclosures. Raw sources are cached.
"""
import hashlib
import html
import json
import os
import re
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE.parents[1] / '.massive_cache' / 'codex_six'
CACHE.mkdir(parents=True, exist_ok=True)


def extract(raw):
    docs = re.findall(r'<DOCUMENT>(.*?)</DOCUMENT>', raw, re.S | re.I)
    chosen = []
    for doc in docs:
        typ = re.search(r'<TYPE>([^\r\n]+)', doc, re.I)
        typ = typ.group(1).strip() if typ else ''
        if not (typ.startswith('8-K') or typ.startswith('EX-99')):
            continue
        filename = re.search(r'<FILENAME>([^\r\n]+)', doc, re.I)
        body = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', ' ', doc, flags=re.S | re.I)
        body = re.sub(r'</(?:p|div|tr|td|th|li|h[1-6])>|<br\s*/?>', '\n', body, flags=re.I)
        body = html.unescape(re.sub(r'<[^>]+>', ' ', body))
        body = '\n'.join(' '.join(line.split()) for line in body.splitlines() if line.strip())
        chosen.append({'type': typ, 'filename': filename.group(1).strip() if filename else '', 'text': body})
    return chosen


def main():
    byacc = {}
    for name in ('guidance', 'noncash'):
        for row in json.loads((HERE / f'{name}_candidates.json').read_text()):
            byacc[row['accession_number']] = row
    session = requests.Session()
    session.headers['User-Agent'] = os.environ.get('SEC_USER_AGENT', 'GQH academic research')
    manifest = []
    for i, (acc, row) in enumerate(sorted(byacc.items())):
        assert '2024-01-01' <= row['filing_date'][:10] <= '2025-12-31'
        url = row['filing_url']
        rawpath = CACHE / f'{acc}.txt'
        result = {'accession_number': acc, 'ticker': row['ticker'], 'filing_date': row['filing_date'], 'url': url}
        try:
            if rawpath.exists():
                raw = rawpath.read_text(errors='replace')
                result['status'] = 'cached'
            else:
                response = session.get(url, timeout=30)
                result['http_status'] = response.status_code
                response.raise_for_status()
                raw = response.text
                if '<DOCUMENT>' not in raw:
                    raise ValueError('not an SEC submission document')
                rawpath.write_text(raw)
                result['status'] = 'retrieved'
                time.sleep(0.25)
            result['sha256'] = hashlib.sha256(raw.encode()).hexdigest()
            result['documents'] = extract(raw)
            (CACHE / f'{acc}.parsed.json').write_text(json.dumps(result, indent=2))
        except Exception as exc:
            result['status'] = 'failed'
            result['error'] = type(exc).__name__ + ': ' + str(exc)
        manifest.append({k: v for k, v in result.items() if k != 'documents'})
        print(i + 1, len(byacc), row['ticker'], acc, result['status'], flush=True)
    (HERE / 'guidance_source_manifest.json').write_text(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
