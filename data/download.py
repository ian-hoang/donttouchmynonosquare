"""Download the data a strategy needs (judges run this with their own Databento key).

    uv run python data/download.py <strategy>

It calls the strategy's load(), which fetches from Databento into data/cache/ (gitignored) and refuses
any single request above GQH_MAX_COST_USD. Licensed raw data is never committed to the repo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import strategies  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    strategies.get(sys.argv[1]).load()
    print("Data ready in data/cache/")
