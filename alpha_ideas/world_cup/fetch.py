"""Step 1 — download match data and ETF prices/dividends for the World Cup test (PREREGISTRATION.md).

Run from the repo root:  uv run python alpha_ideas/world_cup/fetch.py
Cached under data/cache/world_cup/ (gitignored). Public data: openfootball/worldcup.json, martj42/international_results.
Prices and dividends: Massive (the user's key).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "alpha_ideas" / "ai_washing"))
from common import massive_all, massive_get  # noqa: E402  (shared Massive helpers, read-only use)

CACHE = ROOT / "data" / "cache" / "world_cup"
CACHE.mkdir(parents=True, exist_ok=True)
YEARS = [2006, 2010, 2014, 2018, 2022, 2026]
ETFS = ["EWG", "EWU", "EWQ", "EWP", "EWI", "EWN", "EWK", "EWL", "EWD", "EWO", "EDEN", "NORW", "EPOL", "PGAL",
        "GREK", "TUR", "RSX", "EIRL", "SPY", "EWC", "EWW", "EWZ", "ARGT", "ECH", "GXG", "COLO", "EPU", "EWJ", "EWY",
        "EWA", "KSA", "QAT", "ENZL", "EZA", "EGPT", "NGE"]


def curl(url: str, path: Path) -> None:
    if not path.exists():
        subprocess.run(["curl", "-sf", "-o", str(path), url], check=True)


def main():
    for y in YEARS:
        curl(f"https://raw.githubusercontent.com/openfootball/worldcup.json/master/{y}/worldcup.json",
             CACHE / f"openfootball_{y}.json")
    for f in ["results.csv", "shootouts.csv"]:
        curl(f"https://raw.githubusercontent.com/martj42/international_results/master/{f}", CACHE / f"martj42_{f}")

    for t in ETFS:
        path = CACHE / f"aggs_{t}.json"
        if not path.exists():
            rows = massive_all(f"/v2/aggs/ticker/{t}/range/1/day/2005-01-01/2026-09-30",
                               {"adjusted": "true", "sort": "asc", "limit": 50000})
            path.write_text(json.dumps(rows))
        for kind, params in [("dividends", {"ticker": t, "limit": 1000}), ("splits", {"ticker": t, "limit": 1000})]:
            p = CACHE / f"{kind}_{t}.json"
            if not p.exists():
                p.write_text(json.dumps(massive_all(f"/v3/reference/{kind}", params)))
        rows = json.loads(path.read_text())
        divs = json.loads((CACHE / f"dividends_{t}.json").read_text())
        first = pd.to_datetime(rows[0]["t"], unit="ms").date() if rows else None
        last = pd.to_datetime(rows[-1]["t"], unit="ms").date() if rows else None
        print(f"{t:5s} bars {len(rows):5d}  {first} -> {last}  dividends {len(divs)}")


if __name__ == "__main__":
    main()
