"""Stage A worker: download the analysis window of each curated video, run the vision pass, fetch captions,
store a 16 kHz mono FLAC of the same window, then delete the video. Resumable and safe to run as several
processes (each claims a video with an atomic lock file).

Analysis window: [WIN_START, WIN_START + WIN_SECS] seconds of the video (skips intros/title cards).
All stored times are relative to the window start.

Usage: python pipeline/run_local.py [--workers 2] [--limit N] [--ceo musk]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
WIN_START, WIN_SECS = 15, 720
MEDIA = ROOT / "data" / "media"
VIS = ROOT / "data" / "cache" / "vision"
AUD = ROOT / "data" / "cache" / "audio"
LOCK = ROOT / "data" / "cache" / "locks"
PY = sys.executable
# HiPerGator's ffmpeg has no TLS, so there we download the whole (small, 360p) file and cut locally.
SECTIONS = os.environ.get("PF_SECTIONS", "1") == "1"


def _yt(video_id: str, fmt: str, out: Path) -> Path | None:
    import yt_dlp

    opts = {"format": fmt, "outtmpl": str(out) + ".%(ext)s", "quiet": True, "no_warnings": True,
            "force_keyframes_at_cuts": False, "noplaylist": True, "retries": 3, "socket_timeout": 30,
            "concurrent_fragment_downloads": 4,
    }
    # Mac: the default web client gets bot-checked, mweb works (muxed 360p HLS). HiPerGator: the default
    # client works and serves split HLS video/audio. Set PF_YT_CLIENT=default on the cluster.
    client = os.environ.get("PF_YT_CLIENT", "mweb")
    if client != "default":
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}
    opts["merge_output_format"] = "mp4"
    if SECTIONS:  # ffmpeg with TLS (Mac): fetch only the analysis window
        opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(WIN_START, WIN_START + WIN_SECS)])
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
    hits = sorted(out.parent.glob(out.name + ".*"))
    return hits[0] if hits else None


def process(video_id: str) -> dict:
    for d in (MEDIA, VIS, AUD, LOCK):
        d.mkdir(parents=True, exist_ok=True)
    done = VIS / f"{video_id}.vision.json"
    if done.exists() and (AUD / f"{video_id}.flac").exists():
        return {"video_id": video_id, "status": "cached"}
    lock = LOCK / f"{video_id}.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime > 3600:   # stale lock from a crashed worker
        lock.unlink(missing_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return {"video_id": video_id, "status": "locked"}
    t0 = time.time()
    vpath = apath = None
    try:
        vpath = _yt(video_id, "b[protocol^=m3u8][height<=360]/bv*[protocol^=m3u8][height<=360]+ba[protocol^=m3u8]"
                              "/bv*[height<=360]+ba/b[height<=480]", MEDIA / f"{video_id}.v")
        apath = vpath
        if vpath is None:
            raise RuntimeError("download failed")
        t0 = 0 if SECTIONS else WIN_START          # where the analysis window starts inside the file
        r = subprocess.run([PY, str(ROOT / "pipeline" / "vision.py"), str(vpath), str(VIS / video_id),
                            "--start", str(t0), "--secs", str(WIN_SECS)], capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            raise RuntimeError("vision: " + r.stderr[-300:])
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", str(t0), "-i", str(apath), "-t", str(WIN_SECS),
                        "-ac", "1", "-ar", "16000", "-f", "flac", str(AUD / f"{video_id}.flac.part")], check=True)
        (AUD / f"{video_id}.flac.part").rename(AUD / f"{video_id}.flac")   # atomic: readers never see a partial file
        try:
            if os.environ.get("PF_CAPTIONS", "1") == "1":   # off on HiPerGator (YouTube 429s); Whisper there
                from transcribe import captions_words
                captions_words(video_id)
        except Exception as e:  # captions are optional (whisper/scribe fallback later)
            print(f"[{video_id}] captions: {str(e)[:100]}")
        return {"video_id": video_id, "status": "ok", "secs": round(time.time() - t0, 1)}
    except Exception as e:
        (VIS / f"{video_id}.error").write_text(str(e)[:500])
        return {"video_id": video_id, "status": "error", "error": str(e)[:200]}
    finally:
        for p in {vpath, apath}:
            if p is not None and Path(p).exists():
                Path(p).unlink()
        lock.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ceo", default="")
    ap.add_argument("--manifest", default=str(ROOT / "data" / "manifest" / "videos.csv"))
    a = ap.parse_args()
    for d in (MEDIA, VIS, AUD, LOCK):
        d.mkdir(parents=True, exist_ok=True)
    m = pd.read_csv(a.manifest, dtype={"video_id": str})
    if a.ceo:
        m = m[m["ceo_id"] == a.ceo]
    # round-robin across CEOs so every CEO's baseline fills in early
    m = m.assign(_r=m.groupby("ceo_id").cumcount()).sort_values(["_r", "ceo_id"])
    ids = [v for v in m["video_id"] if not (VIS / f"{v}.error").exists()]
    if a.limit:
        ids = ids[: a.limit]
    print(f"{len(ids)} videos, {a.workers} workers", flush=True)
    n = 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(process, ids):
            n += 1
            print(json.dumps(r), flush=True)
    print("done", n)


if __name__ == "__main__":
    main()
