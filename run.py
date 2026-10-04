"""Explore a strategy on IN-SAMPLE data only. Every run is logged to results/ledger.csv.

    uv run python run.py                                   # list strategies
    uv run python run.py my_idea                           # defaults
    uv run python run.py my_idea --set lookback=120 vol_target=0.1
    uv run python run.py my_idea --sweep lookback=20,60,120 vol_target=0,0.1   # every combination
    uv run python run.py my_idea --cost-mult 2             # stress costs
    uv run python run.py my_idea --plot                    # equity curves -> results/explore/my_idea.png
"""
import argparse
import ast
import itertools

import strategies
from gqh import RESULTS, ledger, metrics, report, research


def parse_value(text: str):
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return text


def parse_sets(items) -> dict:
    out = {}
    for item in items:
        key, _, value = item.partition("=")
        out[key] = parse_value(value)
    return out


def build_grid(sweeps) -> list[dict]:
    """["a=1,2", "b=x,y"] -> every combination as a list of dicts."""
    if not sweeps:
        return [{}]
    keys, choices = [], []
    for item in sweeps:
        key, _, values = item.partition("=")
        keys.append(key)
        choices.append([parse_value(v) for v in values.split(",")])
    return [dict(zip(keys, combo)) for combo in itertools.product(*choices)]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("strategy", nargs="?")
    p.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE")
    p.add_argument("--sweep", nargs="*", default=[], metavar="KEY=V1,V2")
    p.add_argument("--cost-mult", type=float, default=1.0)
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    if not args.strategy:
        print("Strategies:", ", ".join(strategies.available()) or "none yet (copy strategies/_template.py)")
        return

    strat = strategies.get(args.strategy)
    hyp = research.hypothesis_status(strat)
    if not hyp["committed"]:
        state = "isn't committed yet" if hyp["exists"] else "doesn't exist yet"
        print(f"WARNING: {hyp['path']} {state}. Commit your hypothesis before backtesting; "
              "judges use the commit time as proof it came first.\n")

    prep = research.prepare(strat)
    print(f"{strat.name}: in-sample ends before {prep.oos_start:%Y-%m-%d} (out-of-sample locked)\n")

    base = parse_sets(args.set)
    rows, curves = {}, {}
    for overrides in build_grid(args.sweep):
        res, m = research.evaluate(strat, prep.in_sample, {**base, **overrides}, args.cost_mult)
        label = ", ".join(f"{k}={v}" for k, v in overrides.items()) or "defaults"
        rows[label], curves[label] = m, res.net

    print(metrics.table(rows).to_string())
    for label, m in rows.items():
        for w in metrics.warnings(m):
            print(f"\nWARNING ({label}): {w}")
    print(f"\nCosts: {research.cost_label(strat, args.cost_mult)}. "
          f"Distinct configs tried so far: {ledger.stats()['n_trials']}")

    if args.plot:
        path = RESULTS / "explore" / f"{strat.name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        report.compare_curves(curves, path, f"{strat.name}: in-sample, net of costs")
        print(f"Plot: {path.relative_to(RESULTS.parent)}")


if __name__ == "__main__":
    main()
