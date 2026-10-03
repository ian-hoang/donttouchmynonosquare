# Feature-extraction stack: tested on this machine

Tested 2026-10-02, about 23:15 to 23:40 ET, on an Apple M4 with 16 GB, macOS (Darwin 27), using `.venv` (py3.12).
Versions: mediapipe 1.0.1, onnxruntime 1.30.0, opensmile 2.6.0, praat-parselmouth 0.4.7, mlx-whisper 0.4.3 (mlx 0.32.3), yt-dlp 2026.8.19, elevenlabs 2.70.0.
I ran one Python process at a time and loaded at most one model at a time.

**Reference script (tested; every subcommand ran unless marked otherwise):** `/Users/ojasvamishra32/pokerface/.scratch/feature-stack/reference_extract.py`
Subcommands: `vision`, `identity`, `cues`, `audio`, `whisper`, `captions` (it hit HTTP 429, see section 5) and `scribe` (only the call shape was checked; there is no key yet).

**Test clip:** "Interview on extreme weather with physical geographer Hannah Cloke – The Royal Society" (Wikimedia Commons; 626 s, 854x480 VP9 + Opus, 57 MB, already in scratch).
https://commons.wikimedia.org/wiki/File:Interview_on_extreme_weather_with_physical_geographer_Hannah_Cloke_%E2%80%93_The_Royal_Society.webm
The clip alternates shot and reverse shot between the interviewer (Roma Agrawal, yellow top) and the interviewee (Hannah Cloke, white T-shirt), with some wide two-shots. That makes it a good identity test. The shirt colours gave an automatic ground truth: 1418 interviewee faces and 624 interviewer faces.

---

## 0. Most important finding: MediaPipe 1.0.1 leaks memory (probable cause of the crash)

- `FaceLandmarker` with the GPU delegate grows by about **1.9 MB per frame** and never frees it. This happens in both VIDEO and IMAGE mode.
  - Measured RSS after 150, 300, 450 and 600 frames: **559, 850, 1140, 1431 MB**.
  - A face pass over 960 frames peaked at 1.95 GB. A pose pass over 960 frames peaked at 2.27 GB, so PoseLandmarker leaks too.
  - A 30-min video at 4 fps is 7200 frames, or about 14 GB per process. Several parallel workers would take down a 16 GB Mac.
- **Fix (tested):** call `close()` and recreate the landmarker every 150 frames. RSS then stays flat at **277 MB** (276, 277, 277, 277).
  - With the fix, the full 626 s clip (2504 frames, face pass then pose pass) peaked at **701 MB**.
  - The reference script does this through `PF_RECYCLE=150`.
  - Side effect: the VIDEO-mode tracker resets every 37.5 s, which is harmless.
- Earlier runs left `p1..p4.parquet` and `v1.parquet` with identical md5. This suggests the previous attempt ran four parallel copies, and it also shows that GPU-delegate output is deterministic run to run.

## 1. MediaPipe 1.0.1 Tasks API (verified code, model URLs, timings)

**Differences between 1.0.1 and 0.10.x (verified here):**
- `import mediapipe as mp; dir(mp)` returns `['Image','ImageFormat','tasks']`. The legacy **`mp.solutions` (FaceMesh, Pose, Holistic) is gone**, so use the Tasks API only.
- **`Delegate.CPU` aborts the whole process** when the model is created, with `graph_service.h:139 Check failed: service_ Service is unavailable.`
- `Delegate.GPU` works only with **`ImageFormat.SRGBA`**. SRGB input aborts with `gpu_buffer_storage_cv_pixel_buffer.cc:154 ... unsupported ImageFrame format: 1`.
  - Decode with `ffmpeg -pix_fmt rgba`.
  - The log still says "Created TensorFlow Lite XNNPACK delegate for CPU", so part of the graph runs on the CPU.
- The option names are unchanged: `output_facial_transformation_matrixes` keeps its spelling, and `num_faces`, `num_poses` and `output_segmentation_masks` are the same. Landmarkers still work as context managers.
- The face landmarker returns **52 blendshape categories** (51 plus `_neutral`) and 478 landmarks.

