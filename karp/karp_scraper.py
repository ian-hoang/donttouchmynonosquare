"""
karp_scraper.py - build a verified, deduped, timestamped manifest of Alex Karp appearances.

Stages (run in order, each reads/writes files in ./data):
  python karp_scraper.py discover   # YouTube search + channel search + GDELT TV airtimes -> candidates.jsonl
  python karp_scraper.py verify     # face-check sampled frames against refs/*.jpg      -> verified.jsonl
  python karp_scraper.py dedupe     # collapse re-uploads, keep best-timestamped copy    -> manifest.csv
  python karp_scraper.py download   # 720p video + 16 kHz mono wav for manifest rows     -> media/

Setup:
  pip install yt-dlp requests opencv-python face_recognition pandas
  (face_recognition needs dlib: `brew install cmake` / `apt install cmake` first)
  ffmpeg must be on PATH.
  Put 5-10 clear, front-facing photos of Karp in ./refs/ (crop from known-good clips).

Notes:
  - YouTube `timestamp` is UPLOAD time; for re-uploaded TV segments it can lag airtime by hours.
    GDELT rows carry true TV airtime (coverage may end ~Oct 2024 - check your first query).
  - Keep media local; don't redistribute. Disclose scraping method in your submission.
"""
import csv, json, re, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from urllib.parse import urlencode

import requests
import yt_dlp

DATA = Path("data"); DATA.mkdir(exist_ok=True)
MEDIA = Path("media"); MEDIA.mkdir(exist_ok=True)
REFS = Path("refs")

# ---------------- config ----------------
SEARCH_QUERIES = [
    "Alex Karp interview", "Alex Karp Palantir CEO", "Alex Karp podcast",
    "Alex Karp CNBC", "Alex Karp Bloomberg", "Alex Karp Fox Business",
    "Alex Karp conference", "Palantir earnings call",
]
SEARCH_DEPTH = 300  # results per query (ytsearchdateN)

# Official / primary-source channels: searched directly, and preferred when deduping.
CHANNEL_HANDLES = [
    "@CNBCtelevision", "@markets", "@FoxBusiness", "@YahooFinance",
    "@PalantirTech", "@ReaganInstitute", "@AspenInstitute",
]
GDELT_STATIONS = ["CNBC", "BLOOMBERG", "FBC"]
GDELT_START, GDELT_END = "20200101000000", datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

MIN_DURATION_S = 180
FRAMES_PER_VIDEO = 12
FACE_TOLERANCE = 0.5
MIN_MATCH_FRAC = 0.25   # fraction of sampled frames that must contain Karp

YDL_QUIET = {"quiet": True, "no_warnings": True, "ignoreerrors": True}


# ---------------- helpers ----------------
def write_jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

def read_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

def mentions_karp(text):
    return bool(re.search(r"\bkarp\b", text or "", re.I))


# ---------------- stage 1: discover ----------------
def _flat(url, n=SEARCH_DEPTH):
    # ytsearchdateN: is unsupported in current yt-dlp; search-results URLs (sp=CAI = sort by upload date) work
    with yt_dlp.YoutubeDL({**YDL_QUIET, "extract_flat": True, "playlist_items": f"1:{n}"}) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    return [e for e in (info.get("entries") or []) if e and e.get("id")]

def _full(vid):
    with yt_dlp.YoutubeDL({**YDL_QUIET, "skip_download": True}) as ydl:
        i = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
    if not i:
        return None
    ts = i.get("release_timestamp") or i.get("timestamp")
    return {
        "source": "youtube", "id": vid, "url": i.get("webpage_url"),
        "title": i.get("title"), "description": (i.get("description") or "")[:2000],
        "channel": i.get("channel"), "channel_handle": i.get("uploader_id"),
        "duration": i.get("duration"),
        "event_time": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None,
        "time_source": "yt_release_timestamp" if i.get("release_timestamp") else
                       ("yt_upload_timestamp" if ts else "yt_upload_date_only"),
        "upload_date": i.get("upload_date"),
        "was_live": i.get("was_live"),
    }

