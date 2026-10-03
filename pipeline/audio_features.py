"""Vocal features from the CEO's own speech segments.

- eGeMAPSv02 functionals via openSMILE (Eyben et al. 2016, IEEE Trans. Affective Computing): the
  standard minimal acoustic parameter set for affect. We keep the parameters with documented links to
  stress/arousal/deception: F0 level and variability (pitch rises under deception, DePaulo et al. 2003
  d=0.21; vocal tension d=0.26), jitter, shimmer, HNR (voice quality under strain), loudness, rate of
  voiced segments (speech tempo).
- Timing from word timestamps: pause rate and length inside CEO turns; response latency (gap between
  the interviewer's last word and the CEO's first word when the turn changes; needs diarization).
"""
from __future__ import annotations

import numpy as np

KEEP = {
    "F0semitoneFrom27.5Hz_sma3nz_amean": "voc_f0_mean_st",
    "F0semitoneFrom27.5Hz_sma3nz_stddevNorm": "voc_f0_cv",
    "F0semitoneFrom27.5Hz_sma3nz_percentile80.0": "voc_f0_p80_st",
    "jitterLocal_sma3nz_amean": "voc_jitter",
    "shimmerLocaldB_sma3nz_amean": "voc_shimmer_db",
    "HNRdBACF_sma3nz_amean": "voc_hnr_db",
    "loudness_sma3_amean": "voc_loudness",
    "loudness_sma3_stddevNorm": "voc_loudness_cv",
    "VoicedSegmentsPerSec": "voc_voiced_seg_per_s",
    "MeanVoicedSegmentLengthSec": "voc_voiced_seg_len",
    "MeanUnvoicedSegmentLength": "voc_unvoiced_seg_len",
    "alphaRatioV_sma3nz_amean": "voc_alpha_ratio",
    "hammarbergIndexV_sma3nz_amean": "voc_hammarberg",
}
_SMILE = None


def _smile():
    global _SMILE
    if _SMILE is None:
        import opensmile

        _SMILE = opensmile.Smile(feature_set=opensmile.FeatureSet.eGeMAPSv02,
                                 feature_level=opensmile.FeatureLevel.Functionals)
    return _SMILE


def concat_segments(signal: np.ndarray, sr: int, segments: list[tuple[float, float]],
                    max_seconds: float = 900.0) -> np.ndarray:
    """Concatenate CEO speech segments (seconds) into one signal, capped at `max_seconds`."""
    parts, total = [], 0.0
    for a, b in segments:
        if b - a < 0.3:
            continue
        seg = signal[int(a * sr):int(b * sr)]
        parts.append(seg)
        total += len(seg) / sr
        if total >= max_seconds:
            break
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def acoustic_features(signal: np.ndarray, sr: int, segments: list[tuple[float, float]]) -> dict:
    x = concat_segments(signal, sr, segments)
    out = {"voc_seconds": float(len(x) / sr) if sr else 0.0}
    if len(x) < sr * 30:                      # need >= 30 s of CEO speech
        out.update({v: np.nan for v in KEEP.values()})
        return out
    df = _smile().process_signal(x.astype(np.float32), sr)
    row = df.iloc[0]
    for k, v in KEEP.items():
        out[v] = float(row[k]) if k in row.index else np.nan
    return out


def timing_features(words: list[dict], ceo_speaker: str | None) -> dict:
    """words: [{text, start, end, speaker}] in time order (speaker may be None without diarization)."""
    out = {"voc_pause_per_min": np.nan, "voc_pause_mean_s": np.nan, "voc_response_latency_s": np.nan,
           "voc_n_turns": np.nan}
    if not words:
        return out
    ceo = [w for w in words if ceo_speaker is None or w.get("speaker") == ceo_speaker]
    if len(ceo) < 100:
        return out
    gaps, speech = [], 0.0
    for a, b in zip(ceo[:-1], ceo[1:]):
        g = b["start"] - a["end"]
        if 0.25 <= g <= 3.0:                    # within-turn pauses only
            gaps.append(g)
        if g < 3.0:
            speech += b["end"] - a["start"] if g < 0 else (b["end"] - b["start"]) + max(g, 0)
    minutes = max(speech / 60.0, 1e-6)
    out["voc_pause_per_min"] = len(gaps) / minutes
    out["voc_pause_mean_s"] = float(np.mean(gaps)) if gaps else 0.0
    if ceo_speaker is not None:
        lat, turns = [], 0
        for a, b in zip(words[:-1], words[1:]):
            if a.get("speaker") != ceo_speaker and b.get("speaker") == ceo_speaker:
                turns += 1
                g = b["start"] - a["end"]
                if -0.5 <= g <= 5.0:
                    lat.append(max(g, 0.0))
        out["voc_n_turns"] = float(turns)
        out["voc_response_latency_s"] = float(np.median(lat)) if len(lat) >= 3 else np.nan
    return out