```python
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision
fl_opts = vision.FaceLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="models/face_landmarker.task", delegate=BaseOptions.Delegate.GPU),
    running_mode=vision.RunningMode.VIDEO, num_faces=3,
    min_face_detection_confidence=0.5, min_face_presence_confidence=0.5, min_tracking_confidence=0.5,
    output_face_blendshapes=True, output_facial_transformation_matrixes=True)
pl_opts = vision.PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path="models/pose_landmarker_lite.task", delegate=BaseOptions.Delegate.GPU),
    running_mode=vision.RunningMode.VIDEO, num_poses=3, output_segmentation_masks=False)
fl = vision.FaceLandmarker.create_from_options(fl_opts)
for n, (t_ms, rgba) in enumerate(frames):              # rgba: HxWx4 uint8 from ffmpeg -pix_fmt rgba
    if n and n % 150 == 0: fl.close(); fl = vision.FaceLandmarker.create_from_options(fl_opts)   # LEAK FIX
    r = fl.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGBA, data=rgba), t_ms)  # t_ms strictly increasing
    # r.face_landmarks[k] (478 NormalizedLandmark), r.face_blendshapes[k] (52 Category: .category_name/.score),
    # r.facial_transformation_matrixes[k] (4x4 np array)
```

**Model URLs.** Each was checked on 2026-10-02 for HTTP 200, with the `x-goog-hash` md5 matching the local file:

| model | URL | bytes |
|---|---|---|
| face_landmarker.task | https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task | 3,758,596 |
| pose_landmarker_lite.task | https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task | 5,777,746 |
| pose_landmarker_full.task | https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task | 9,398,198 |
| blaze_face_short_range.tflite | https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite | 229,746 |

The local copy of pose_full matches the `/1/` URL. The `/latest/` URL returns a different md5 at the same size. Pin URLs by version (`/1/`), not by `latest`.

**Measured inference time per frame** (median; 120 s of the clip at 4 fps = 480 frames; ffmpeg does fps sampling and scaling):

| height | face (3 faces max) | face p90 | pose lite | pose p90 | decode | peak RSS (no recycle) |
|---|---|---|---|---|---|---|
| 360p (640x360) | **4.72 ms** | 5.09 | **8.21 ms** | 9.53 | 0.18 ms | 1.24 GB (leak) |
| 480p (854x480) | 4.92 ms | 7.46 | 8.55 ms | 12.07 | 0.30 ms | 1.99 GB (leak) |

- Full clip at **360p, 4 fps**, with face and pose passes and recycling on: 2504 frames in **48.7 s wall** (face 18.9 s, pose 29.0 s), peak **701 MB**. That is 12.9x real time, and the process used about 0.8 CPU core (39.5 s user).
- At 360p, MediaPipe found **no faces in the wide two-shots** (interviewee faces were about 4% of frame width). Every detected face was a close-up, with face width at 12 to 15% of frame width. This is desirable for us, but it means wide-shot-only videos give no face data, so a QC column for this is needed.
- **Recommendation:** use 360p. Going to 480p costs more memory and adds nothing at close-up face sizes.

## 2. Blendshapes and pose mapped to interpretable cues

These are implemented in `cues_from_frames()` and were run on the interviewee's 1424 frames. Blendshape ranges below are p50 / p95 / p99 on the interviewee frames.

