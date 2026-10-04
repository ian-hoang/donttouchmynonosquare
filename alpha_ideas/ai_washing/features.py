"""Step 3 — AI-term counts for every downloaded press release (see PREREGISTRATION.md, "Signal").

Run from the repo root:  uv run python alpha_ideas/ai_washing/features.py
Writes data/cache/ai_washing/ai_features.parquet and prints an audit of what the token matches look like, so false
positives (an "AI" that isn't artificial intelligence) can be spotted. Uses no returns.
"""
from __future__ import annotations

import gzip
import html
import random
import re
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from common import CACHE

SEC = CACHE / "sec"
EX99 = SEC / "ex99"

# Case-insensitive phrases
PHRASES = {
    "artificial intelligence": r"artificial\s+intelligence",
    "machine learning": r"machine\s+learning",
    "deep learning": r"deep\s+learning",
    "neural network": r"neural\s+networks?",
    "large language model": r"large\s+language\s+models?",
    "chatgpt": r"chatgpt",
    "agentic": r"agentic",
}
# Case-sensitive whole tokens: not touching a letter or digit on either side
# Bug fix (signal-only audit, before any return was computed): "GPT" was dropped. Oil & gas releases use it for
# "gathering, processing and transportation" (Chord Energy: ~15 per release); real AI uses ("GPT-4") come with other terms.
TOKENS = {"AI": r"AI", "A.I.": r"A\.I\.", "GenAI": r"GenAI", "OpenAI": r"OpenAI", "LLM": r"LLMs?"}
RE_PHRASE = {k: re.compile(v, re.IGNORECASE) for k, v in PHRASES.items()}
RE_TOKEN = {k: re.compile(r"(?<![A-Za-z0-9])" + v + r"(?![A-Za-z0-9])") for k, v in TOKENS.items()}
RE_WORD = re.compile(r"[A-Za-z]+")
# Bug fix (same audit): a release that defines "AI" as something other than artificial intelligence (Tyson: avian
# influenza; Advance Auto Parts: Autopart International; oncology: aromatase inhibitor) gets its bare AI tokens zeroed.
RE_AI_DEF = re.compile(r"([A-Za-z][A-Za-z\-]+(?:\s+[A-Za-z\-]+){0,3})\s*\(\s*[\"“”']?(?:AI|A\.I\.)[\"“”']?\s*\)")
RE_AI_EQ_OTHER = re.compile(r"(?<![A-Za-z0-9])AI\s*=\s*aromatase", re.IGNORECASE)
RE_STOP = re.compile(r"\b(the|and|of|to|in|for|a|on|with|our|is|we|as|by|was|from)\b", re.IGNORECASE)


def html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", " ", s)
    s = re.sub(r"(?s)<[^>]*>", " ", s)
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def ai_redefined(text: str) -> bool:
    if RE_AI_EQ_OTHER.search(text):
        return True
    return any("intelligence" not in m.group(1).lower() for m in RE_AI_DEF.finditer(text))


def count(text: str) -> dict:
    out = {f"n_{k}": len(r.findall(text)) for k, r in {**RE_PHRASE, **RE_TOKEN}.items()}
    redefined = ai_redefined(text)
    if redefined:
        out["n_AI"] = 0
    out["ai_full"] = sum(out.values())
    out["ai_redefined"] = redefined
    out["ai_strict"] = out["n_artificial intelligence"] + out["n_AI"]
    out["n_words"] = len(RE_WORD.findall(text))
    # Text-quality measures: real English press releases are ~25-35% stop words; encoded junk (e.g. a uuencoded
    # exhibit) has almost none and many ;@>= symbols.
    out["stop_share"] = len(RE_STOP.findall(text)) / max(out["n_words"], 1)
    out["sym_share"] = sum(text.count(c) for c in ";@>=<^`") / max(len(text), 1)
    return out


def one(acc: str) -> dict:
    with gzip.open(EX99 / f"{acc}.txt.gz", "rt", encoding="utf-8") as fh:
        text = html_to_text(fh.read())
    return {"acc": acc, **count(text)}


def contexts(accs: list[str], key: str, n: int, seed: int = 7) -> list[str]:
    rng, out = random.Random(seed), []
    pat = RE_TOKEN.get(key) or RE_PHRASE[key]
    for acc in rng.sample(accs, len(accs)):
        with gzip.open(EX99 / f"{acc}.txt.gz", "rt", encoding="utf-8") as fh:
            text = html_to_text(fh.read())
        ms = list(pat.finditer(text))
        if ms:
            m = rng.choice(ms)
            out.append(f"{acc}: …{text[max(0, m.start() - 70):m.end() + 70]}…")
        if len(out) >= n:
            break
    return out


