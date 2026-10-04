"""Estimate (default) or explicitly download one fixed contract's MBO history."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gqh import CACHE, data  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("symbol", help="verified raw outright symbol, e.g. ESZ6; not a continuous ticker")
    p.add_argument("start", help="fixed UTC date at midnight, to include MBO snapshot")
    p.add_argument("end", help="exclusive fixed UTC end date/time")
    p.add_argument("--download", action="store_true", help="spend credits, subject to GQH_MAX_COST_USD")
    args = p.parse_args()
    request = dict(dataset="GLBX.MDP3", symbols=[args.symbol], schema="mbo", start=args.start,
                   end=args.end, stype_in="raw_symbol")
    estimate = data.price(**request)
    print(f"Estimate: ${estimate['usd']:.4f}, {estimate['gb']:.4f} GB billable")
    if args.download:
        data.databento(**request)
        key = hashlib.sha1(json.dumps(request, sort_keys=True).encode()).hexdigest()[:12]
        print(f"DBN: {CACHE / f'GLBX.MDP3_mbo_{key}.dbn.zst'}")
    else:
        print("No download. Add --download to fetch under the existing credit guard.")


if __name__ == "__main__":
    main()
