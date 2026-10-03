"""Like make_chunks.py but in reverse manifest order, so a second array works from the other end of the
same queue (per-video lock files prevent double work)."""
import sys
from pathlib import Path
import pandas as pd
root = Path(__file__).resolve().parents[2]
manifest, out, n = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3])
done = {p.name.split(".")[0] for p in (root / "data/cache/vision").glob("*.vision.json")}
ids = [v for v in pd.read_csv(manifest, dtype={"video_id": str})["video_id"] if v not in done][::-1]
out.mkdir(parents=True, exist_ok=True)
for i in range(n):
    (out / f"chunk_{i}.txt").write_text("\n".join(ids[i::n]) + "\n")
print(len(ids), "ids (reversed) ->", n, "chunks in", out)
