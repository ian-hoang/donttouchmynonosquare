"""Turn per-frame landmarks + audio + transcript into one feature row per video (runs on the Mac).

Steps
1. Identity. Link face boxes into tracks (IoU), embed the aligned crops with ArcFace (MobileFaceNet,
   InsightFace buffalo_sc, run locally, never on UF systems), cluster tracks by identity. The CEO is the
   face that recurs across that CEO's videos: a per-CEO reference embedding is the consensus of the
   dominant clusters across videos (`build_references`). In each video the target is the cluster most
   similar to the reference; videos where nothing matches (cos < MIN_ID_COS) are dropped as not-the-CEO.
2. Who is talking. With diarization (ElevenLabs Scribe) the CEO speaker is the label whose words coincide
   with the target's mouth movement. Without it, a word is the CEO's when the target face is on screen
   with an active mouth at that moment. Unattributable words are dropped (conservative).
3. Features: facial cues on target frames, vocal features on CEO speech, text features on CEO words.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from audio_features import acoustic_features, timing_features
from text_features import text_features

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
CACHE = ROOT / "data" / "cache"
MIN_ID_COS = 0.35
FPS = 4.0

# ----------------------------------------------------------------------------- tracks + identity

def link_tracks(f: pd.DataFrame, fps: float = FPS, iou_min: float = 0.3) -> pd.DataFrame:
    f = f.sort_values(["t_ms", "face_idx"]).reset_index(drop=True)
    step = 1000.0 / fps
    tid = np.full(len(f), -1)
    nxt, prev = 0, []
    x0, y0, x1, y1 = (f[c].to_numpy() for c in ("x0", "y0", "x1", "y1"))
    area = (x1 - x0) * (y1 - y0)
    t = f["t_ms"].to_numpy()
    for tt, g in f.groupby("t_ms", sort=True):
        cand = [p for p in prev if abs(tt - t[p] - step) < step / 2]
        used, cur = set(), []
        for i in g.index:
            best, bi = iou_min, None
            for p in cand:
                if p in used:
                    continue
                ix = max(0.0, min(x1[i], x1[p]) - max(x0[i], x0[p]))
                iy = max(0.0, min(y1[i], y1[p]) - max(y0[i], y0[p]))
                inter = ix * iy
                u = area[i] + area[p] - inter
                if u > 0 and inter / u > best:
                    best, bi = inter / u, p
            if bi is None:
                tid[i] = nxt
                nxt += 1
            else:
                tid[i] = tid[bi]
                used.add(bi)
            cur.append(i)
        prev = cur
    f["track_id"] = tid
    return f


_ARC = None


def _arcface():
    global _ARC
    if _ARC is None:
        import onnxruntime as ort

        _ARC = ort.InferenceSession(str(MODELS / "buffalo_sc" / "w600k_mbf.onnx"), providers=["CPUExecutionProvider"])
    return _ARC


def embed_crops(f: pd.DataFrame) -> np.ndarray:
    import cv2

    sess = _arcface()
    inp = sess.get_inputs()[0].name
    emb = np.full((len(f), 512), np.nan, np.float32)
    idx = np.flatnonzero(f["crop_jpg"].notna().to_numpy())
    batch, rows = [], []
    for i in idx:
        img = cv2.imdecode(np.frombuffer(f["crop_jpg"].iat[i], np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32)
        batch.append(((rgb - 127.5) / 127.5).transpose(2, 0, 1))
        rows.append(i)
        if len(batch) == 64 or i == idx[-1]:
            out = sess.run(None, {inp: np.stack(batch)})[0]
            out /= np.linalg.norm(out, axis=1, keepdims=True)
            emb[rows] = out
            batch, rows = [], []
    if batch:
        out = sess.run(None, {inp: np.stack(batch)})[0]
        out /= np.linalg.norm(out, axis=1, keepdims=True)
        emb[rows] = out
    return emb


def cluster_tracks(f: pd.DataFrame, emb: np.ndarray, tau: float = 0.4) -> tuple[np.ndarray, list[dict]]:
    """Greedy clustering of track-mean embeddings. Returns cluster id per row and cluster summaries."""
    ok = ~np.isnan(emb[:, 0])
    tracks = f[ok].groupby("track_id").size().sort_values(ascending=False)
    cents, members, tr2c = [], [], {}
    for tid in tracks.index:
        e = emb[(f["track_id"] == tid).to_numpy() & ok].mean(0)
        e /= np.linalg.norm(e)
        sims = [c @ e for c in cents]
        if sims and max(sims) >= tau:
            k = int(np.argmax(sims))
            members[k].append(e)
            c = np.mean(members[k], 0)
            cents[k] = c / np.linalg.norm(c)
        else:
            k = len(cents)
            cents.append(e)
            members.append([e])
        tr2c[tid] = k
    cl = f["track_id"].map(tr2c).fillna(-1).astype(int).to_numpy()
    n_frames = f["t_ms"].nunique()
    summ = []
    for k, c in enumerate(cents):
        m = cl == k
        summ.append({"cluster": k, "centroid": c.tolist(), "frames": int(f.loc[m, "t_ms"].nunique()),
                     "screen_frac": float(f.loc[m, "t_ms"].nunique() / max(n_frames, 1)),
                     "median_face_w": float(f.loc[m, "fw"].median())})
    return cl, summ


def identity_pass(video_id: str, face_path: Path) -> dict:
    """Stage 1 (per video): tracks, embeddings, clusters. Cached as JSON + parquet of cluster labels."""
    out_json = CACHE / "identity" / f"{video_id}.json"
    if out_json.exists():
        return json.loads(out_json.read_text())
    f = pd.read_parquet(face_path)
    if f.empty:
        res = {"video_id": video_id, "clusters": [], "n_frames": 0}
    else:
        f = link_tracks(f)
        emb = embed_crops(f)
        cl, summ = cluster_tracks(f, emb)
        f["cluster"] = cl
        (CACHE / "identity").mkdir(parents=True, exist_ok=True)
        f.drop(columns=["crop_jpg"]).to_parquet(CACHE / "identity" / f"{video_id}.faces.parquet")
        res = {"video_id": video_id, "clusters": summ, "n_frames": int(f["t_ms"].nunique())}
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(res))
    return res


def build_references(identity: dict[str, dict], video_ceo: dict[str, str], min_screen: float = 0.10) -> dict:
    """Per CEO: the dominant-cluster centroid that agrees most with dominant clusters of the CEO's other
    videos (the CEO recurs, interviewers do not). Returns {ceo_id: unit vector}."""
    by_ceo: dict[str, list[np.ndarray]] = {}
    for vid, res in identity.items():
        cents = [np.array(c["centroid"]) for c in res.get("clusters", []) if c["screen_frac"] >= min_screen]
        if cents and vid in video_ceo:
            by_ceo.setdefault(video_ceo[vid], []).extend(cents)
    refs = {}
    for ceo, cents in by_ceo.items():
        C = np.stack(cents)
        if len(C) < 3:
            continue
        S = C @ C.T
        np.fill_diagonal(S, np.nan)
        support = np.nanmean(S > 0.45, axis=1)                  # how many other clusters look like this one
        best = int(np.nanargmax(support))
        close = C[S[best] > 0.45] if np.any(S[best] > 0.45) else C[[best]]
        ref = np.vstack([C[[best]], close]).mean(0)
        refs[ceo] = (ref / np.linalg.norm(ref)).tolist()
    return refs


# ----------------------------------------------------------------------------- facial cues

def _m(df: pd.DataFrame, a: str, b: str) -> pd.Series:
    return (df[a] + df[b]) / 2.0


def mouth_activity(face: pd.DataFrame) -> pd.Series:
    """Rolling std (+/-0.5 s) of mouth opening: high while talking, low while listening."""
    s = face["jawOpen"] + _m(face, "mouthLowerDownLeft", "mouthLowerDownRight")
    return s.rolling(5, center=True, min_periods=3).std()


def face_cues(f: pd.DataFrame, pose: pd.DataFrame | None, fps: float = FPS) -> dict:
    """f: TARGET rows only, one per frame. Literature mapping in docs/research/literature.md."""
    f = f.sort_values("t_ms").reset_index(drop=True)
    minutes = len(f) / fps / 60.0
    out = {"face_minutes": minutes}
    if len(f) < fps * 60:                      # need >= 1 minute of the CEO's face
        return out
    contiguous = np.r_[True, np.diff(f["t_ms"].to_numpy()) <= 1000 / fps * 1.5]
    blink = _m(f, "eyeBlinkLeft", "eyeBlinkRight")
    thr = float(max(0.35, blink.median() + 0.5 * (blink.quantile(0.99) - blink.median())))
    closed = (blink > thr).to_numpy()
    onsets = closed & ~np.r_[False, closed[:-1]]
    out["fc_blink_per_min"] = float(onsets.sum() / minutes)
    out["fc_lip_press"] = float(_m(f, "mouthPressLeft", "mouthPressRight").mean())
    out["fc_lip_roll"] = float(((f["mouthRollLower"] + f["mouthRollUpper"]) / 2).mean())
    out["fc_chin_raise"] = float(f["mouthShrugLower"].mean())
    out["fc_brow_inner_up"] = float(f["browInnerUp"].mean())
    out["fc_brow_down"] = float(_m(f, "browDownLeft", "browDownRight").mean())
    smile = _m(f, "mouthSmileLeft", "mouthSmileRight")
    cheek = _m(f, "cheekSquintLeft", "cheekSquintRight")
    eyesq = _m(f, "eyeSquintLeft", "eyeSquintRight")
    sm = smile > 0.3
    out["fc_smile_frac"] = float(sm.mean())
    out["fc_duchenne_frac"] = float(((cheek > 0.1) | (eyesq > 0.4))[sm].mean()) if sm.sum() >= 10 else np.nan
    out["fc_pleasant"] = float((smile * ((cheek > 0.1) | (eyesq > 0.4))).mean())
    big = smile > 0.2
    out["fc_smile_asym"] = float(((f["mouthSmileLeft"] - f["mouthSmileRight"]).abs()
                                  / (f["mouthSmileLeft"] + f["mouthSmileRight"] + 1e-6))[big].mean()) if big.sum() >= 10 else np.nan
    out["fc_sneer"] = float(_m(f, "noseSneerLeft", "noseSneerRight").mean())
    out["fc_expressivity"] = float(f[[c for c in f.columns if c.startswith(("brow", "mouth", "cheek", "jaw"))]].std().mean())
    d = f[["yaw", "pitch", "roll"]].diff().abs().sum(axis=1).to_numpy() * fps
    d = d[contiguous & (np.arange(len(f)) > 0)]
    d = d[d < 200]
    out["fc_head_motion"] = float(np.median(d)) if len(d) else np.nan
    if "gaze_l" in f:
        g = ((f["gaze_l"] + f["gaze_r"]) / 2.0).dropna()
        out["fc_gaze_aversion"] = float(((g - g.median()).abs() > 0.12).mean()) if len(g) else np.nan
    if pose is not None and len(pose):
        P = pose.merge(f[["t_ms", "cx", "cy", "fw", "x0", "x1", "y0", "y1"]], on="t_ms")
        P["dn"] = np.hypot(P["nose_x"] - P["cx"], P["nose_y"] - P["cy"]) / P["fw"]
        P = P[P["dn"] < 1.0].sort_values("dn").drop_duplicates("t_ms").sort_values("t_ms").reset_index(drop=True)
        if len(P) >= 60:
            touch = np.zeros(len(P), bool)
            pad = 0.2
            for nm in ("wr_l", "wr_r", "index_l", "index_r", "thumb_l", "thumb_r"):
                vis = P[f"{nm}_v"] > 0.5
                inside = ((P[f"{nm}_x"] > P["x0"] - pad * P["fw"]) & (P[f"{nm}_x"] < P["x1"] + pad * P["fw"]) &
                          (P[f"{nm}_y"] > P["y0"] - pad * P["fw"]) & (P[f"{nm}_y"] < P["y1"] + pad * P["fw"]))
                touch |= (vis & inside).to_numpy()
            out["fc_self_touch"] = float(touch.mean())
            sw = (P["sh_l_x"] - P["sh_r_x"]).abs().clip(lower=1e-3)
            pose_fps = 1000.0 / max(np.median(np.diff(P["t_ms"])), 1)
            cont = np.r_[False, np.diff(P["t_ms"].to_numpy()) <= 1000 / pose_fps * 1.5]
            sp = []
            for s in ("l", "r"):
                v = ((P[f"wr_{s}_v"] > 0.5).to_numpy() & np.r_[False, (P[f"wr_{s}_v"] > 0.5).to_numpy()[:-1]] & cont)
                spd = (np.hypot(P[f"wr_{s}_x"].diff(), P[f"wr_{s}_y"].diff()) / sw * pose_fps).to_numpy()
                sp.append(spd[v])
            sp = np.concatenate(sp)
            out["fc_hands_visible"] = float(((P["wr_l_v"] > 0.5) | (P["wr_r_v"] > 0.5)).mean())
            out["fc_gesture_energy"] = float(np.median(sp)) if len(sp) >= 30 else np.nan
    return out


# ----------------------------------------------------------------------------- speech attribution

def attribute_words(words: list[dict], faces: pd.DataFrame, target_cluster: int) -> tuple[list[dict], dict]:
    """Return the CEO's words and attribution QC."""
    if not words:
        return [], {"attr_method": "none"}
    tgt = faces[faces["cluster"] == target_cluster].sort_values("t_ms")
    tgt = tgt.drop_duplicates("t_ms")
    act = mouth_activity(tgt.reset_index(drop=True)).to_numpy()
    thr = float(np.nanquantile(act, 0.4)) if np.isfinite(act).sum() > 20 else np.inf
    t_tgt = tgt["t_ms"].to_numpy()
    others = faces[faces["cluster"] != target_cluster]
    t_any = np.sort(faces["t_ms"].unique())

    def target_talking(ms: float) -> int:     # 1 talking, 0 visible but not talking, -1 unknown
        j = np.searchsorted(t_tgt, ms)
        best = None
        for k in (j - 1, j):
            if 0 <= k < len(t_tgt) and abs(t_tgt[k] - ms) <= 300:
                best = k if best is None or abs(t_tgt[k] - ms) < abs(t_tgt[best] - ms) else best
        if best is None:
            return -1
        return 1 if np.isfinite(act[best]) and act[best] >= thr else 0

    speakers = {w.get("speaker") for w in words if w.get("speaker") is not None}
    if len(speakers) >= 2:                                         # diarized (Scribe)
        score = {}
        for s in speakers:
            ws = [w for w in words if w.get("speaker") == s]
            if len(ws) < 50:
                continue
            lab = np.array([target_talking(1000 * (w["start"] + w["end"]) / 2) for w in ws])
            seen = lab >= 0
            score[s] = float((lab[seen] == 1).mean()) if seen.sum() >= 20 else 0.0
        if score:
            ceo = max(score, key=score.get)
            ceo_words = [w for w in words if w.get("speaker") == ceo]
            return ceo_words, {"attr_method": "diarized", "ceo_speaker": ceo, "ceo_speaker_mouth_match": score[ceo]}
    # Visual path: vote per utterance (words separated by < 1 s), not per word. An utterance is the CEO's when,
    # over the frames it spans, the target is talking in most frames where the target is visible, the target is
    # visible in at least 40% of them, and no other identity is talking more often than the target.
    words = [w for w in words if w.get("type") != "audio_event"]
    oth = others.sort_values("t_ms")
    oth_act = {}
    for cl, g in oth.groupby("cluster"):
        g = g.drop_duplicates("t_ms").reset_index(drop=True)
        a = mouth_activity(g).to_numpy()
        oth_act[cl] = (g["t_ms"].to_numpy(), a)

    def other_talking(ms: float) -> bool:
        for t_o, a_o in oth_act.values():
            j = np.searchsorted(t_o, ms)
            for k in (j - 1, j):
                if 0 <= k < len(t_o) and abs(t_o[k] - ms) <= 300 and np.isfinite(a_o[k]) and a_o[k] >= thr:
                    return True
        return False

    utts, cur = [], []
    for w in words:   # split at pauses > 0.6 s and cap each voting unit at 15 s
        if cur and (w["start"] - cur[-1]["end"] > 0.6 or w["end"] - cur[0]["start"] > 15.0):
            utts.append(cur)
            cur = []
        cur.append(w)
    if cur:
        utts.append(cur)
    ceo_words, n_vote = [], 0
    for u in utts:
        grid = np.arange(1000 * u[0]["start"], 1000 * u[-1]["end"] + 1, 250.0)
        lab = np.array([target_talking(ms) for ms in grid])
        vis = lab >= 0
        if vis.mean() < 0.4:
            continue
        tgt_talk = (lab == 1).sum()
        oth_talk = sum(other_talking(ms) for ms in grid[~(lab == 1)])
        if tgt_talk >= 0.5 * vis.sum() and tgt_talk >= oth_talk:
            ceo_words.extend(u)
            n_vote += 1
    return ceo_words, {"attr_method": "visual_utterance", "mouth_thr": thr, "n_utterances": len(utts),
                       "n_ceo_utterances": n_vote}