| cue | definition (as coded) | FACS proxy | range check |
|---|---|---|---|
| blink rate | b = mean(eyeBlinkL,R). Threshold = max(0.35, p50 + 0.5·(p99 − p50)), which came out at 0.38. Count onsets per minute of target time. Also report `eye_closed_frac`. | AU45 | b p50 0.07 / p95 0.53 / p99 0.70; works |
| lip press | mean(mouthPressL,R) | AU24 | 0.06 / 0.22 / 0.43; usable |
| lip roll / suck | mouthRollLower (also mouthRollUpper) | AU28 | 0.008 / 0.07 / 0.17; weak |
| chin raise | mouthShrugLower | AU17 | 0.001 / 0.024 / 0.081; **very weak, low trust** |
| inner brow raise | browInnerUp | AU1 | 0.08 / 0.68 / 0.79; good range |
| brow lower | mean(browDownL,R) | AU4 | 0.09 / 0.66 / 0.81; good range |
| smile | mean(mouthSmileL,R) > 0.3 | AU12 | 0.01 / 0.83 / 0.92; good range |
| **Duchenne smile** | **cheekSquintL/R are DEAD (p99 = 0.000 over 1418 frames)**. Use the share of smile frames where eyeSquint exceeds the person's own non-smile eyeSquint median by more than 0.1. Also report the median lift. | AU6+AU12 | eyeSquint p50 0.36 (high resting level, so it must be measured relative to that) |
| smile asymmetry | \|L−R\|/(L+R) on frames with smile > 0.2. Also \|mouthDimpleL−R\| | AU12/AU14 unilateral | 0.14 on the clip |
| head pose | yaw/pitch/roll from R = T[:3,:3]: yaw = atan2(−R20, hypot(R00,R10)), pitch = atan2(R21,R22), roll = atan2(R10,R00). Translation is T[:3,3] in canonical-face cm. | n/a | yaw −6.9±7.0°, pitch 4.2±4.0° |
| head motion energy | Sum of \|Δyaw\|+\|Δpitch\|+\|Δroll\| × fps (deg/s), counted only between consecutive frames of the same run. Steps over 200 deg/s are dropped as cuts. Report the median and p90. | n/a | 21 deg/s median, 52 p90 |
| hand-to-face (self-touch) | Pose is matched to the face whose nose lies within one face width of the face centre. Touch = any of wrist, index, thumb or pinky landmarks (15 to 22) with visibility > 0.5 inside the face box padded by 0.2 face widths. | adaptor | 0.0 on the clip (no touches seen) |
| gesture (illustrator) energy | Wrist speed in shoulder widths per second, using consecutive frames where visibility > 0.5. Report the median and p90, plus `hands_visible_frac` as QC. | illustrator | 0.25 / 0.73 sw/s; hands visible 99.9% |

**Dead or near-dead blendshapes in mp 1.0.1:** cheekSquintL/R and noseSneerL/R (p99 0.000), mouthFrownL (p99 0.005), and mouthShrugLower (p99 0.08). **Do not pre-specify cues on these** in the literature-weighted tell score. Keep `cheekSquint_p99_QC` as a sanity column.

**Blink sampling rate matters (tested).** On a continuous 37 s interviewee shot, the face pass ran at 12 fps and was then subsampled:

| sampling | blinks per min |
|---|---|
| 12 fps | **24.3** |
| 6 fps | 16.2 |
| 4 fps | 14.6 |

- At 4 fps, about 40% of blinks are missed. At 12 fps, most closures last only 1 or 2 frames (83 to 167 ms).
- **Recommendation:** run the **face pass at 12 fps** and the **pose pass at 4 fps**. The face pass costs about 5 ms per frame, so this is cheap. Either way, normalise against each CEO's own baseline at a fixed fps.

## 3. Face identity: keeping features on the CEO

These results came from `identity` on the full clip (2048 faces, 35 IoU-linked tracks, ArcFace on every other sampled frame, crops at 480p):