def main():
    meta = pd.read_parquet(SEC / "ex99_meta.parquet")
    ok = meta.loc[meta["status"] == "ok", "acc"].tolist()
    print(f"press releases with text: {len(ok):,} of {len(meta):,} earnings 8-Ks; statuses {meta['status'].value_counts().to_dict()}")
    with ProcessPoolExecutor() as pool:
        feats = pd.DataFrame(list(pool.map(one, ok, chunksize=200)))
    # Bug fix (same audit): encoded junk or empty exhibits (e.g. Liberty Global 2020, whose random characters spelled
    # "AI" 48 times) are treated like a filing without press-release text. Normal releases: stop words 16-33% of
    # words (0.5th percentile 16%), ;@>=<^` symbols ~0.07% of characters.
    feats["junk"] = (feats["stop_share"] < 0.05) | (feats["sym_share"] > 0.01)
    print(f"junk/empty texts dropped: {int(feats['junk'].sum())}; releases with a non-AI definition of 'AI' "
          f"(AI token zeroed): {int(feats['ai_redefined'].sum())}")
    feats.to_parquet(CACHE / "ai_features.parquet", index=False)

    # ---- audit (signal only, no returns)
    rel = pd.read_parquet(SEC / "earnings_8k.parquet").drop_duplicates("accessionNumber")
    f = feats.merge(rel[["accessionNumber", "accepted_et"]], left_on="acc", right_on="accessionNumber")
    f["q"] = pd.to_datetime(f["accepted_et"]).dt.to_period("Q")
    print("\nAI mentions per press release by quarter (mean / share with ≥1 / share with ≥3):")
    print(f.groupby("q").agg(n=("acc", "size"), mean_ai=("ai_full", "mean"),
                             any_ai=("ai_full", lambda x: (x >= 1).mean()),
                             ge3=("ai_full", lambda x: (x >= 3).mean()),
                             words=("n_words", "median")).round(3).to_string())
    print("\nterm totals:", feats[[c for c in feats if c.startswith("n_") and c != "n_words"]].sum().to_dict())
    with_ai = feats.loc[feats["n_AI"] > 0, "acc"].tolist()
    for key in ["AI", "A.I.", "LLM", "agentic"]:
        accs = feats.loc[feats[f"n_{key}"] > 0, "acc"].tolist()
        print(f"\n--- random contexts for {key!r} ({len(accs):,} releases) ---")
        for c in contexts(accs, key, 25 if key == "AI" else 8):
            print(c)
    print(f"\nreleases with the AI token: {len(with_ai):,}")

    # "AI" that means something else: how many releases with the AI token also contain one of these phrases?
    other = {"aromatase inhibitor": r"aromatase\s+inhibitor", "avian influenza": r"avian\s+influenza",
             "adrenal insufficiency": r"adrenal\s+insufficiency", "artificial insemination": r"artificial\s+insemination",
             "Adobe Illustrator": r"Adobe\s+Illustrator", "Amnesty International": r"Amnesty\s+International"}
    hits = {k: [] for k in other}
    for acc in with_ai:
        with gzip.open(EX99 / f"{acc}.txt.gz", "rt", encoding="utf-8") as fh:
            text = html_to_text(fh.read())
        for k, pat in other.items():
            if re.search(pat, text, re.IGNORECASE):
                hits[k].append(acc)
    print("\nreleases with the AI token that also mention a non-AI expansion:")
    for k, accs in hits.items():
        tot = int(feats.set_index("acc").loc[accs, "n_AI"].sum()) if accs else 0
        print(f"  {k}: {len(accs)} releases, {tot} AI tokens in them")
        for c in contexts(accs, "AI", 4):
            print("     ", c)

    # Sanity: the releases with the most AI mentions should be AI-heavy companies.
    comp = pd.read_parquet(SEC / "companies.parquet")
    top = (feats.merge(rel[["accessionNumber", "cik", "accepted_et"]], left_on="acc", right_on="accessionNumber")
                .merge(comp[["cik", "name"]], on="cik").sort_values("ai_full", ascending=False).head(25))
    print("\nTop 25 releases by AI mentions:")
    print(top[["name", "accepted_et", "ai_full", "n_AI", "n_words"]].to_string(index=False))


if __name__ == "__main__":
    main()
