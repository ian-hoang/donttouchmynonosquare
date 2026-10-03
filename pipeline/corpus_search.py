"""YouTube candidate search (flat, no media). Reproducible record of how the corpus was found.

Round 1 (data/manifest/candidates_raw.csv) used generic queries and skews to 2023-2026. Round 2 adds
year-specific queries for every CEO and every in-sample year so baselines and in-sample events exist.

Usage: python pipeline/corpus_search.py --years 2016-2024 --out data/manifest/candidates_years.csv [--workers 3]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ["{name} interview {year}", "{name} CNBC {year}", "{name} Bloomberg interview {year}",
             "{name} full interview {year}"]


def search(query: str, n: int = 40) -> list[dict]:
    r = subprocess.run([sys.executable, "-m", "yt_dlp", "--flat-playlist", "--dump-json", f"ytsearch{n}:{query}"],
                       capture_output=True, text=True, timeout=180)
    out = []
    for line in r.stdout.splitlines():
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.append({"video_id": j.get("id"), "title": j.get("title"), "channel": j.get("channel"),
                    "channel_id": j.get("channel_id"), "duration_s": j.get("duration"), "view_count": j.get("view_count"),
                    "query": query})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="2016-2024")
    ap.add_argument("--out", default=str(ROOT / "data" / "manifest" / "candidates_years.csv"))
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    y0, y1 = map(int, a.years.split("-"))
    uni = pd.read_csv(ROOT / "config" / "universe.csv", dtype=str)
    jobs = []
    for u in uni.itertuples():
        start = max(y0, int(str(u.tenure_start)[:4]), int(str(u.listed_start)[:4]))
        end = min(y1, int(str(u.tenure_end)[:4])) if isinstance(u.tenure_end, str) and u.tenure_end else y1
        for year in range(start, end + 1):
            for t in TEMPLATES:
                jobs.append((u.ceo_id, u.name, u.ticker, t.format(name=u.search_name, year=year)))
    print(len(jobs), "queries", flush=True)
    rows = []

    def run(job):
        ceo_id, name, ticker, q = job
        try:
            return [{**r, "ceo": name, "ceo_id": ceo_id, "ticker": ticker} for r in search(q)]
        except Exception as e:  # keep going; a failed query just yields nothing
            print("fail", q, str(e)[:80], flush=True)
            return []

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, res in enumerate(ex.map(run, jobs)):
            rows.extend(res)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(jobs)} queries, {len(rows)} hits", flush=True)
    df = pd.DataFrame(rows).drop_duplicates("video_id")
    df.to_csv(a.out, index=False)
    print("unique", len(df))


if __name__ == "__main__":
    main()