| heuristic | precision (interviewee) | recall |
|---|---|---|
| A: largest face per frame | 0.694 (no better than base rate) | 1.0 |
| **B: largest × most persistent track ("main character")** | **0.000** (picked the interviewer's long intro shot) | 0.0 |
| **D: ArcFace track clustering (greedy, cosine ≥ 0.4), keep the cluster with the most screen time** | **1.000** | **1.000** (2 clusters found) |

- **The "largest + most persistent face" heuristic is NOT adequate.**
  - With shot and reverse shot, every frame shows one face, so "largest" chooses whoever is on screen.
  - The interviewer's faces were actually *larger* on average (face width 0.144 vs 0.132).
  - The longest single track belonged to the interviewer.
- **The identity embedding needs no new pip installs.** `onnxruntime` (already installed) can run InsightFace's **`w600k_mbf.onnx`** (MobileFaceNet ArcFace, 13.6 MB). It comes from the official release `https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_sc.zip` (15.0 MB zip; extracted to `.scratch/feature-stack/models/buffalo_sc/`).
  - Alignment: 5 points from the MediaPipe mesh (eye corners 33/133 and 362/263, nose 1, mouth corners 61/291) feed `cv2.estimateAffinePartial2D` against the standard ArcFace 112x112 template.
  - Input is RGB scaled to [−1, 1] in NCHW.
  - Speed: **2.9 ms per face**. Peak memory for the identity pass: **165 MB**. The whole pass took 9.5 s for the 10-minute clip.
  - Separation: interviewee faces vs an interviewer reference gave cosine p10/p50/p90 of −0.004 / 0.033 / 0.068. Interviewer vs interviewer gave 0.73 / 0.81 / 0.90. There is no overlap.
  - Licence caveat (UNVERIFIED today): InsightFace's pretrained models are released for non-commercial research use. A hackathon research project fits, but this should be stated in the note.
- The `insightface` pip package is **not needed** and is not installed.
- **Recommended approach (simplest robust):**
  1. Link face tracks by IoU.
  2. Take the mean ArcFace embedding per track.
  3. Cluster greedily at cosine ≥ 0.4.
  4. Build a **per-CEO reference embedding** from the top-screen-time cluster of that CEO's first 3 or more videos. Require pairwise agreement of cosine ≥ 0.5, plus one manual thumbnail check per CEO.
  5. In every video, keep only clusters with cosine ≥ 0.4 to the CEO reference.
  6. Drop the video if no cluster matches (QC column `ceo_face_frac`).
  This avoids anchors who dominate screen time in TV hits.

## 4. Audio (30 s interviewee segment, 16 kHz mono)

The `audio` subcommand ran on the clip from 367 s to 397 s.

**openSMILE eGeMAPSv02 Functionals:**
- 88 features in **0.62 s**, including init, which is about 48x real time.
- F0: 32.9 semitones relative to 27.5 Hz, which is about 184 Hz.
- Jitter (local) 0.016; shimmer 0.96 dB; HNR (ACF) 8.6 dB; voiced segments 2.7 per second; loudness peaks 4.6 per second.

**Praat (parselmouth):**
- Took **0.09 s**.
- F0 median 179 Hz, which agrees with openSMILE; F0 SD 2.27 semitones.
- Jitter (local) 0.020, shimmer (local) 0.079, HNR (cc) 15.9 dB.

**Memory and cautions:**
- Peak RSS **195 MB**.
- The two HNR algorithms differ (8.6 vs 15.9 dB), so **never mix the openSMILE and Praat versions** of a feature across videos. Pick one per feature, and pre-specify it.
- Compute these per CEO answer segment, using the diarised word times, rather than over the whole file.

## 5. Transcription

**YouTube auto-captions via yt-dlp json3:**
- **Not tested today.** `--skip-download --write-auto-subs --sub-format json3` got **HTTP 429 Too Many Requests** on the subtitle URL. YouTube is rate-limiting this IP, probably because of the earlier corpus search.
- From prior knowledge (UNVERIFIED today): json3 ASR tracks carry `events[].tStartMs`, plus `segs[].tOffsetMs` per word. So you get word **start** times but no end times, no speaker labels and no fillers.
- If you use captions: throttle with `--sleep-subtitles 5` (UNVERIFIED), make one request at a time, and cache aggressively.

**mlx-whisper (one model loaded):**
- **Model:** `mlx-community/whisper-base.en-mlx`, 143.7 MB of weights.
- **Speed and memory on 30 s of audio:** wall time on a warm run was 1.36 s including model load, which is **22x real time**. The first run took 11.8 s, including the download. Peak RSS **1.1 GB**.
- **Output:** word timestamps are on, and it produced 87 words with clean start and end times. The first word's start is stretched (0.00 to 0.92 s), which is a typical Whisper artifact.
- **Why not other sizes:** `whisper-small.en-mlx` is 481 MB and `whisper-large-v3-turbo` is 1.61 GB (sizes from the HF API). Both exceed today's 300 MB download cap, and their memory and speed are UNVERIFIED.
- **Gaps:** Whisper tends to drop "um"/"uh" (known behaviour, not measured here) and has no diarisation.

**ElevenLabs Scribe:**
- Call shape verified against the installed `elevenlabs==2.70.0`:
  ```python
  client.speech_to_text.convert(file=fh, model_id="scribe_v2", language_code="en", diarize=True,
      num_speakers=None, timestamps_granularity="word", tag_audio_events=True, no_verbatim=False)
  ```
  - `timestamps_granularity` accepts `'word'` or `'character'`.
  - `no_verbatim=False` keeps filler words. It is "only supported with scribe_v2", which matters for hedge and disfluency cues.
  - `r.words[i]` has `text`, `start`, `end`, `type ∈ {word, spacing, audio_event}`, `speaker_id`, `logprob`.
  - Other relevant parameters: `diarization_threshold`, `keyterms` (list of CEO and company names), `detect_speaker_roles`, `seed`.
- It has not been run, because there is no key yet.
- **Recommendation:** use Scribe, which gives diarisation, fillers and word times and qualifies for the ElevenLabs prize. Fall back to mlx-whisper base.en.
- To map Scribe speakers to the CEO, take the speaker whose talk time overlaps most with frames where the CEO cluster is on screen and the face shows `jawOpen` variance. This is UNVERIFIED and still needs building.

## 6. Per-video budget and safe parallelism (16 GB)

Rates measured here, for one worker on a 30-min (1800 s) video:

| stage | rate measured | 30-min video | peak RSS |
|---|---|---|---|
| face pass, 360p, **12 fps** (21,600 frames) | 7.5 ms per frame all-in | ~160 s | ~0.3 to 0.4 GB (recycled) |
| pose lite, 360p, 4 fps (7,200 frames) | 11.6 ms per frame all-in | ~85 s | ~0.4 GB (recycled) |
| identity (ArcFace every 2nd 4-fps frame, 480p decode) | 9.5 s per 626 s | ~27 s | 0.17 GB |
| audio (eGeMAPS + Praat) | ~0.7 s per 30 s | ~45 s | 0.2 GB |
| mlx-whisper base.en | 22x RT | ~80 s | 1.1 GB |
| **total** | | **~6.5 min** (~4.5 min if face runs at 4 fps) | max 1.1 GB (one stage at a time) |

Not counted: the video download, and ffmpeg child-process memory (`/usr/bin/time` reports the Python process only).

**What this means for the corpus:** 300 videos averaging 25 minutes take about **27 hours with one worker**. That is too slow for the deadline, so cut the scope:
- Cap each video at its **first 15 minutes**.
- Download at 360p only.
- Run the face pass at 12 fps only on segments where the CEO is speaking.

**Safe parallelism.** Measured per-worker memory: vision 0.7 GB (with recycle), whisper 1.1 GB.
- **At most 3 vision workers**, about 2.1 GB in total.
- **Plus 1 transcription worker** (Scribe API calls need almost no RAM; mlx-whisper needs 1.1 GB).
- **Never more than one mlx or whisper model in memory.**
- Set `PF_RECYCLE=150` (or lower) and keep it on always.
- Set `OMP_NUM_THREADS=2` for onnxruntime workers. ArcFace used about 5.6 CPU cores (53 s user over 9.5 s real).
- Downloads should run one at a time.

UNVERIFIED: GPU (Metal) contention between 3 MediaPipe processes. The throughput gain from 3 workers was **not measured**, because the safety rule allows one process at a time. Expect at most about 2.5x.

**Downloads this session:** buffalo_sc.zip (15.0 MB) and whisper-base.en (143.7 MB), about 159 MB. The previous attempt added about 76 MB (the clip plus the MediaPipe models). Total is about 235 MB, under the 300 MB cap.
