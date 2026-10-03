# Deviations from the pre-registration (dc55459)

Every change made after the pre-registration commit is listed here with its time, reason, and whether
it could have been informed by returns. The quant note summarizes this file.

| # | Time (ET) | Change | Reason | Informed by returns? |
|---|---|---|---|---|
| 1 | 2026-10-03 00:10 | Corpus round 2: year-specific YouTube searches (2016–2024, 4 templates × CEO × year; `pipeline/corpus_search.py`), curated with the identical agent prompt and rules as round 1 | Round 1 search results skew to 2023–2026; the CEO baselines and the in-sample period need older interviews. Pure data collection; the universe and every rule are unchanged | No: decided from upload-year counts in the manifest, before any in-sample result existed (the only real-data run so far had 1 in-sample event, a code test) |
| 2 | 2026-10-03 00:25 | `config/universe.csv`: Tim Cook `tenure_end` = 2026-08-31 | Factual correction: Cook stepped down as Apple CEO on 2026-08-31 (John Ternus CEO from 2026-09-01). Removes non-CEO interviews (inside the sealed OOS window only) | No |
| 3 | 2026-10-03 00:30 | `config/universe.csv`: Bob Iger `tenure_end` = 2026-03-17 (Josh D'Amaro CEO from 2026-03-18); start-date corrections for Karp (2005), Khosrowshahi (2017-09-01), Armstrong (2012-05), Dimon (2005-12-31) | Source-verified tenure audit (Disney press release; Palantir, Uber, Coinbase, JPMorgan filings). Only the Iger change alters data (removes OOS-window interviews after he left); the start dates precede each stock's listing or the 2016 sample start | No |
| 4 | 2026-10-03 00:30 | Clarification, not a change: Sundar Pichai is kept from 2015-10-02 (CEO of Google, Alphabet's operating company and ~all of its revenue) although he became Alphabet CEO on 2019-12-03 | Economic relevance of the speaker to GOOGL; disclosed because a strict reading would start at 2019-12-03 (robustness: `leave_out_pichai`) | No |

Pipeline changes that do not touch the frozen specification (made before any in-sample result):
- Speech attribution: word-level visual attribution replaced by utterance-level audio-visual voting (≤ 15 s units),
  because word-level attribution kept only 8% of words and left most videos without voice and text features.
- Transcripts: Whisper large-v3-turbo on HiPerGator GPUs (YouTube captions are rate-limited from the cluster).
