"""Build masked labeling batches from the CEO-only text of each processed video.

Each batch file (.scratch/labels/batch_NNN.json) holds up to N videos; each video is a list of CEO
utterances with identifying tokens masked (agentic/masking.py). Videos that fail the leak check are
skipped and listed. Nothing here sees prices or returns.

Usage: python agentic/prepare_label_batches.py [--per-batch 15]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agentic.masking import entities_for, leak_check, mask_text  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-batch", type=int, default=15)
    ap.add_argument("--max-chars", type=int, default=9000, help="cap per video to bound tokens")
    a = ap.parse_args()
    man = pd.read_csv(ROOT / "data" / "manifest" / "videos.csv", dtype={"video_id": str})
    tdir = ROOT / "data" / "cache" / "ceo_text"
    out = ROOT / ".scratch" / "labels"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("batch_*.json"):
        old.unlink()
    done = set()
    lab = ROOT / "data" / "features" / "utterance_labels.csv"
    if lab.exists():
        done = set(pd.read_csv(lab, dtype={"video_id": str})["video_id"])
    items, leaks = [], []
    for r in man.itertuples():
        p = tdir / f"{r.video_id}.json"
        if r.video_id in done or not p.exists():
            continue
        ents = entities_for(r.ticker)
        utts, total = [], 0
        for u in json.loads(p.read_text()):
            m, _ = mask_text(u["text"], ents)
            if total + len(m) > a.max_chars:
                break
            utts.append(m)
            total += len(m)
        residue = leak_check(" ".join(utts), ents)
        if residue:
            leaks.append({"video_id": r.video_id, "residue": residue[:5]})
            continue
        if utts:
            items.append({"video_id": r.video_id, "utterances": utts})
    for i in range(0, len(items), a.per_batch):
        (out / f"batch_{i // a.per_batch:03d}.json").write_text(json.dumps(items[i:i + a.per_batch]))
    (out / "leaks.json").write_text(json.dumps(leaks, indent=1))
    print(f"{len(items)} videos -> {(len(items) + a.per_batch - 1) // a.per_batch} batches; {len(leaks)} blocked by leak check")


if __name__ == "__main__":
    main()
