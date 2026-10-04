from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import backtest_micro as batch
from gqh.microengine import Execution
import microstrategies


def configuration():
    return {
        "symbol": "ESU6", "instrument_id": 42140870,
        "sessions": pd.bdate_range("2026-08-03", "2026-09-04").strftime("%Y-%m-%d").tolist(),
        "holdout_start": "2026-08-29T04:42:00+00:00",
        "parameters": {name: dict(microstrategies.get(name).DEFAULTS) for name in microstrategies.NAMES},
        "execution": asdict(Execution()),
        "scenarios": [
            {"name": "base", "cost_mult": 1, "overrides": {}},
            {"name": "double_cost", "cost_mult": 2, "overrides": {}},
            {"name": "latency_3s", "cost_mult": 1, "overrides": {"latency_ms": 3000}},
            {"name": "spread_only", "cost_mult": 1, "overrides": {"fee_per_side": 0, "slippage_ticks": 0}},
        ],
    }


def feature_frame(date, *, full=True):
    index = pd.date_range(f"{date} 13:30:00", f"{date} 14:30:00", freq="s", tz="UTC", name="ts_decision")
    if not full:
        index = index[:3]
    frame = pd.DataFrame(0.0, index=index, columns=sorted(batch._FEATURES - {"session", "valid", "instrument_id"}))
    frame["bid"], frame["ask"], frame["mid"] = 5000.0, 5000.25, 5000.125
    frame["bid_size"], frame["ask_size"] = 100.0, 100.0
    frame["session"], frame["valid"], frame["instrument_id"] = date, True, 42140870
    return frame


def test_frozen_date_selection_is_twenty_is_and_five_unopened_holdout_sessions():
    sessions, cutoff, execution = batch.validate_configuration(configuration())
    assert len(sessions) == 20
    assert sessions[0] == "2026-08-03"
    assert sessions[-1] == "2026-08-28"
    assert cutoff == pd.Timestamp("2026-08-29T04:42:00Z")
    assert execution.multiplier == 50


def test_configuration_rejects_shifted_holdout_and_unfrozen_parameters():
    config = configuration()
    config["holdout_start"] = "2026-08-28T14:00:00Z"
    with pytest.raises(ValueError, match="split"):
        batch.validate_configuration(config)
    config["holdout_start"] = "2026-08-27T00:00:00Z"
    with pytest.raises(ValueError, match="Exactly 20"):
        batch.validate_configuration(config)
    config = configuration()
    del config["parameters"]["missing_beat"]["tick_size"]
    with pytest.raises(ValueError, match="every default"):
        batch.validate_configuration(config)
    config = configuration()
    config["scenarios"][1]["cost_mult"] = 1
    with pytest.raises(ValueError, match="frozen scenario definition"):
        batch.validate_configuration(config)


def test_loader_never_opens_holdout_and_hashes_exact_is_bytes(tmp_path, monkeypatch):
    config = configuration()
    sessions, cutoff, _ = batch.validate_configuration(config)
    for date in sessions:
        feature_frame(date).to_csv(tmp_path / f"ESU6_{date}.csv.gz", compression="gzip")
    # Deliberately poisonous holdout content. Loading or hashing it is a test
    # failure; the runner must construct IS names rather than glob a directory.
    holdout = tmp_path / "ESU6_2026-08-31.csv.gz"
    holdout.write_bytes(b"THIS MUST NEVER BE READ")
    original = Path.read_bytes
    opened = []

    def read(path):
        assert path != holdout
        opened.append(path.name)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    frame, hashes = batch.load_in_sample(config, sessions, cutoff, tmp_path)
    assert len(frame) == 20 * 3601
    assert len(hashes) == len(opened) == 20
    assert frame.index.max() < cutoff
    assert all(len(item["sha256"]) == 64 for item in hashes)


def test_loader_fails_before_any_read_when_an_is_file_is_missing(tmp_path, monkeypatch):
    config = configuration()
    sessions, cutoff, _ = batch.validate_configuration(config)
    for date in sessions[:-1]:
        (tmp_path / f"ESU6_{date}.csv.gz").touch()
    monkeypatch.setattr(Path, "read_bytes", lambda _: pytest.fail("Do not read an incomplete batch"))
    with pytest.raises(ValueError, match="Missing required"):
        batch.load_in_sample(config, sessions, cutoff, tmp_path)


