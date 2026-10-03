"""Mac-side feeder: download each pending video's analysis window (YouTube mweb client, residential IP) and push
it to HiPerGator, where pipeline/hpg/stage_a_poll.py runs vision + audio. YouTube bot-checks the cluster's
datacenter IPs after a few hundred downloads, so the cluster only computes.

Usage: python pipeline/feeder.py [--workers 4] [--manifest data/manifest/videos.csv]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from run_local import WIN_SECS, WIN_START  # noqa: E402

OUTBOX = ROOT / "data" / "media" / "outbox"
REMOTE = "ojasvamishra@hpg.rc.ufl.edu:/blue/ai-workshop/ojasvamishra/pokerface/data/media/inbox/"
SSH = ["ssh", "-o", f"ControlPath={Path.home()}/.ssh/cm-hpg", "-o", "BatchMode=yes", "ojasvamishra@hpg.rc.ufl.edu"]
FMT = "b[protocol^=m3u8][height<=360]/bv*[protocol^=m3u8][height<=360]+ba[protocol^=m3u8]/bv*[height<=360]+ba/b[height<=480]"


def remote_done() -> set[str]:
    r = subprocess.run(SSH + ["cd /blue/ai-workshop/$USER/pokerface/data && ls cache/vision | grep vision.json; "
                              "ls media/inbox 2>/dev/null"], capture_output=True, text=True, timeout=120)
    return {l.split(".")[0] for l in r.stdout.split()}


def download(vid: str) -> str:
    import yt_dlp

    out = OUTBOX / f"{vid}.v"
    opts = {"format": FMT, "outtmpl": str(out) + ".%(ext)s", "quiet": True, "no_warnings": True, "noplaylist": True,
            "download_ranges": yt_dlp.utils.download_range_func(None, [(WIN_START, WIN_START + WIN_SECS)]),
            "retries": 3, "socket_timeout": 30, "merge_output_format": "mp4",
            "extractor_args": {"youtube": {"player_client": ["mweb"]}}}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])
        hits = [p for p in OUTBOX.glob(f"{vid}.v.*") if not p.name.endswith((".part", ".ytdl"))]
        if not hits:
            return "nofile"
        hits[0].rename(OUTBOX / f"{vid}.mp4")   # final name only when complete, so the uploader never ships partials
        return "ok"
    except Exception as e:
        msg = str(e)
        return "botcheck" if "Sign in to confirm" in msg else f"error: {msg[:80]}"


def uploader(stop: threading.Event) -> None:
    while not stop.is_set() or any(OUTBOX.glob("*.mp4")):
        if any(OUTBOX.glob("*.mp4")):
            subprocess.run(["rsync", "-a", "--remove-source-files", "--include=*.mp4", "--exclude=*",
                            "-e", f"ssh -o ControlPath={Path.home()}/.ssh/cm-hpg", f"{OUTBOX}/", REMOTE],
                           capture_output=True)
        time.sleep(10)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--manifest", default=str(ROOT / "data" / "manifest" / "videos.csv"))
    a = ap.parse_args()
    OUTBOX.mkdir(parents=True, exist_ok=True)
    subprocess.run(SSH + ["mkdir -p /blue/ai-workshop/$USER/pokerface/data/media/inbox"], check=True)
    done = remote_done()
    man = pd.read_csv(a.manifest, dtype={"video_id": str})
    man = man.assign(_r=man.groupby("ceo_id").cumcount()).sort_values(["_r", "ceo_id"])  # round-robin CEOs
    todo = [v for v in man["video_id"] if v not in done]
    print(f"{len(todo)} to feed ({len(done)} already done/queued)", flush=True)
    stop = threading.Event()
    up = threading.Thread(target=uploader, args=(stop,), daemon=True)
    up.start()
    counts: dict[str, int] = {}
    bot_streak = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, (vid, st) in enumerate(zip(todo, ex.map(download, todo))):
            key = st.split(":")[0]
            counts[key] = counts.get(key, 0) + 1
            bot_streak = bot_streak + 1 if st == "botcheck" else 0
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(todo)} {counts}", flush=True)
            if bot_streak >= 15:
                print("15 bot-checks in a row; pausing 5 minutes", flush=True)
                time.sleep(300)
                bot_streak = 0
    stop.set()
    up.join(timeout=600)
    print("done", counts, flush=True)


if __name__ == "__main__":
    main()