def speech_segments(ceo_words: list[dict], max_gap: float = 0.6) -> list[tuple[float, float]]:
    segs: list[list[float]] = []
    for w in ceo_words:
        if segs and w["start"] - segs[-1][1] <= max_gap:
            segs[-1][1] = max(segs[-1][1], w["end"])
        else:
            segs.append([w["start"], w["end"]])
    return [(a, b) for a, b in segs]


# ----------------------------------------------------------------------------- one video

def assemble_video(video_id: str, ceo_ref: np.ndarray | None, face_dir: Path, audio_path: Path | None,
                   words: list[dict], transcript_backend: str, window: tuple[float, float]) -> dict:
    ident = identity_pass(video_id, face_dir / f"{video_id}.face.parquet")
    row = {"video_id": video_id, "transcript_backend": transcript_backend}
    if not ident["clusters"]:
        return {**row, "qc_fail": "no_faces"}
    faces = pd.read_parquet(CACHE / "identity" / f"{video_id}.faces.parquet")
    cents = np.array([c["centroid"] for c in ident["clusters"]])
    if ceo_ref is not None:
        sims = cents @ np.asarray(ceo_ref)
        k = int(np.argmax(sims))
        row["id_cos"] = float(sims[k])
        if sims[k] < MIN_ID_COS:
            return {**row, "qc_fail": "ceo_not_found"}
    else:
        k = int(np.argmax([c["screen_frac"] for c in ident["clusters"]]))
        row["id_cos"] = np.nan
    row["target_screen_frac"] = ident["clusters"][k]["screen_frac"]
    row["n_identities"] = len([c for c in ident["clusters"] if c["screen_frac"] >= 0.05])
    tgt = faces[faces["cluster"] == k].sort_values("fw").drop_duplicates("t_ms", keep="last")
    pose_path = face_dir / f"{video_id}.pose.parquet"
    pose = pd.read_parquet(pose_path) if pose_path.exists() else None
    row.update(face_cues(tgt, pose))
    lo, hi = window   # absolute video seconds; stored frames and audio are relative to `lo`
    w_in = [{**w, "start": w["start"] - lo, "end": w["end"] - lo} for w in words if lo <= w["start"] <= hi]
    ceo_words, attr = attribute_words(w_in, faces, k)
    row.update(attr)
    row["n_words_window"] = len(w_in)
    segs = speech_segments(ceo_words)
    speech_s = float(sum(b - a for a, b in segs))
    if ceo_words:   # CEO-only text for the utterance-labeling agent (local cache; transcripts are never committed)
        tdir = CACHE / "ceo_text"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / f"{video_id}.json").write_text(json.dumps(
            [{"start": round(a, 2), "end": round(b, 2),
              "text": " ".join(w["text"] for w in ceo_words if a <= w["start"] <= b)} for a, b in segs]))
    row["ceo_speech_s"] = speech_s
    row.update(text_features(" ".join(w["text"] for w in ceo_words), speech_seconds=speech_s))
    row.update(timing_features(w_in, attr.get("ceo_speaker")) if attr.get("attr_method") == "diarized"
               else timing_features(ceo_words, None))
    if audio_path is not None and Path(audio_path).exists() and segs:
        import soundfile as sf

        y, sr = sf.read(str(audio_path), dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        row.update(acoustic_features(y, sr, segs))
    return row
