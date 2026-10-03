"""GPU transcription worker (HiPerGator): faster-whisper large-v3-turbo with word timestamps.

Drains data/cache/audio/*.flac that have no data/cache/transcripts/<id>.whisper.json yet. Exits when there is
nothing left to do and no Stage A jobs remain queued, or after --max-idle seconds with no new audio, so the
GPU is never held idle (UFRC policy).

Deterministic settings: beam_size 5, temperature 0 only (no sampling fallback), no conditioning on previous
text, fixed model revision via the model name.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUD = ROOT / "data" / "cache" / "audio"
OUT = ROOT / "data" / "cache" / "transcripts"


def stage_a_running() -> bool:
    r = subprocess.run(["squeue", "--me", "-h", "-n", "pf-stageA"], capture_output=True, text=True)
    return bool(r.stdout.strip())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--max-idle", type=int, default=600)
    a = ap.parse_args()
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    OUT.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(a.model, device="cuda", compute_type="float16")
    pipe = BatchedInferencePipeline(model=model)
    idle_since = time.time()
    n = 0
    while True:
        todo = [p for p in sorted(AUD.glob("*.flac")) if not (OUT / f"{p.stem}.whisper.json").exists()
                and not (OUT / f"{p.stem}.whisper.err").exists() and time.time() - p.stat().st_mtime > 20]
        if not todo:
            if not stage_a_running() or time.time() - idle_since > a.max_idle:
                break
            time.sleep(20)
            continue
        idle_since = time.time()
        for p in todo:
            if (OUT / f"{p.stem}.whisper.json").exists():
                continue
            lock = OUT / f"{p.stem}.whisper.lock"      # several GPU workers share the queue
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            except FileExistsError:
                if time.time() - lock.stat().st_mtime < 900:
                    continue
            t0 = time.time()
            try:
                words = transcribe_one(pipe, p, a.batch)
            except Exception as e:  # one bad file must not kill the GPU job
                (OUT / f"{p.stem}.whisper.err").write_text(str(e)[:500])
                print(json.dumps({"video_id": p.stem, "error": str(e)[:200]}), flush=True)
                continue
            tmp = OUT / f"{p.stem}.whisper.json.tmp"
            tmp.write_text(json.dumps(words))
            tmp.rename(OUT / f"{p.stem}.whisper.json")
            lock.unlink(missing_ok=True)
            n += 1
            print(json.dumps({"video_id": p.stem, "words": len(words), "secs": round(time.time() - t0, 1)}), flush=True)
    print("done", n, flush=True)


def transcribe_one(pipe, p: Path, batch: int) -> list[dict]:
    import soundfile as sf

    audio, _ = sf.read(str(p), dtype="float32")   # 16 kHz mono FLAC from Stage A; bypasses PyAV
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    segs, _ = pipe.transcribe(audio, language="en", word_timestamps=True, batch_size=batch, beam_size=5,
                              temperature=0.0, condition_on_previous_text=False, vad_filter=True)
    return [{"text": w.word.strip(), "start": round(float(w.start), 3), "end": round(float(w.end), 3),
             "speaker": None, "p": round(float(w.probability), 3)} for s in segs for w in (s.words or [])]


if __name__ == "__main__":
    main()
