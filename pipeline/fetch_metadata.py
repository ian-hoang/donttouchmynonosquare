"""Fetch full YouTube metadata (no media) for every candidate video.

Output:
  data/cache/meta/<video_id>.json          raw yt-dlp info (not committed)
  data/manifest/candidates_meta.csv        committed: ids, channel, exact upload time, captions flag

Usage: python pipeline/fetch_metadata.py [--workers 4]
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "meta"
FIELDS = ["id", "title", "channel", "channel_id", "uploader", "duration", "upload_date", "timestamp",
          "release_timestamp", "view_count", "like_count", "live_status", "was_live", "categories"]


def fetch_one(vid: str) -> dict | None:
    import yt_dlp

    out = CACHE / f"{vid}.json"
    if out.exists():
        return json.loads(out.read_text())
    opts = {"skip_download": True, "quiet": True, "no_warnings": True, "noplaylist": True,
            "extract_flat": False, "socket_timeout": 20, "retries": 2,
            "writesubtitles": False, "writeautomaticsub": False, "ignore_no_formats_error": True,
            # the default web client gets bot-checked after ~100 requests; mweb returns full metadata
            "extractor_args": {"youtube": {"player_client": ["mweb"]}}, "sleep_interval_requests": 0.5}
    for attempt in range(3):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            keep = {k: info.get(k) for k in FIELDS}
            keep["description"] = (info.get("description") or "")[:1500]
            ac = info.get("automatic_captions") or {}
            sc = info.get("subtitles") or {}
            keep["has_auto_en"] = any(k.startswith("en") for k in ac)
            keep["has_subs_en"] = any(k.startswith("en") for k in sc)
            keep["heights"] = sorted({f.get("height") for f in info.get("formats", []) if f.get("height")})
            out.write_text(json.dumps(keep))
            return keep
        except Exception as e:  # unavailable / private / age-gated / transient
            msg = str(e)
            if "Sign in to confirm" in msg:
                time.sleep(20 * (attempt + 1))
                continue
            out.write_text(json.dumps({"id": vid, "error": msg[:300]}))
            return {"id": vid, "error": msg[:300]}
    return {"id": vid, "error": "bot-check"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--candidates", default=str(ROOT / "data" / "manifest" / "candidates_raw.csv"))
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    cand = pd.read_csv(a.candidates, dtype={"video_id": str})
    ids = list(dict.fromkeys(cand["video_id"]))
    print(f"{len(ids)} candidates")
    rows, done = [], 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(fetch_one, v): v for v in ids}
        for f in as_completed(futs):
            r = f.result()
            done += 1
            if r:
                rows.append({k: v for k, v in r.items() if k != "description"})
            if done % 100 == 0:
                print(f"  {done}/{len(ids)}", flush=True)
    meta = pd.DataFrame(rows).rename(columns={"id": "video_id"})
    df = cand.drop_duplicates("video_id").merge(meta, on="video_id", how="left", suffixes=("", "_meta"))
    keep_cols = ["video_id", "ceo", "ticker", "query", "title", "channel", "channel_id", "duration",
                 "upload_date", "timestamp", "release_timestamp", "view_count", "live_status",
                 "has_auto_en", "has_subs_en", "error"]
    df = df[[c for c in keep_cols if c in df.columns]]
    df.to_csv(ROOT / "data" / "manifest" / "candidates_meta.csv", index=False)
    print("ok", df["error"].isna().sum() if "error" in df else len(df), "of", len(df))


if __name__ == "__main__":
    main()
