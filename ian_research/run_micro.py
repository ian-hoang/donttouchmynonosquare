"""Compare three causal intraday experiments and their simple baselines.

Examples:
  python run_micro.py all --demo
  python run_micro.py missing_beat --dbn data/cache/sample.dbn.zst \
      --tick-size .25 --multiplier 50 --fee-per-side 2.50
Real runs require committed hypotheses; OOS is hidden unless --final is supplied.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess

import numpy as np
import pandas as pd

from gqh import ROOT, RESULTS
from gqh.microdata import mbo_features, synthetic_features
from gqh.microengine import Execution, check_causality, simulate
from gqh.split import oos_start
import microstrategies


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hypothesis_ready(name):
    path = f"hypotheses/{name}.md"
    committed = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True)
    if committed.returncode or not (ROOT / path).exists() or committed.stdout != (ROOT / path).read_bytes():
        raise ValueError(f"Commit {path} before any market-data backtest. Synthetic --demo/tests are allowed.")


def source_hash():
    paths = [ROOT / "run_micro.py", ROOT / "pyproject.toml", ROOT / "uv.lock"]
    paths += sorted((ROOT / "gqh").glob("*.py"))
    paths += sorted((ROOT / "microstrategies").glob("*.py"))
    paths += [ROOT / "hypotheses" / f"{name}.md" for name in microstrategies.NAMES]
    digest = hashlib.sha256()
    for path in paths:
        if path.exists():
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def lock_final(path, manifest):
    """Lock the entire comparison, including data/code/costs/clock, before OOS."""
    text = json.dumps(manifest, sort_keys=True, indent=2)
    if path.exists():
        if path.read_text() != text:
            raise ValueError("OOS already locked to a different comparison. Do not tune on the holdout; "
                             "preserve the lock and disclose any necessary research restart.")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as f:
            f.write(text)


def read_dbn(path, max_records):
    import databento as db

    store = db.DBNStore.from_file(path)
    if str(store.metadata.dataset) != "GLBX.MDP3" or str(store.metadata.schema) != "mbo":
        raise ValueError("This replay currently supports GLBX.MDP3 MBO only")
    parts, total = [], 0
    for part in store.to_df(price_type="float", count=250_000):
        total += len(part)
        if total > max_records:
            raise ValueError(f"More than {max_records:,} records. Narrow dates or explicitly raise --max-records.")
        parts.append(part)
    if not parts:
        raise ValueError("DBN has no MBO records")
    frame = pd.concat(parts)
    frame.attrs["source"] = dict(dataset=str(store.metadata.dataset), schema=str(store.metadata.schema),
                                symbols=list(store.metadata.symbols), start=str(store.metadata.start),
                                end=str(store.metadata.end), stype_in=str(store.metadata.stype_in))
    return frame


def parameters(names, assignments):
    result = {name: dict(microstrategies.get(name).DEFAULTS) for name in names}
    for assignment in assignments:
        try:
            key, value = assignment.split("=", 1)
            name, param = key.split(".", 1)
            value = json.loads(value)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Use --set strategy.parameter=JSON_VALUE") from exc
        if name not in result or param not in result[name]:
            raise ValueError(f"Unknown strategy/parameter {key}")
        result[name][param] = value
    return result


def append_trial(path, entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True, allow_nan=False) + "\n")


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("strategy", nargs="?", default="all", choices=("all", *microstrategies.NAMES))
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true", help="synthetic plumbing check; not performance evidence")
    source.add_argument("--dbn", type=Path, help="single fixed-contract GLBX.MDP3 MBO, starting at a snapshot")
    p.add_argument("--fifo", action="store_true", help="confirm selected contract uses FIFO (required for Queue Sacrifice)")
    p.add_argument("--interval", default="1s")
    p.add_argument("--max-quote-age", default="2s")
    p.add_argument("--max-records", type=int, default=2_000_000)
    p.add_argument("--session-start", default="09:30")
    p.add_argument("--session-end", default="16:00")
    p.add_argument("--session-tz", default="America/New_York")
    p.add_argument("--tick-size", type=float)
    p.add_argument("--multiplier", type=float)
    p.add_argument("--fee-per-side", type=float)
    for flag, default in (("slippage-ticks", 1.), ("latency-ms", 100.), ("max-spread-ticks", 4.),
                          ("max-hold-seconds", 30.), ("stop-loss-dollars", 100.),
                          ("daily-loss-dollars", 300.), ("capital", 100_000.)):
        p.add_argument(f"--{flag}", type=float, default=default)
    p.add_argument("--set", nargs="*", default=[])
    p.add_argument("--final", action="store_true", help="freeze the whole comparison and evaluate OOS once")
    p.add_argument("--output", type=Path, default=RESULTS / "micro" / "runs")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        names = list(microstrategies.NAMES) if args.strategy == "all" else [args.strategy]
        if args.demo and args.final:
            raise ValueError("Synthetic demos cannot be final holdout evaluations")
        if not args.demo:
            if any(getattr(args, k) is None for k in ("tick_size", "multiplier", "fee_per_side")):
                raise ValueError("Real runs require explicit --tick-size, --multiplier and --fee-per-side")
            if "queue_sacrifice" in names and not args.fifo:
                raise ValueError("Verify the product's matching rules, then supply --fifo for Queue Sacrifice")
            for name in names:
                hypothesis_ready(name)
        params = parameters(names, args.set)
        config_fields = vars(Execution())
        settings = {k: getattr(args, k) if getattr(args, k) is not None else v for k, v in config_fields.items()}
        config = Execution(**settings)
        config.validate()
        # Price displacement must use the same contract tick as execution.
        if "missing_beat" in params:
            if any(s.startswith("missing_beat.tick_size=") for s in args.set) and params["missing_beat"]["tick_size"] != config.tick_size:
                raise ValueError("Missing Beat tick_size must match execution --tick-size")
            params["missing_beat"]["tick_size"] = config.tick_size
        if args.demo:
            if args.interval != "1s":
                raise ValueError("Demo fixture uses --interval 1s; real replay supports other intervals")
            frame, data_hash = synthetic_features(), "synthetic-v1-seed7"
            provenance = {"synthetic": True, "seed": 7}
        else:
            data_hash = sha256(args.dbn)
            events = read_dbn(args.dbn, args.max_records)
            provenance = events.attrs["source"]
            frame = mbo_features(events, interval=args.interval,
                                 max_quote_age=args.max_quote_age)
        # Explicit regular intraday window; no overnight-wrap sessions in v1.
        if args.session_start >= args.session_end:
            raise ValueError("session-start must precede session-end within one local calendar date")
        local = frame.tz_convert(args.session_tz).between_time(args.session_start, args.session_end)
        frame = local.tz_convert("UTC")
        if len(frame) < 100:
            raise ValueError("Fewer than 100 completed bars in selected sessions")
        cut = oos_start(frame.index)
        is_data = frame.loc[frame.index < cut]
        # Demo is always IS-only, even though its fixture is not market evidence.
        parts = {"IS": is_data}
        if args.final:
            parts["OOS"] = frame.loc[frame.index >= cut]
        manifest = dict(source_hash=source_hash(), data_hash=data_hash, source=provenance, strategies=params,
                        runtime={"python": platform.python_version(), **{p: version(p) for p in ("numpy", "pandas", "databento")}},
                        execution=asdict(config), interval=args.interval, max_quote_age=args.max_quote_age,
                        session_start=args.session_start, session_end=args.session_end, session_tz=args.session_tz,
                        fifo=bool(args.fifo), oos_start=cut.isoformat(), synthetic=bool(args.demo),
                        comparison=["signal", "baseline"], costs=[1.0, 2.0])
        # Every strategy and baseline is checked on IS before any simulated fills.
        for name in names:
            module = microstrategies.get(name)
            for kind in ("signal", "baseline"):
                check_causality(getattr(module, kind), is_data, params[name])
        if args.final:
            lock_final(RESULTS / "micro" / "OOS_LOCK.json", manifest)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder = args.output / ("demo" if args.demo else "market") / stamp
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
        ledger = RESULTS / "micro" / ("demo_ledger.jsonl" if args.demo else "ledger.jsonl")
        records, curves = [], {}
        for name in names:
            module = microstrategies.get(name)
            for part, subset in parts.items():
                for kind in ("signal", "baseline"):
                    target = getattr(module, kind)(subset, **params[name])
                    for cost in (1.0, 2.0):
                        label = f"{name}.{kind}.{part}.cost{cost:g}"
                        trial = dict(time=stamp, strategy=name, kind=kind, part=part, cost_mult=cost,
                                     manifest=manifest, label=label)
                        append_trial(ledger, {**trial, "status": "started"})
                        try:
                            result = simulate(subset, target, config, cost_mult=cost)
                        except Exception as exc:
                            append_trial(ledger, {**trial, "status": "failed", "error": str(exc)})
                            raise
                        append_trial(ledger, {**trial, "status": "complete", "summary": result.summary})
                        records.append(dict(strategy=name, variant=kind, sample=part, cost_mult=cost, **result.summary))
                        result.curve.to_csv(folder / f"{label}.curve.csv")
                        result.fills.to_csv(folder / f"{label}.fills.csv", index=False)
                        curves[label] = result.curve.pnl
        table = pd.DataFrame(records)
        table.to_csv(folder / "comparison.csv", index=False)
        (folder / "comparison.json").write_text(json.dumps(records, indent=2, allow_nan=False))
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(11, 5))
        for label, curve in curves.items():
            if ".cost1" in label:
                ax.plot(curve.index, curve, label=label, alpha=.8)
        ax.set(ylabel="Net P&L ($), one contract", title="SYNTHETIC SMOKE TEST" if args.demo else "Intraday research comparison")
        ax.legend(fontsize=6)
        fig.tight_layout()
        fig.savefig(folder / "comparison.png", dpi=150)
        plt.close(fig)
        print("SYNTHETIC SMOKE TEST — no evidence of market profitability" if args.demo else "Market-data research")
        print(f"OOS begins {cut.isoformat()}; {'locked evaluation' if args.final else 'NOT evaluated'}")
        print(table[["strategy", "variant", "sample", "cost_mult", "net_pnl", "fills"]].to_string(index=False))
        print(f"Private output: {folder}")
        print("Defaults are untuned. Sharpe is suppressed below 20 sessions. Combine all teammates' trial logs.")
    except (ValueError, OSError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