def _gdelt():
    rows = []
    for st in GDELT_STATIONS:
        params = {
            "query": f'"alex karp" station:{st}', "mode": "clipgallery",
            "format": "json", "maxrecords": 3000,
            "startdatetime": GDELT_START, "enddatetime": GDELT_END,
        }
        try:
            r = requests.get("https://api.gdeltproject.org/api/v2/tv/tv", params=params, timeout=60)
            clips = r.json().get("clips", [])
        except Exception as e:
            print(f"  GDELT {st} failed: {e}"); continue
        print(f"  GDELT {st}: {len(clips)} clips")
        for c in clips:
            rows.append({
                "source": "gdelt_tv", "id": c.get("ia_show_id") or c.get("preview_url"),
                "url": c.get("preview_url"), "title": c.get("show"), "channel": c.get("station"),
                "snippet": c.get("snippet"), "event_time": c.get("date"),
                "time_source": "tv_airtime_captions",
            })
        time.sleep(2)  # be polite
    return rows

def discover():
    ids = set()
    for q in SEARCH_QUERIES:
        hits = _flat("https://www.youtube.com/results?" + urlencode({"search_query": q, "sp": "CAI%3D"}, safe="%"))
        print(f"  search '{q}': {len(hits)}"); ids.update(h["id"] for h in hits)
    for h in CHANNEL_HANDLES:
        hits = _flat(f"https://www.youtube.com/{h}/search?query=karp")
        print(f"  channel {h}: {len(hits)}"); ids.update(x["id"] for x in hits)
    print(f"enriching {len(ids)} unique videos...")
    with ThreadPoolExecutor(8) as ex:
        yt = [r for r in ex.map(_full, ids) if r]
    yt = [r for r in yt
          if (r["duration"] or 0) >= MIN_DURATION_S
          and mentions_karp(r["title"] + " " + r["description"])]
    rows = yt + _gdelt()
    write_jsonl(DATA / "candidates.jsonl", rows)
    print(f"candidates: {len(yt)} youtube + {len(rows) - len(yt)} gdelt -> data/candidates.jsonl")


# ---------------- stage 2: verify ----------------
def _ref_encodings():
    import face_recognition as fr
    encs = []
    for p in REFS.glob("*.[jp][pn]g"):
        e = fr.face_encodings(fr.load_image_file(p))
        if e: encs.append(e[0])
    if not encs:
        sys.exit("No usable reference faces in ./refs/")
    return encs

def _match_frac(url, refs):
    import cv2, face_recognition as fr
    with tempfile.TemporaryDirectory() as td:
        opts = {**YDL_QUIET, "format": "worstvideo[height>=240]/worst",
                "outtmpl": f"{td}/v.%(ext)s"}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = list(Path(td).glob("v.*"))
        if not files: return None
        cap = cv2.VideoCapture(str(files[0]))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        hits = tried = 0
        for k in range(FRAMES_PER_VIDEO):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (k + 0.5) / FRAMES_PER_VIDEO))
            ok, frame = cap.read()
            if not ok: continue
            tried += 1
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            for e in fr.face_encodings(rgb):
                if any(fr.compare_faces(refs, e, tolerance=FACE_TOLERANCE)):
                    hits += 1; break
        cap.release()
        return hits / tried if tried else None

def verify():
    refs = _ref_encodings()
    rows = read_jsonl(DATA / "candidates.jsonl")
    out = []
    for i, r in enumerate(rows):
        if r["source"] != "youtube":
            r["face_match_frac"] = None; out.append(r); continue  # GDELT rows: verified by captions
        try:
            frac = _match_frac(r["url"], refs)
        except Exception as e:
            print(f"  [{i}] error {r['id']}: {e}"); continue
        r["face_match_frac"] = frac
        keep = frac is not None and frac >= MIN_MATCH_FRAC
        print(f"  [{i+1}/{len(rows)}] {frac} {'KEEP' if keep else 'drop'}  {r['title'][:70]}")
        if keep: out.append(r)
    write_jsonl(DATA / "verified.jsonl", out)
    print(f"verified: {len(out)} -> data/verified.jsonl")


