"""Build the curated corpus: data/manifest/videos.csv (committed).

Inputs (all committed or reproducible):
  data/manifest/candidates_for_curation.csv   rule-prefiltered YouTube search hits
  data/manifest/curation_labels.csv           agentic curation verdicts (metadata only, never returns)
  data/cache/meta/<id>.json                   exact upload timestamps (pipeline/fetch_metadata.py)
  config/universe.csv                         CEO tenure and listing windows

Rules (pre-registered in docs/RULEBOOK.md):
  keep == True and content_type is an unscripted Q&A setting
  publish date inside the CEO's tenure, after the stock listed, and inside [2016-01-01, 2026-09-30]
  duplicates: same CEO, |duration diff| <= 3 s and same publish day -> keep the earliest upload
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
QA_TYPES = {"tv_interview", "podcast_interview", "fireside_or_conference_qa", "panel", "earnings_call"}
SAMPLE_START, SAMPLE_END = "2016-01-01", "2026-09-30"


def load_meta(ids) -> pd.DataFrame:
    rows = []
    for v in ids:
        p = ROOT / "data" / "cache" / "meta" / f"{v}.json"
        if not p.exists():
            continue
        j = json.loads(p.read_text())
        if j.get("error") or not j.get("timestamp"):
            continue
        rows.append({"video_id": v, "publish_ts_utc": pd.Timestamp(int(j["timestamp"]), unit="s", tz="UTC"),
                     "channel_meta": j.get("channel"), "channel_id_meta": j.get("channel_id"),
                     "duration_meta": j.get("duration"), "has_auto_en": j.get("has_auto_en"),
                     "has_subs_en": j.get("has_subs_en"), "live_status": j.get("live_status")})
    return pd.DataFrame(rows)


def build() -> pd.DataFrame:
    cand = pd.read_csv(ROOT / "data" / "manifest" / "candidates_for_curation.csv", dtype={"video_id": str})
    lab = pd.read_csv(ROOT / "data" / "manifest" / "curation_labels.csv", dtype={"video_id": str})
    uni = pd.read_csv(ROOT / "config" / "universe.csv", dtype=str)
    df = cand.merge(lab, on="video_id", how="inner")
    df = df[df["keep"].astype(str).str.lower().eq("true") & df["content_type"].isin(QA_TYPES)
            & ~df["wrong_tenure_or_role"].astype(str).str.lower().eq("true")]
    meta = load_meta(df["video_id"])
    df = df.merge(meta, on="video_id", how="inner")
    df = df.merge(uni[["ceo_id", "tenure_start", "tenure_end", "listed_start"]], on="ceo_id", how="left")
    d = df["publish_ts_utc"].dt.tz_convert(None)
    lo = pd.concat([pd.to_datetime(df["tenure_start"]), pd.to_datetime(df["listed_start"]),
                    pd.Series(pd.Timestamp(SAMPLE_START), index=df.index)], axis=1).max(axis=1)
    hi = pd.to_datetime(df["tenure_end"]).fillna(pd.Timestamp(SAMPLE_END)).clip(upper=pd.Timestamp(SAMPLE_END))
    df = df[(d >= lo) & (d <= hi + pd.Timedelta(days=1))]
    # duplicate uploads of the same interview: same CEO, same day, near-identical duration
    df = df.sort_values("publish_ts_utc")
    df["_day"] = df["publish_ts_utc"].dt.date
    df["_dur"] = (df["duration_meta"].fillna(df["duration_s"]) / 3).round()
    df = df.drop_duplicates(["ceo_id", "_day", "_dur"], keep="first")
    cols = ["video_id", "ceo_id", "ceo", "ticker", "title", "channel", "content_type", "publish_ts_utc",
            "duration_s", "view_count", "has_auto_en", "confidence"]
    out = df[cols].sort_values(["ceo_id", "publish_ts_utc"]).reset_index(drop=True)
    out.to_csv(ROOT / "data" / "manifest" / "videos.csv", index=False)
    return out


if __name__ == "__main__":
    v = build()
    print(len(v), "videos")
    print(v.groupby("ceo_id").agg(n=("video_id", "size"), first=("publish_ts_utc", "min"),
                                  last=("publish_ts_utc", "max")).to_string())
