"""Word-level transcripts with three interchangeable backends.

Every backend returns the same structure, a list of words in time order:
    {"text": str, "start": float, "end": float, "speaker": str | None}

  captions  YouTube automatic captions (json3), fetched with yt-dlp. Free, instant, word timing
            for auto-generated tracks; no speaker labels.
  whisper   mlx-whisper on Apple Silicon or faster-whisper on CUDA (HiPerGator), word timestamps,
            no speaker labels. Deterministic: temperature 0, no sampling fallback.
  scribe    ElevenLabs Speech-to-Text (Scribe) with diarization and audio-event tags. Needs
            ELEVENLABS_API_KEY. Responses are cached so reruns never call the API twice.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache" / "transcripts"


def _cache_path(video_id: str, backend: str) -> Path:
    return CACHE / f"{video_id}.{backend}.json"


# ----------------------------------------------------------------------------- YouTube captions

def captions_words(video_id: str, json3_path: Path | None = None) -> list[dict] | None:
    """Parse YouTube json3 automatic captions into words. Downloads the track if no path is given."""
    cp = _cache_path(video_id, "captions")
    if cp.exists():
        return json.loads(cp.read_text())
    if json3_path is None:
        import yt_dlp

        tmp = CACHE / "_subs"
        tmp.mkdir(parents=True, exist_ok=True)
        opts = {"skip_download": True, "writeautomaticsub": True, "writesubtitles": False,
                "subtitleslangs": ["en", "en-orig", "en-US"], "subtitlesformat": "json3",
                "outtmpl": str(tmp / "%(id)s.%(ext)s"), "quiet": True, "no_warnings": True,
                "ignore_no_formats_error": True}
        client = os.environ.get("PF_YT_CLIENT", "mweb")
        if client != "default":
            opts["extractor_args"] = {"youtube": {"player_client": [client]}}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        cands = sorted(tmp.glob(f"{video_id}*.json3"))
        if not cands:
            return None
        json3_path = cands[0]
    data = json.loads(Path(json3_path).read_text())
    words = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs or "tStartMs" not in ev:
            continue
        t0 = ev["tStartMs"] / 1000.0
        dur = ev.get("dDurationMs", 0) / 1000.0
        offs = [s.get("tOffsetMs", 0) / 1000.0 for s in segs]
        for i, s in enumerate(segs):
            txt = s.get("utf8", "").strip()
            if not txt or txt == "\n":
                continue
            start = t0 + offs[i]
            end = t0 + (offs[i + 1] if i + 1 < len(segs) else dur)
            words.append({"text": txt, "start": start, "end": max(end, start + 0.05), "speaker": None})
    words.sort(key=lambda w: w["start"])
    CACHE.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(words))
    return words


# ----------------------------------------------------------------------------- Whisper

def whisper_words(video_id: str, audio_path: Path, model: str | None = None) -> list[dict]:
    cp = _cache_path(video_id, "whisper")
    if cp.exists():
        return json.loads(cp.read_text())
    words = []
    if platform.system() == "Darwin":
        import mlx_whisper

        res = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=model or "mlx-community/whisper-large-v3-turbo",
                                     word_timestamps=True, temperature=0.0, language="en",
                                     condition_on_previous_text=False)
        for seg in res.get("segments", []):
            for w in seg.get("words", []):
                words.append({"text": w["word"].strip(), "start": float(w["start"]), "end": float(w["end"]),
                              "speaker": None})
    else:
        from faster_whisper import WhisperModel

        m = WhisperModel(model or "large-v3", device="cuda", compute_type="float16")
        segs, _ = m.transcribe(str(audio_path), language="en", word_timestamps=True, temperature=0.0,
                               condition_on_previous_text=False, vad_filter=True)
        for seg in segs:
            for w in seg.words or []:
                words.append({"text": w.word.strip(), "start": float(w.start), "end": float(w.end), "speaker": None})
    CACHE.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(words))
    return words


# ----------------------------------------------------------------------------- ElevenLabs Scribe

def scribe_words(video_id: str, audio_path: Path, num_speakers: int | None = None) -> list[dict] | None:
    cp = _cache_path(video_id, "scribe")
    if cp.exists():
        return json.loads(cp.read_text())
    key = os.environ.get("ELEVENLABS_API_KEY") or _env("ELEVENLABS_API_KEY")
    if not key:
        return None
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=key)
    with open(audio_path, "rb") as fh:
        kwargs = dict(file=fh, model_id="scribe_v1", diarize=True, tag_audio_events=True,
                      timestamps_granularity="word", language_code="en")
        if num_speakers:
            kwargs["num_speakers"] = num_speakers
        res = client.speech_to_text.convert(**kwargs)
    raw = res.model_dump() if hasattr(res, "model_dump") else json.loads(res.json())
    words = []
    for w in raw.get("words", []):
        if w.get("type") == "spacing":
            continue
        words.append({"text": w.get("text", "").strip(), "start": float(w.get("start") or 0.0),
                      "end": float(w.get("end") or 0.0), "speaker": w.get("speaker_id"),
                      "type": w.get("type", "word")})
    CACHE.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(words))
    (CACHE / f"{video_id}.scribe.sha").write_text(hashlib.sha256(Path(audio_path).read_bytes()).hexdigest())
    return words


def _env(key: str) -> str | None:
    f = ROOT / ".env"
    if not f.exists():
        return None
    for line in f.read_text().splitlines():
        if line.startswith(key + "="):
            v = line.split("=", 1)[1].split("#")[0].strip()
            return v or None
    return None


def best_transcript(video_id: str, audio_path: Path | None, prefer: tuple[str, ...] = ("scribe", "captions", "whisper")):
    """First backend that succeeds, in order of preference. Returns (words, backend)."""
    for b in prefer:
        try:
            if b == "scribe" and audio_path is not None:
                w = scribe_words(video_id, audio_path)
            elif b == "captions":
                w = captions_words(video_id)
            elif b == "whisper" and audio_path is not None:
                w = whisper_words(video_id, audio_path)
            else:
                w = None
            if w:
                return w, b
        except Exception as e:  # keep going down the list
            print(f"[{video_id}] {b} failed: {str(e)[:120]}")
    return [], "none"
