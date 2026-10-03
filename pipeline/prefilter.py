"""Rule prefilter for search hits (same rules as the original corpus): CEO name in the title, junk-title filter,
3-120 minutes, de-duplicated; writes candidates_for_curation{U}.csv and curation batches of 120.

Usage: PF_UNIVERSE=_h2 python pipeline/prefilter.py data/manifest/candidates_years_h2.csv .scratch/curation_h2
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
U = __import__("os").environ.get("PF_UNIVERSE", "")
JUNK = (r"motivat|speech that|compilation|\bai\b|reacts?\b|reaction|#shorts|life advice|quotes|edit\b|deepfake|parody|"
        r"impression|snl|roast|meme|top \d+|explained|analysis of|body language|lie detector|expert breaks")

src, outdir = sys.argv[1], Path(sys.argv[2])
d = pd.read_csv(src, dtype={"video_id": str})
t = d["title"].fillna("").str.lower()
last = d["ceo"].str.split().str[-1].str.lower()
first = d["ceo"].str.split().str[0].str.lower()
name_in = pd.Series([(l in s) or (f in s and len(f) > 3) for l, f, s in zip(last, first, t)], index=d.index)
f = d[name_in & ~t.str.contains(JUNK, regex=True) & d["duration_s"].between(180, 7200)].drop_duplicates(["video_id", "ceo_id"]).copy()  # one row per CEO stint (Niccol CMG + SBUX)
f["duration_min"] = (f["duration_s"] / 60).round(1)
f = f.sort_values(["ceo_id", "view_count"], ascending=[True, False])
f.to_csv(ROOT / "data" / "manifest" / f"candidates_for_curation{U}.csv", index=False)
outdir.mkdir(parents=True, exist_ok=True)
n = 0
for ceo, g in f.groupby("ceo_id"):
    for i in range(0, len(g), 120):
        g.iloc[i:i + 120][["video_id", "ceo", "ticker", "title", "channel", "duration_min", "view_count"]].to_csv(
            outdir / f"batch_{n:03d}.csv", index=False)
        n += 1
print(len(d), "hits ->", len(f), "prefiltered ->", n, "batches")
print(f.groupby("ceo_id").size().to_string())
