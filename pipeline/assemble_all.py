"""Stage B (Mac): identity for every processed video, per-CEO reference faces, then one feature row per
video -> data/features/video_features.csv (committed; derived numbers only).

Transcript preference: ElevenLabs Scribe (diarized) > Whisper (HiPerGator GPU) > YouTube captions.
Whisper and Scribe run on the window FLAC, so their times are already window-relative; captions are in
absolute video time and are shifted by the window start.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from assemble import assemble_video, build_references, identity_pass  # noqa: E402
from run_local import WIN_SECS, WIN_START  # noqa: E402

CACHE = ROOT / "data" / "cache"
VIS, AUD, TR = CACHE / "vision", CACHE / "audio", CACHE / "transcripts"


def transcript(video_id: str) -> tuple[list[dict], str, tuple[float, float]]:
    for backend, window in (("scribe", (0, WIN_SECS)), ("whisper", (0, WIN_SECS)),
                            ("captions", (WIN_START, WIN_START + WIN_SECS))):
        p = TR / f"{video_id}.{backend}.json"
        if p.exists():
            w = json.loads(p.read_text())
            if w:
                return w, backend, window
    return [], "none", (0, WIN_SECS)


def _ident(v: str):
    return v, identity_pass(v, VIS / f"{v}.face.parquet")


def _assemble(args):
    v, ref = args
    words, backend, window = transcript(v)
    try:
        return assemble_video(v, np.asarray(ref) if ref is not None else None, VIS,
                              AUD / f"{v}.flac" if (AUD / f"{v}.flac").exists() else None, words, backend, window)
    except Exception as e:
        return {"video_id": v, "qc_fail": f"assemble_error: {str(e)[:120]}"}


def main() -> None:
    import os
    from concurrent.futures import ProcessPoolExecutor

    os.environ.setdefault("OMP_NUM_THREADS", "2")
    workers = int(os.environ.get("PF_ASSEMBLE_WORKERS", "4"))
    man = pd.read_csv(ROOT / "data" / "manifest" / "videos.csv", dtype={"video_id": str})
    ready = [v for v in man["video_id"] if (VIS / f"{v}.vision.json").exists() and (VIS / f"{v}.face.parquet").exists()]
    print(f"{len(ready)} of {len(man)} videos have vision output", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        ident = dict(ex.map(_ident, ready, chunksize=4))
    print(f"  identity done for {len(ident)} videos", flush=True)
    video_ceo = dict(zip(man["video_id"], man["ceo_id"]))
    refs = build_references(ident, video_ceo)
    (CACHE / "identity" / "ceo_references.json").write_text(json.dumps(refs))
    print("CEO references:", sorted(refs), flush=True)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(_assemble, [(v, refs.get(video_ceo[v])) for v in ready], chunksize=4))
    feats = man.merge(pd.DataFrame(rows), on="video_id", how="inner")
    out = ROOT / "data" / "features" / "video_features.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    feats.to_csv(out, index=False)
    ok = feats["qc_fail"].isna() if "qc_fail" in feats else pd.Series(True, index=feats.index)
    print(f"wrote {len(feats)} rows ({int(ok.sum())} pass identity/face QC) -> {out}")
    print(feats[ok].groupby("ceo_id").size().to_string())


if __name__ == "__main__":
    main()