def test_loader_rejects_incomplete_grid(tmp_path):
    config = configuration()
    sessions, cutoff, _ = batch.validate_configuration(config)
    for date in sessions:
        (tmp_path / f"ESU6_{date}.csv.gz").touch()
    feature_frame(sessions[0]).iloc[:-1].to_csv(tmp_path / f"ESU6_{sessions[0]}.csv.gz", compression="gzip")
    with pytest.raises(ValueError, match="3601-bar"):
        batch.load_in_sample(config, sessions, cutoff, tmp_path)


def test_exact_config_bytes_must_match_head(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "ROOT", tmp_path)
    path = tmp_path / "experiments/config.json"
    monkeypatch.setattr(batch.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"old bytes"))
    with pytest.raises(ValueError, match="Commit the exact"):
        batch.experiment_ready(path, b"new bytes")


def test_batch_outputs_all_twenty_four_frozen_runs_without_parameter_mutation(tmp_path, monkeypatch):
    config = configuration()
    saved = json.dumps(config, sort_keys=True)
    config_path = tmp_path / "config.json"
    config_path.write_text(saved)
    frame = pd.concat([feature_frame(date, full=False) for date in config["sessions"][:20]])
    phases = []
    monkeypatch.setattr(batch, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(batch, "experiment_ready", lambda *a: "test-commit")
    monkeypatch.setattr(batch, "hypothesis_ready", lambda name: phases.append(("hypothesis", name)))
    monkeypatch.setattr(batch, "load_in_sample", lambda *a: (frame, [{"file": "fixture", "sha256": "fixture"}]))
    monkeypatch.setattr(batch, "source_hash", lambda: "fixture-source")
    real_simulate = batch.simulate

    def check(function, subset, params):
        phases.append(("causality", function.__module__, function.__name__))
        return pd.Series(0.0, index=subset.index, name="target")

    def simulate(*args, **kwargs):
        assert sum(phase[0] == "causality" for phase in phases) == 6
        phases.append(("simulate",))
        return real_simulate(*args, **kwargs)

    monkeypatch.setattr(batch, "check_causality", check)
    monkeypatch.setattr(batch, "simulate", simulate)
    folder, table = batch.run(config_path, tmp_path, tmp_path / "output")
    assert len(table) == 24
    assert set(table["sample"]) == {"IS"}
    assert set(table["scenario"]) == batch._SCENARIOS
    assert len(list(folder.glob("*.curve.csv"))) == 24
    assert len(list(folder.glob("*.fills.csv"))) == 24
    assert len(list(folder.glob("*.evidence.json"))) == 24
    assert len(list(folder.glob("*.diagnostics.csv"))) == 3
    assert config_path.read_text() == saved
    manifest = json.loads((folder / "manifest.json").read_text())
    assert not manifest["holdout_evaluated"]
    assert manifest["configuration"] == config
    assert len(manifest["batch_runner_sha256"]) == 64
    ledger = [json.loads(line) for line in (tmp_path / "results/micro/ledger.jsonl").read_text().splitlines()]
    assert len(ledger) == 48
    assert sum(entry["status"] == "complete" for entry in ledger) == 24
    assert {entry["mode"] for entry in ledger} == {"frozen_in_sample", "optimistic_diagnostic"}
    assert all(entry["sample"] == "IS" for entry in ledger)


def test_failed_execution_is_logged_before_error_propagates(tmp_path, monkeypatch):
    config = configuration()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    frame = feature_frame(config["sessions"][0], full=False)
    monkeypatch.setattr(batch, "RESULTS", tmp_path / "results")
    monkeypatch.setattr(batch, "experiment_ready", lambda *a: "test-commit")
    monkeypatch.setattr(batch, "hypothesis_ready", lambda *a: None)
    monkeypatch.setattr(batch, "load_in_sample", lambda *a: (frame, []))
    monkeypatch.setattr(batch, "source_hash", lambda: "fixture-source")
    monkeypatch.setattr(batch, "check_causality", lambda *a: pd.Series(0.0, index=frame.index))

    def fail(*a, **k):
        raise ValueError("fixture execution failure")

    monkeypatch.setattr(batch, "simulate", fail)
    with pytest.raises(ValueError, match="fixture execution failure"):
        batch.run(path, tmp_path, tmp_path / "output")
    ledger = [json.loads(line) for line in (tmp_path / "results/micro/ledger.jsonl").read_text().splitlines()]
    assert [entry["status"] for entry in ledger] == ["started", "failed"]
    assert ledger[-1]["error"] == "fixture execution failure"