# ---------------- stage 3: dedupe ----------------
TIME_RANK = {"tv_airtime_captions": 0, "yt_release_timestamp": 1,
             "yt_upload_timestamp": 2, "yt_upload_date_only": 3}

def _tokens(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower())) - {"alex", "karp", "palantir", "ceo", "the", "a", "on", "and"}

def _same(a, b):
    """Heuristic re-upload match: similar duration, close dates, overlapping title tokens."""
    if abs((a.get("duration") or 0) - (b.get("duration") or 0)) > 5: return False
    da, db = a.get("event_time"), b.get("event_time")
    if da and db and abs((datetime.fromisoformat(da) - datetime.fromisoformat(db)).days) > 3: return False
    ta, tb = _tokens(a["title"]), _tokens(b["title"])
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.3

def _priority(r):
    official = (r.get("channel_handle") or "").lower() in {h.lower() for h in CHANNEL_HANDLES}
    return (TIME_RANK.get(r["time_source"], 9), not official, r.get("event_time") or "9999")

def dedupe():
    rows = [r for r in read_jsonl(DATA / "verified.jsonl") if r["source"] == "youtube"]
    gdelt = [r for r in read_jsonl(DATA / "verified.jsonl") if r["source"] == "gdelt_tv"]
    groups = []
    for r in sorted(rows, key=_priority):
        for g in groups:
            if _same(g[0], r):
                g.append(r); break
        else:
            groups.append([r])
    canon = []
    for g in groups:
        best = min(g, key=_priority)
        best["n_reuploads"] = len(g) - 1
        best["time_confidence"] = {0: "high", 1: "high", 2: "medium"}.get(TIME_RANK.get(best["time_source"]), "low")
        canon.append(best)
    for r in gdelt:
        r["n_reuploads"] = 0; r["time_confidence"] = "high"
    cols = ["source", "id", "url", "title", "channel", "duration", "event_time",
            "time_source", "time_confidence", "n_reuploads", "face_match_frac", "was_live"]
    with open(DATA / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in sorted(canon + gdelt, key=lambda r: r.get("event_time") or ""):
            w.writerow(r)
    print(f"manifest: {len(canon)} unique YouTube + {len(gdelt)} GDELT airtimes -> data/manifest.csv")
    print("Next: manually join GDELT airtimes to matching YouTube clips to upgrade their timestamps.")


# ---------------- stage 4: download ----------------
def download():
    with open(DATA / "manifest.csv") as f:
        urls = [r["url"] for r in csv.DictReader(f) if r["source"] == "youtube"]
    vopts = {**YDL_QUIET, "format": "bv*[height<=720]+ba/b[height<=720]",
             "outtmpl": str(MEDIA / "%(id)s.%(ext)s"), "merge_output_format": "mp4"}
    aopts = {**YDL_QUIET, "format": "ba", "outtmpl": str(MEDIA / "%(id)s.%(ext)s"),
             "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
             "postprocessor_args": {"extractaudio": ["-ar", "16000", "-ac", "1"]}}
    with yt_dlp.YoutubeDL(vopts) as ydl: ydl.download(urls)
    with yt_dlp.YoutubeDL(aopts) as ydl: ydl.download(urls)
    print(f"downloaded {len(urls)} clips -> media/")


if __name__ == "__main__":
    stages = {"discover": discover, "verify": verify, "dedupe": dedupe, "download": download}
    if len(sys.argv) != 2 or sys.argv[1] not in stages:
        sys.exit(f"usage: python {sys.argv[0]} [{'|'.join(stages)}]")
    stages[sys.argv[1]]()
