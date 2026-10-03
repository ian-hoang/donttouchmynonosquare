"""Run the frozen opening-hour comparison on its 20 in-sample sessions only.

No downloads, parameter overrides, automatic selection, or holdout evaluation
are provided. Licensed feature files and research output remain private.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import platform
import subprocess

import numpy as np
import pandas as pd

from gqh import ROOT, RESULTS
from gqh.microengine import Execution, check_causality, simulate
from gqh.microevidence import evidence
import microstrategies
from run_micro import append_trial, hypothesis_ready, sha256, source_hash


_SCENARIOS = {"base", "double_cost", "latency_3s", "spread_only"}
_FEATURES = {
    "bid", "ask", "mid", "bid_size", "ask_size", "buy_volume", "sell_volume",
    "trade_volume", "signed_volume", "bid_add", "ask_add", "bid_cancel", "ask_cancel",
    "bid_priority_cancel", "ask_priority_cancel", "session", "valid", "instrument_id",
}


def experiment_ready(path: Path, payload: bytes) -> str:
    """Require the exact configuration bytes in HEAD before reading prices."""
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("Experiment configuration must be inside the repository") from exc
    committed = subprocess.run(["git", "show", f"HEAD:{relative}"], cwd=ROOT, capture_output=True)
    if committed.returncode or committed.stdout != payload:
        raise ValueError(f"Commit the exact {relative} before any market-data backtest")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    if head.returncode:
        raise ValueError("Cannot identify the hypothesis/configuration commit")
    return head.stdout.strip()


def validate_configuration(config: dict):
    required = {"sessions", "holdout_start", "parameters", "execution", "scenarios", "symbol", "instrument_id"}
    if not required.issubset(config):
        raise ValueError(f"Missing configuration fields: {sorted(required - set(config))}")
    symbol = config["symbol"]
    if not isinstance(symbol, str) or not symbol.isalnum():
        raise ValueError("symbol must be an alphanumeric fixed-contract symbol")
    if not isinstance(config["instrument_id"], int) or config["instrument_id"] <= 0:
        raise ValueError("instrument_id must be a positive integer")
    sessions = config["sessions"]
    if len(sessions) != 25 or len(set(sessions)) != 25 or sessions != sorted(sessions):
        raise ValueError("Freeze exactly 25 distinct chronological session dates")
    dates = pd.to_datetime(sessions, format="%Y-%m-%d", utc=True, errors="raise")
    if any(date.strftime("%Y-%m-%d") != original for date, original in zip(dates, sessions)):
        raise ValueError("sessions must contain ISO calendar dates")
    cutoff = pd.Timestamp(config["holdout_start"])
    if cutoff.tzinfo is None:
        raise ValueError("holdout_start must specify its timezone")
    cutoff = cutoff.tz_convert("UTC")
    in_sample = []
    for date, text in zip(dates, sessions):
        start, end = date + pd.Timedelta(hours=13, minutes=30), date + pd.Timedelta(hours=14, minutes=30)
        if start < cutoff <= end:
            raise ValueError("The fixed holdout cutoff cannot split an opening-hour session")
        if end < cutoff:
            in_sample.append(text)
    if len(in_sample) != 20:
        raise ValueError("Exactly 20 complete in-sample sessions are required; do not move the holdout")
    if set(config["parameters"]) != set(microstrategies.NAMES):
        raise ValueError("Freeze parameters for all three strategies")
    for name in microstrategies.NAMES:
        if set(config["parameters"][name]) != set(microstrategies.get(name).DEFAULTS):
            raise ValueError(f"Freeze every default parameter explicitly for {name}")
    if set(config["execution"]) != set(asdict(Execution())):
        raise ValueError("Freeze every Execution field explicitly")
    execution = Execution(**config["execution"])
    execution.validate()
    if config["parameters"]["missing_beat"]["tick_size"] != execution.tick_size:
        raise ValueError("Missing Beat and execution tick_size must match")
    scenarios = config["scenarios"]
    if len(scenarios) != 4 or {s["name"] for s in scenarios} != _SCENARIOS:
        raise ValueError("Require the four frozen base, double_cost, latency_3s, spread_only scenarios")
    for scenario in scenarios:
        if set(scenario) != {"name", "cost_mult", "overrides"}:
            raise ValueError("Each scenario requires exactly name, cost_mult, overrides")
        if not np.isfinite(scenario["cost_mult"]) or scenario["cost_mult"] <= 0:
            raise ValueError("Scenario cost_mult must be finite and positive")
        if set(scenario["overrides"]) - set(config["execution"]):
            raise ValueError("Unknown execution scenario override")
        settings = replace(execution, **scenario["overrides"])
        settings.validate()
        if settings.tick_size != execution.tick_size or settings.multiplier != execution.multiplier:
            raise ValueError("Scenarios must retain the contract tick and multiplier")
        expected = {
            "base": (1.0, execution),
            "double_cost": (2.0, execution),
            "latency_3s": (1.0, replace(execution, latency_ms=3000.0)),
            "spread_only": (1.0, replace(execution, fee_per_side=0.0, slippage_ticks=0.0)),
        }[scenario["name"]]
        if scenario["cost_mult"] != expected[0] or settings != expected[1]:
            raise ValueError(f"{scenario['name']} settings do not match its frozen scenario definition")
    return in_sample, cutoff, execution


def load_in_sample(config, sessions, cutoff, features_root):
    """Open only the twenty explicitly named IS files; never enumerate OOS."""
    paths = [features_root / f"{config['symbol']}_{day}.csv.gz" for day in sessions]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"Missing required in-sample feature files: {missing}")
    frames, hashes = [], []
    for date, path in zip(sessions, paths):
        payload = path.read_bytes()
        frame = pd.read_csv(BytesIO(payload), compression="gzip", index_col=0, parse_dates=[0])
        if not isinstance(frame.index, pd.DatetimeIndex) or str(frame.index.tz) != "UTC":
            raise ValueError(f"{path.name}: require UTC ts_decision index")
        expected = pd.date_range(f"{date} 13:30:00", f"{date} 14:30:00", freq="s", tz="UTC", name="ts_decision")
        if frame.index.name != "ts_decision" or not frame.index.equals(expected):
            raise ValueError(f"{path.name}: require the complete 3601-bar opening-hour grid")
        if not _FEATURES.issubset(frame):
            raise ValueError(f"{path.name}: missing features {sorted(_FEATURES - set(frame))}")
        if not frame["session"].eq(date).all() or not frame["instrument_id"].eq(config["instrument_id"]).all():
            raise ValueError(f"{path.name}: session or instrument does not match the frozen experiment")
        if frame["valid"].isna().any() or not frame["valid"].isin([True, False]).all():
            raise ValueError(f"{path.name}: valid must be boolean without missing values")
        frame["valid"] = frame["valid"].astype(bool)
        numeric = sorted(_FEATURES - {"session", "valid", "instrument_id"})
        if not np.isfinite(frame.loc[frame.valid, numeric].to_numpy(dtype=float)).all():
            raise ValueError(f"{path.name}: valid bars contain missing or nonfinite numeric features")
        if not (frame.index < cutoff).all():
            raise ValueError("Refusing an out-of-sample row")
        frames.append(frame)
        hashes.append({"file": path.name, "sha256": hashlib.sha256(payload).hexdigest(), "rows": len(frame)})
    combined = pd.concat(frames)
    if not combined.index.is_monotonic_increasing or not combined.index.is_unique:
        raise ValueError("In-sample feature timestamps must be unique and chronological")
    return combined, hashes


def diagnostic_counts(frame):
    summary = {"rows": len(frame)}
    for name in frame.select_dtypes(include=["number", "bool"]).columns:
        values = frame[name].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        summary[name] = {"finite": int(len(finite)), "nonzero": int(np.count_nonzero(finite)),
                         "minimum": float(finite.min()) if len(finite) else None,
                         "maximum": float(finite.max()) if len(finite) else None}
    return summary


def _json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def run(config_path, features_root, output_root, *, plot=False):
    config_path, features_root, output_root = map(Path, (config_path, features_root, output_root))
    payload = config_path.read_bytes()
    config = json.loads(payload)
    sessions, cutoff, execution = validate_configuration(config)
    head = experiment_ready(config_path, payload)
    for name in microstrategies.NAMES:
        hypothesis_ready(name)
    frame, input_hashes = load_in_sample(config, sessions, cutoff, features_root)
    manifest = {
        "mode": "frozen_in_sample", "sample": "IS", "holdout_evaluated": False,
        "configuration": config, "config_sha256": hashlib.sha256(payload).hexdigest(),
        "source_hash": source_hash(), "batch_runner_sha256": sha256(Path(__file__)),
        "hypothesis_config_commit": head, "inputs": input_hashes, "in_sample_sessions": sessions,
        "runtime": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
        "notes": ["spread_only is an optimistic diagnostic, not deployable execution.",
                  "All four scenarios and both variants are reported without selection.",
                  "Uncertainty intervals do not adjust for multiple strategies or reused samples."],
    }
    manifest_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = output_root / stamp
    folder.mkdir(parents=True, exist_ok=False)
    _json(folder / "manifest.json", {**manifest, "manifest_sha256": manifest_hash})
    ledger = RESULTS / "micro" / "ledger.jsonl"
    targets = {}
    # All six causality checks finish before any simulated fill is generated.
    for name in microstrategies.NAMES:
        module = microstrategies.get(name)
        for variant in ("signal", "baseline"):
            targets[name, variant] = check_causality(getattr(module, variant), frame, config["parameters"][name])
        diag = module.diagnostics(frame, **config["parameters"][name])
        diag.to_csv(folder / f"{name}.diagnostics.csv", index_label="ts_decision")
        _json(folder / f"{name}.diagnostic_counts.json", diagnostic_counts(diag))

    records, curves = [], {}
    for name in microstrategies.NAMES:
        for scenario in config["scenarios"]:
            settings = replace(execution, **scenario["overrides"])
            results = {}
            for variant in ("signal", "baseline"):
                label = f"{name}.{variant}.{scenario['name']}.IS"
                trial = {"time": stamp, "strategy": name, "kind": variant, "sample": "IS",
                         "scenario": scenario["name"], "cost_mult": scenario["cost_mult"],
                         "mode": "optimistic_diagnostic" if scenario["name"] == "spread_only" else "frozen_in_sample",
                         "parameters": config["parameters"][name], "execution": asdict(settings),
                         "manifest_sha256": manifest_hash, "output": str(folder), "label": label}
                append_trial(ledger, {**trial, "status": "started"})
                try:
                    result = simulate(frame, targets[name, variant], settings, cost_mult=scenario["cost_mult"])
                    result.curve.to_csv(folder / f"{label}.curve.csv", index_label="ts_decision")
                    result.fills.to_csv(folder / f"{label}.fills.csv", index=False)
                    results[variant] = result
                    selected = {key: result.summary[key] for key in (
                        "net_pnl", "return_on_capital", "max_drawdown", "sessions", "fills",
                        "contracts_traded", "invalid_bars", "exposure_fraction")}
                    records.append({"strategy": name, "variant": variant, "scenario": scenario["name"],
                                    "sample": "IS", "mode": trial["mode"], **selected})
                    curves[label] = result.curve.pnl
                    append_trial(ledger, {**trial, "status": "complete", "summary": selected})
                except Exception as exc:
                    append_trial(ledger, {**trial, "status": "failed", "error": str(exc)})
                    raise
            for variant in ("signal", "baseline"):
                result = results[variant]
                paired = results["baseline"].curve if variant == "signal" else None
                report = evidence(result.curve, result.fills, paired)
                _json(folder / f"{name}.{variant}.{scenario['name']}.IS.evidence.json", report)
    table = pd.DataFrame(records)
    table.to_csv(folder / "comparison.csv", index=False)
    _json(folder / "comparison.json", records)
    if plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(12, 6))
        for label, pnl in curves.items():
            if ".base." in label:
                ax.plot(pnl.index, pnl, label=label, linewidth=1)
        ax.set(title="Frozen opening-hour comparison: 20 in-sample sessions", ylabel="Net P&L ($)")
        ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(folder / "base_equity.png", dpi=150)
        plt.close(fig)
    return folder, table


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "experiments/micro_opening_2026.json")
    parser.add_argument("--features-root", type=Path, default=ROOT / "data/cache/micro_opening_2026/features")
    parser.add_argument("--output", type=Path, default=RESULTS / "micro/runs/opening_2026")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args(argv)
    try:
        folder, table = run(args.config, args.features_root, args.output, plot=args.plot)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(table[["strategy", "variant", "scenario", "sample", "net_pnl", "fills"]].to_string(index=False))
    print(f"Private output: {folder}")
    print("20 IS sessions only; holdout untouched. spread_only is an optimistic diagnostic.")


if __name__ == "__main__":
    main()
