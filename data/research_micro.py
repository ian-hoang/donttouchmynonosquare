"""Fetch/replay the frozen intraday experiment without opening its holdout.

Download costs are reserved before each API request, including failed attempts.
The complete reconstructed book is streamed from midnight before retaining the
opening hour. Files and their checksums stay in the ignored data cache.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gqh import ROOT  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
import pandas as pd  # noqa: E402

CACHE = ROOT / "data/cache/micro_opening_2026"
GUARD = threading.Lock()


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selected(config):
    holdout = pd.Timestamp(config["holdout_start"])
    return [day for day in config["sessions"] if pd.Timestamp(f"{day}T14:30:00Z") < holdout]


def estimate(config, destination, workers):
    import databento as db

    def one(day):
        request = dict(dataset="GLBX.MDP3", symbols=[config["symbol"]], schema="mbo", stype_in="raw_symbol",
                       start=f"{day}T00:00:00Z", end=f"{day}T14:31:00Z")
        client = db.Historical()
        return dict(request=request, usd=float(client.metadata.get_cost(**request)),
                    records=int(client.metadata.get_record_count(**request)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        estimates = list(pool.map(one, config["sessions"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(estimates, indent=2))
    is_days = set(selected(config))
    print(json.dumps(dict(all_sessions=len(estimates), all_sessions_usd=sum(e["usd"] for e in estimates),
                          in_sample_usd=sum(e["usd"] for e in estimates if e["request"]["start"][:10] in is_days),
                          estimates_file=str(destination)), indent=2))


def download(config, estimates, workers):
    import databento as db

    load_dotenv(ROOT / ".env")
    cap = min(float(os.getenv("GQH_MAX_COST_USD", "5")), 20.0)
    if cap <= 0:
        raise ValueError("Download budget must be positive")
    requests = {e["request"]["start"][:10]: e for e in estimates}
    days = selected(config)
    if any(day not in requests or "error" in requests[day] for day in days):
        raise ValueError("Missing cost estimate for a selected session")
    CACHE.mkdir(parents=True, exist_ok=True)
    budget_file = CACHE / "spend_reservations.jsonl"
    old = [json.loads(line) for line in budget_file.read_text().splitlines()] if budget_file.exists() else []
    reserved = sum(row["usd"] for row in old)
    remaining = [d for d in days if not (CACHE / f"{config['symbol']}_{d}.dbn.zst").exists()]
    estimate = sum(requests[d]["usd"] for d in remaining)
    if reserved + estimate > cap:
        raise ValueError(f"${reserved + estimate:.4f} reserved/estimated exceeds total ${cap:.2f} guard")
    print(f"{len(remaining)} missing IS files; estimated new cost ${estimate:.4f}; total budget ${cap:.2f}", flush=True)

    def fetch(day):
        nonlocal reserved
        item = requests[day]
        request = item["request"]
        if (request["symbols"] != [config["symbol"]] or request["schema"] != "mbo" or
                request["dataset"] != "GLBX.MDP3" or request["stype_in"] != "raw_symbol" or
                request["start"] != f"{day}T00:00:00Z" or request["end"] != f"{day}T14:31:00Z"):
            raise ValueError("Cost estimate does not match frozen instrument/source")
        client = db.Historical()
        cost = float(client.metadata.get_cost(**request))
        with GUARD:
            if reserved + cost > cap:
                raise ValueError("Fresh download estimate would exceed the cumulative budget")
            reservation = dict(time=datetime.now(timezone.utc).isoformat(), day=day, usd=cost, request=request)
            with budget_file.open("a") as f:
                f.write(json.dumps(reservation) + "\n")
            reserved += cost
        path = CACHE / f"{config['symbol']}_{day}.dbn.zst"
        part = path.with_suffix(path.suffix + ".part")
        if part.exists():
            raise ValueError(f"Prior incomplete request {part.name}; inspect before another charged attempt")
        started = time.monotonic()
        client.timeseries.get_range(**request, path=part)
        part.rename(path)
        info = dict(request=request, estimated_usd=cost, bytes=path.stat().st_size,
                    sha256=checksum(path), seconds=round(time.monotonic() - started, 2))
        path.with_suffix(".json").write_text(json.dumps(info, indent=2))
        return day, info

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, day): day for day in remaining}
        for future in as_completed(futures):
            day, info = future.result()
            print(f"Downloaded {day}: {info['bytes']/1e6:.1f} MB, ${info['estimated_usd']:.4f}, {info['seconds']} s", flush=True)


def prepare(config, only=None):
    import databento as db
    from gqh.microdata import mbo_features_iter

    out = CACHE / "features"
    out.mkdir(parents=True, exist_ok=True)
    replay_hash = checksum(ROOT / "gqh/microdata.py")
    for day in selected(config):
        if only is not None and day != only:
            continue
        path = CACHE / f"{config['symbol']}_{day}.dbn.zst"
        target = out / f"{config['symbol']}_{day}.csv.gz"
        manifest = out / f"{config['symbol']}_{day}.json"
        if not path.exists():
            raise ValueError(f"Missing IS source {path}")
        if target.exists() and manifest.exists():
            previous = json.loads(manifest.read_text())
            if previous["replay_hash"] == replay_hash and previous["source_sha256"] == checksum(path):
                print(f"Already prepared {day}", flush=True)
                continue
            raise ValueError(f"Stale feature cache for {day}; preserve and explicitly rebuild it")
        print(f"Replaying {day}", flush=True)
        started = time.monotonic()
        store = db.DBNStore.from_file(path)
        if str(store.metadata.dataset) != "GLBX.MDP3" or str(store.metadata.schema) != "mbo":
            raise ValueError("Expected GLBX.MDP3 MBO")
        records = 0

        def chunks():
            nonlocal records
            for chunk in store.to_df(price_type="float", count=250_000):
                if not chunk.instrument_id.eq(config["instrument_id"]).all():
                    raise ValueError("Unexpected contract ID in frozen raw-symbol data")
                records += len(chunk)
                yield chunk

        frame = mbo_features_iter(chunks(), interval=config["interval"], max_quote_age=config["max_quote_age"])
        unattributed = float(frame.unattributed_fill_volume.sum())
        frame = frame.tz_convert(config["session_tz"]).between_time(config["session_start"], config["session_end"]).tz_convert("UTC")
        if len(frame) != 3601:
            raise ValueError(f"Expected exactly 3601 opening-hour grid rows, found {len(frame)} on {day}")
        frame.to_csv(target, compression="gzip", index_label="ts_decision")
        info = dict(day=day, source_sha256=checksum(path), feature_sha256=checksum(target),
                    replay_hash=replay_hash, records=records, rows=len(frame), valid_fraction=float(frame.valid.mean()),
                    unattributed_fill_volume_before_session_filter=unattributed,
                    seconds=round(time.monotonic() - started, 2))
        manifest.write_text(json.dumps(info, indent=2))
        print(json.dumps(info), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["estimate", "download", "prepare"])
    p.add_argument("--config", type=Path, default=ROOT / "experiments/micro_opening_2026.json")
    p.add_argument("--estimates", type=Path, default=ROOT / "data/cache/micro_estimates.json")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--day", help="prepare just this predeclared IS day")
    p.add_argument("--available", action="store_true", help="prepare only completed downloads; backtests still require all IS days")
    args = p.parse_args()
    load_dotenv(ROOT / ".env")
    try:
        config = json.loads(args.config.read_text())
        if args.mode in ("estimate", "download"):
            if not 1 <= args.workers <= 4:
                raise ValueError("workers must be 1..4")
            if args.mode == "estimate":
                estimate(config, args.estimates, args.workers)
            else:
                download(config, json.loads(args.estimates.read_text()), args.workers)
        else:
            days = selected(config)
            if args.day:
                if args.day not in days:
                    raise ValueError("Requested day is outside the frozen IS partition")
                days = [args.day]
            if args.available:
                days = [day for day in days if (CACHE / f"{config['symbol']}_{day}.dbn.zst").exists()]
            if not 1 <= args.workers <= 4:
                raise ValueError("workers must be 1..4")
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(prepare, config, day) for day in days]
                for future in as_completed(futures):
                    future.result()
    except Exception as exc:
        secret = os.getenv("DATABENTO_API_KEY", "")
        message = str(exc).replace(secret, "[REDACTED]") if secret else str(exc)
        print(f"{type(exc).__name__}: {message}", file=sys.stderr, flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
