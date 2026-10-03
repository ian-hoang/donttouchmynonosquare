"""Chunks in a fixed-seed shuffled order, so a burst-QOS array works the queue from different points than
the forward and reverse arrays (per-video locks prevent double work)."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
root = Path(__file__).resolve().parents[2]
manifest, out, n = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
done = {p.name.split(".")[0] for p in (root / "data/cache/vision").glob("*.vision.json")}
ids = np.array([v for v in pd.read_csv(manifest, dtype={"video_id": str})["video_id"] if v not in done])
ids = ids[np.random.default_rng(20261003).permutation(len(ids))]
out.mkdir(parents=True, exist_ok=True)
for i in range(n):
    (out / f"chunk_{i}.txt").write_text("\n".join(ids[i::n]) + "\n")
print(len(ids), "ids (shuffled) ->", n, "chunks in", out)
