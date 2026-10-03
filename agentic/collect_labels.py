"""Collect utterance-labeling workflow output into data/features/utterance_labels.csv (committed, derived counts)."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
raw = json.loads(Path(sys.argv[1]).read_text())
res = raw.get("out") or raw.get("result", {}).get("out") or []
rows = [v for b in res if b.get("videos") for v in b["videos"]]
new = pd.DataFrame(rows)
out = ROOT / "data" / "features" / "utterance_labels.csv"
if out.exists():
    new = pd.concat([pd.read_csv(out, dtype={"video_id": str}), new], ignore_index=True)
new = new.drop_duplicates("video_id", keep="last")
new.to_csv(out, index=False)
print(len(new), "videos labeled ->", out)
