"""Verbal features from the CEO's own words (one video -> one dict of rates per 100 words).

Lexicons and their sources:
- Loughran & McDonald (2011, J. Finance) financial sentiment dictionary: Negative, Positive,
  Uncertainty, Litigious, Constraining, strong/weak modal. Word list as bundled in `pysentiment2` (LM.csv).
- Larcker & Zakolyukina (2012, J. Accounting Research) deception categories for executives on calls:
  references to general knowledge, shareholder value, extreme positive/negative emotion, anxiety,
  self vs. group vs. impersonal reference, negation, certainty, hesitation. Their lists combine LIWC with
  self-built lists; LIWC is proprietary, so we use short transparent lists in the same spirit (below).
- Hedges follow Hyland (1998); denial phrases are ours, chosen before any backtest.
- Detail density (numbers per 100 words) operationalizes DePaulo et al. (2003)'s "fewer details" cue.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+(?:[.,]\d+)*%?")

PHRASES = {
    "general_knowledge": ["you know", "as you know", "everybody knows", "everyone knows", "we all know",
                          "of course", "obviously", "clearly", "it's obvious", "needless to say",
                          "as everyone knows", "you guys know"],
    "shareholder_value": ["shareholder value", "value for shareholders", "value for our shareholders",
                          "shareholder return", "shareholder returns", "value creation", "create value",
                          "creating value", "unlock value", "long-term value"],
    "hedge": ["i think", "i believe", "i guess", "we think", "we believe", "sort of", "kind of",
              "more or less", "to some extent", "in a sense", "i would say", "i'd say"],
    "denial": ["not true", "that's not true", "that is not true", "no truth", "absolutely not",
               "not at all", "no plans", "no plan to", "no intention", "never said", "that's false",
               "that is false", "fake news", "not happening", "nothing to it", "categorically",
               "we're not going to", "we are not going to", "that's wrong", "that is wrong",
               "that's a myth", "rumor", "rumors", "speculation", "deny", "denied"],
    "filler": ["um", "uh", "er", "erm", "ah", "hmm", "i mean", "you know"],
    "forward_looking": ["will", "going to", "gonna", "expect", "expects", "plan to", "plans to",
                        "anticipate", "next year", "next quarter", "soon", "by the end of", "in the future"],
}

WORDS = {
    "extreme_positive": {"fantastic", "excellent", "superb", "outstanding", "incredible", "amazing",
                         "tremendous", "phenomenal", "extraordinary", "exceptional", "spectacular",
                         "awesome", "unbelievable", "insane", "terrific", "wonderful", "perfect",
                         "remarkable", "revolutionary", "unprecedented", "epic", "mind-blowing"},
    "extreme_negative": {"terrible", "horrible", "awful", "disaster", "disastrous", "catastrophic",
                         "catastrophe", "devastating", "horrendous", "nightmare", "worst", "abysmal"},
    "anxiety": {"worried", "worry", "worries", "nervous", "afraid", "fear", "fears", "anxious",
                "anxiety", "concerned", "scared", "panic", "tense", "uneasy", "stress", "stressed"},
    "first_singular": {"i", "me", "my", "mine", "myself", "i'm", "i've", "i'd", "i'll"},
    "first_plural": {"we", "us", "our", "ours", "ourselves", "we're", "we've", "we'd", "we'll"},
    "third_plural": {"they", "them", "their", "theirs", "themselves", "they're", "they've", "they'll"},
    "impersonal": {"it", "it's", "its", "this", "that", "these", "those", "anything", "something",
                   "nothing", "everything", "someone", "somebody", "anyone", "anybody", "everyone",
                   "everybody", "one"},
    "negation": {"no", "not", "never", "none", "nobody", "nothing", "neither", "nor", "don't", "isn't",
                 "wasn't", "can't", "won't", "didn't", "doesn't", "aren't", "weren't", "haven't",
                 "hasn't", "hadn't", "shouldn't", "wouldn't", "couldn't", "cannot"},
    "certainty": {"absolutely", "certainly", "definitely", "always", "never", "completely", "totally",
                  "undoubtedly", "guaranteed", "sure", "entirely", "100%", "undeniably", "indisputably"},
    "hedge_word": {"maybe", "perhaps", "possibly", "probably", "might", "could", "may", "seem", "seems",
                   "appear", "appears", "suggest", "suggests", "likely", "unlikely", "approximately",
                   "roughly", "somewhat", "around", "about"},
}
NUMBER_WORDS = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "eleven", "twelve", "twenty", "thirty", "forty", "fifty", "hundred", "thousand",
                "million", "billion", "trillion", "percent", "half", "quarter", "dozen"}


@lru_cache(maxsize=1)
def _lm() -> dict[str, set[str]]:
    import pysentiment2

    path = Path(pysentiment2.__file__).parent / "static" / "LM.csv"
    d = pd.read_csv(path)
    d["Word"] = d["Word"].astype(str).str.lower()
    out = {c.lower(): set(d.loc[d[c] > 0, "Word"]) for c in
           ["Negative", "Positive", "Uncertainty", "Litigious", "Constraining"]}
    out["strong_modal"] = set(d.loc[d["Modal"] == 1, "Word"])
    out["weak_modal"] = set(d.loc[d["Modal"] == 3, "Word"])
    return out


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower().replace("’", "'"))


def _count_phrases(text: str, phrases: list[str]) -> int:
    """Non-overlapping counts, longest phrase first ("that's not true" is one denial, not two)."""
    t = " " + re.sub(r"\s+", " ", text.lower().replace("’", "'")) + " "
    n = 0
    for p in sorted(phrases, key=len, reverse=True):
        t, k = re.subn(r"(?<![a-z'])" + re.escape(p) + r"(?![a-z'])", " | ", t)
        n += k
    return n


def text_features(text: str, speech_seconds: float | None = None, min_words: int = 150) -> dict:
    """Rates per 100 words of the CEO's speech. Returns NaNs below `min_words` (too little text)."""
    toks = tokenize(text)
    n = len(toks)
    feats: dict[str, float] = {"n_words": float(n)}
    keys = (list(PHRASES) + list(WORDS) + ["lm_" + k for k in _lm()] +
            ["numbers", "lm_net_tone", "words_per_min", "type_token_ratio"])
    if n < min_words:
        feats.update({f"txt_{k}": np.nan for k in keys})
        return feats
    per100 = 100.0 / n
    for k, ph in PHRASES.items():
        feats[f"txt_{k}"] = _count_phrases(text, ph) * per100
    for k, ws in WORDS.items():
        feats[f"txt_{k}"] = sum(t in ws for t in toks) * per100
    lm = _lm()
    for k, ws in lm.items():
        feats[f"txt_lm_{k}"] = sum(t in ws for t in toks) * per100
    pos, neg = feats["txt_lm_positive"], feats["txt_lm_negative"]
    feats["txt_lm_net_tone"] = (pos - neg) / (pos + neg + 1.0)
    feats["txt_numbers"] = sum(t[0].isdigit() or t in NUMBER_WORDS for t in toks) * per100
    feats["txt_words_per_min"] = n / (speech_seconds / 60.0) if speech_seconds and speech_seconds > 30 else np.nan
    first = toks[:1000]
    feats["txt_type_token_ratio"] = len(set(first)) / len(first)
    return feats


if __name__ == "__main__":
    demo = ("You know, we are absolutely not discontinuing that product. That's not true. "
            "We expect incredible growth next year, maybe 50 percent, I think. ") * 20
    for k, v in text_features(demo, speech_seconds=120).items():
        print(f"{k:28s} {v:8.2f}")
