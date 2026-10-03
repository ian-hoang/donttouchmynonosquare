"""MediaPipe face + pose landmarks for every face in a video, sampled at a fixed rate.

Deterministic: fixed fps grid, fixed resize, fixed model files, no tracking state shared across videos.
Runs on macOS (GPU delegate, RGBA input; the CPU delegate aborts on mediapipe 1.0.1/macOS) and on Linux
HiPerGator nodes (CPU delegate).

mediapipe 1.0.1 leaks ~1.9 MB per frame in FaceLandmarker/PoseLandmarker; we recreate the landmarker
every RECYCLE frames, which holds RSS flat (~280 MB). That leak is what crashed the first run.

Usage: python pipeline/vision.py VIDEO OUT_PREFIX [--fps 4] [--height 360] [--start 15] [--secs 1200]
       -> OUT_PREFIX.face.parquet, OUT_PREFIX.pose.parquet
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODELS = Path(os.environ.get("PF_MODELS", ROOT / "models"))
MODEL_URLS = {
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
    "pose_landmarker_lite.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
}
RECYCLE = int(os.environ.get("PF_RECYCLE", 150))
# MediaPipe 478-mesh points for 5-point face alignment: eye centers, nose tip, mouth corners
KP5 = [(33, 133), (362, 263), (1,), (61,), (291,)]
POSE_KEEP = {0: "nose", 11: "sh_l", 12: "sh_r", 13: "el_l", 14: "el_r", 15: "wr_l", 16: "wr_r",
             17: "pinky_l", 18: "pinky_r", 19: "index_l", 20: "index_r", 21: "thumb_l", 22: "thumb_r"}


def ensure_models() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_URLS.items():
        p = MODELS / name
        if not p.exists():
            urllib.request.urlretrieve(url, p)


def _delegate():
    from mediapipe.tasks.python import BaseOptions

    want = os.environ.get("PF_DELEGATE", "GPU" if platform.system() == "Darwin" else "CPU").upper()
    return BaseOptions.Delegate.GPU if want == "GPU" else BaseOptions.Delegate.CPU


def probe_wh(path: str) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout
    w, h = out.strip().split(",")[:2]
    return int(w), int(h)


def frames(path: str, height: int, fps: float, start: float = 0.0, secs: float | None = None):
    """Yield (t_ms, HxWx4 uint8 RGBA) on a fixed fps grid. Constant memory."""
    w0, h0 = probe_wh(path)
    h = min(height, h0 - h0 % 2)
    w = int(round(w0 * h / h0 / 2) * 2)
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-ss", str(start), "-i", path, *(["-t", str(secs)] if secs else []),
           "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgba", "-"]
    n = w * h * 4
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=n)
    i = 0
    try:
        while len(buf := p.stdout.read(n)) == n:
            yield int(round((start + i / fps) * 1000)), np.frombuffer(buf, np.uint8).reshape(h, w, 4)
            i += 1
    finally:
        p.kill()
        p.wait()


def head_pose(T) -> tuple[float, ...]:
    T = np.asarray(T)
    R = T[:3, :3]
    yaw = np.degrees(np.arctan2(-R[2, 0], np.hypot(R[0, 0], R[1, 0])))
    pitch = np.degrees(np.arctan2(R[2, 1], R[2, 2]))
    roll = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
    return yaw, pitch, roll, T[0, 3], T[1, 3], T[2, 3]


ARC_TEMPLATE = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                         [41.5493, 92.3655], [70.7299, 92.2041]], np.float32)


def aligned_crop_jpeg(img_rgba: np.ndarray, kp_norm: np.ndarray) -> bytes | None:
    """112x112 5-point-aligned face crop (ArcFace template), JPEG-encoded. Identity runs off-cluster."""
    import cv2

    h, w = img_rgba.shape[:2]
    src = (kp_norm * np.array([w, h], np.float32)).astype(np.float32)
    M, _ = cv2.estimateAffinePartial2D(src, ARC_TEMPLATE, method=cv2.LMEDS)
    if M is None:
        return None
    crop = cv2.warpAffine(np.ascontiguousarray(img_rgba[:, :, :3]), M, (112, 112), borderValue=0)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes() if ok else None


def run_face(video: str, fps: float, height: int, start: float, secs: float | None,
             crop_every: int = 8) -> tuple[pd.DataFrame, dict]:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    opts = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODELS / "face_landmarker.task"), delegate=_delegate()),
        running_mode=vision.RunningMode.VIDEO, num_faces=3,
        min_face_detection_confidence=0.5, min_face_presence_confidence=0.5, min_tracking_confidence=0.5,
        output_face_blendshapes=True, output_facial_transformation_matrixes=True)
    rows, ms = [], []
    fl = vision.FaceLandmarker.create_from_options(opts)
    for n, (t, a) in enumerate(frames(video, height, fps, start, secs)):
        if n and n % RECYCLE == 0:
            fl.close()
            fl = vision.FaceLandmarker.create_from_options(opts)
        img = mp.Image(image_format=mp.ImageFormat.SRGBA, data=np.ascontiguousarray(a))
        s = time.perf_counter()
        r = fl.detect_for_video(img, t)
        ms.append(time.perf_counter() - s)
        nf = len(r.face_landmarks)
        for k, lm in enumerate(r.face_landmarks):
            xy = np.array([(p.x, p.y) for p in lm], np.float32)
            x0, y0 = xy.min(0)
            x1, y1 = xy.max(0)
            yaw, pitch, roll, tx, ty, tz = head_pose(r.facial_transformation_matrixes[k])
            row = {"t_ms": t, "face_idx": k, "n_faces": nf, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                   "cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "fw": x1 - x0, "fh": y1 - y0,
                   "yaw": yaw, "pitch": pitch, "roll": roll, "tx": tx, "ty": ty, "tz": tz}
            kp = np.array([xy[list(ids)].mean(0) for ids in KP5], np.float32)
            for j in range(5):
                row[f"kp{j}x"], row[f"kp{j}y"] = kp[j]
            row["crop_jpg"] = aligned_crop_jpeg(a, kp) if crop_every and n % crop_every == 0 else None
            # iris centers relative to eye corners -> horizontal gaze ratio (468/473 are iris centers)
            if len(xy) > 473:
                for side, (iris, a_, b_) in {"l": (468, 33, 133), "r": (473, 362, 263)}.items():
                    span = xy[b_, 0] - xy[a_, 0]
                    row[f"gaze_{side}"] = float((xy[iris, 0] - xy[a_, 0]) / span) if abs(span) > 1e-6 else np.nan
            row.update({c.category_name: c.score for c in r.face_blendshapes[k]})
            rows.append(row)
    fl.close()
    df = pd.DataFrame(rows)
    for c in df.select_dtypes("float64").columns:
        df[c] = df[c].astype("float32")
    return df, {"face_ms_median": 1000 * float(np.median(ms)) if ms else np.nan, "n_frames": len(ms)}


def run_pose(video: str, fps: float, height: int, start: float, secs: float | None) -> tuple[pd.DataFrame, dict]:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    opts = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODELS / "pose_landmarker_lite.task"), delegate=_delegate()),
        running_mode=vision.RunningMode.VIDEO, num_poses=3, output_segmentation_masks=False)
    rows, ms = [], []
    pl = vision.PoseLandmarker.create_from_options(opts)
    for n, (t, a) in enumerate(frames(video, height, fps, start, secs)):
        if n and n % RECYCLE == 0:
            pl.close()
            pl = vision.PoseLandmarker.create_from_options(opts)
        img = mp.Image(image_format=mp.ImageFormat.SRGBA, data=np.ascontiguousarray(a))
        s = time.perf_counter()
        r = pl.detect_for_video(img, t)
        ms.append(time.perf_counter() - s)
        for k, P in enumerate(r.pose_landmarks):
            row = {"t_ms": t, "pose_idx": k, "n_poses": len(r.pose_landmarks)}
            for i, nm in POSE_KEEP.items():
                row[f"{nm}_x"], row[f"{nm}_y"], row[f"{nm}_v"] = P[i].x, P[i].y, P[i].visibility
            rows.append(row)
    pl.close()
    df = pd.DataFrame(rows)
    for c in df.select_dtypes("float64").columns:
        df[c] = df[c].astype("float32")
    return df, {"pose_ms_median": 1000 * float(np.median(ms)) if ms else np.nan}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--fps", type=float, default=4.0)
    ap.add_argument("--height", type=int, default=360)
    ap.add_argument("--start", type=float, default=15.0)
    ap.add_argument("--secs", type=float, default=1200.0)
    ap.add_argument("--pose-fps", type=float, default=2.0)
    a = ap.parse_args()
    ensure_models()
    t0 = time.perf_counter()
    face, s1 = run_face(a.video, a.fps, a.height, a.start, a.secs)
    face.to_parquet(a.out + ".face.parquet")
    pose, s2 = run_pose(a.video, a.pose_fps, a.height, a.start, a.secs)
    pose.to_parquet(a.out + ".pose.parquet")
    stats = {**s1, **s2, "wall_s": round(time.perf_counter() - t0, 1), "fps": a.fps, "height": a.height,
             "host": platform.node(), "delegate": os.environ.get("PF_DELEGATE", "auto")}
    Path(a.out + ".vision.json").write_text(json.dumps(stats))
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
