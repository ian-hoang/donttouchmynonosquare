"""Warm the identity cache: run the ArcFace identity pass for every locally available video that lacks one.
Safe to run repeatedly while Stage A is still producing outputs."""
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from assemble import identity_pass  # noqa: E402

VIS, IDN = ROOT / "data/cache/vision", ROOT / "data/cache/identity"


def one(v):
    try:
        identity_pass(v, VIS / f"{v}.face.parquet")
        return 1
    except Exception:
        return 0


if __name__ == "__main__":
    todo = [p.name.split(".")[0] for p in VIS.glob("*.vision.json")
            if (VIS / f"{p.name.split('.')[0]}.face.parquet").exists() and not (IDN / f"{p.name.split('.')[0]}.json").exists()]
    with ProcessPoolExecutor(max_workers=8) as ex:
        n = sum(ex.map(one, todo, chunksize=2))
    print(f"identity computed for {n} of {len(todo)} new videos")
