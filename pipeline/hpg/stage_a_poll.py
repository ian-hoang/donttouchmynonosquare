"""HiPerGator compute worker: claim videos the Mac feeder uploaded to data/media/inbox/, run vision + audio, delete
the media. Several workers share the inbox via atomic lock files. Exits after --max-idle seconds with an empty
inbox, so no allocation sits idle.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))
from run_local import AUD, LOCK, VIS, WIN_SECS  # noqa: E402

INBOX = ROOT / "data" / "media" / "inbox"


def process_file(p: Path) -> dict:
    vid = p.stem
    t0 = time.time()
    cmd = [str(ROOT / "pipeline" / "vision.py"), str(p), str(VIS / vid), "--start", "0", "--secs", str(WIN_SECS)]
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True, timeout=1800)
    alt = ROOT / ".venv010" / "bin" / "python"
    if r.returncode != 0 and alt.exists():
        # mediapipe 1.0.1's CPU dispatcher occasionally crashes on recycle; retry once with mediapipe 0.10.21
        r = subprocess.run([str(alt)] + cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        (VIS / f"{vid}.error").write_text("vision: " + r.stderr[-400:])
        return {"video_id": vid, "status": "error", "error": r.stderr[-160:]}
    part = AUD / f"{vid}.flac.part"
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(p), "-t", str(WIN_SECS), "-ac", "1",
                    "-ar", "16000", "-f", "flac", str(part)], check=True)
    part.rename(AUD / f"{vid}.flac")
    return {"video_id": vid, "status": "ok", "secs": round(time.time() - t0, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-idle", type=int, default=900)
    a = ap.parse_args()
    for d in (INBOX, VIS, AUD, LOCK):
        d.mkdir(parents=True, exist_ok=True)
    idle_since = time.time()
    while time.time() - idle_since < a.max_idle:
        files = sorted(INBOX.glob("*.mp4"), key=lambda q: q.stat().st_mtime)
        claimed = None
        for f in files:
            if time.time() - f.stat().st_mtime < 5:          # still being written by rsync
                continue
            lock = LOCK / f"{f.stem}.lock"
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                claimed = (f, lock)
                break
            except FileExistsError:
                continue
        if claimed is None:
            time.sleep(10)
            continue
        f, lock = claimed
        idle_since = time.time()
        try:
            print(json.dumps(process_file(f)), flush=True)
        except Exception as e:
            print(json.dumps({"video_id": f.stem, "status": "error", "error": str(e)[:160]}), flush=True)
        finally:
            f.unlink(missing_ok=True)
            lock.unlink(missing_ok=True)
    print("idle exit", flush=True)


if __name__ == "__main__":
    main()
