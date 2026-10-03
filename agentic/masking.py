"""Entity masking for LLM labeling of CEO utterances.

Why: an LLM that recognizes "Jensen Huang, NVIDIA, Blackwell, 2024" also knows what NVDA did
next. If it can see who is speaking and when, its labels can carry hindsight about the stock,
which is lookahead. We replace identifying tokens with fixed placeholders before any text
leaves the machine. The labeler then sees only how something is said.

Placeholders
  [CEO]            the speaking CEO (full name, first name, last name)
  [PERSON]         other universe CEOs and extra people (hosts, analysts) passed in
  [COMPANY]        the speaker's own company / ticker
  [OTHER_COMPANY]  other universe companies and extra companies
  [PRODUCT]        products / platforms of any universe company (case-sensitive)
  [TICKER]         cashtags ($XYZ) and universe tickers
  [YEAR]           1990-2039 four-digit years, FY24 / FY2024, '24
  [QUARTER]        Q1-Q4, "first quarter" .. "fourth quarter" kept as-is (not identifying)
  [DATE]           "March 15", "15 March", 3/15/2024, 2024-03-15
  [MONTH]          capitalized month names ("May" only before a number or [YEAR])
  [NUM]            remaining numerals (units such as "billion", "percent", "%" are kept, so
                   numeric_claim stays detectable while exact magnitudes, which can identify
                   a company and quarter, are hidden)

Masking is deterministic and order-fixed (longest strings first). `leak_check` reports any
residue (4-digit years, known names) so a batch can be blocked before it is sent.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_CSV = ROOT / "config" / "universe.csv"

COMPANY_NAMES = {
    "TSLA": ["Tesla", "Tesla Motors", "SpaceX", "xAI", "X Corp", "Twitter"],
    "NVDA": ["NVIDIA", "Nvidia"],
    "PLTR": ["Palantir", "Palantir Technologies"],
    "META": ["Meta", "Meta Platforms", "Facebook"],
    "AAPL": ["Apple"],
    "MSFT": ["Microsoft"],
    "GOOGL": ["Alphabet", "Google", "DeepMind", "YouTube", "Waymo"],
    "AMZN": ["Amazon", "Amazon Web Services", "AWS"],
    "AMD": ["AMD", "Advanced Micro Devices", "Xilinx"],
    "JPM": ["JPMorgan", "JP Morgan", "J.P. Morgan", "JPMorgan Chase", "Chase"],
    "COIN": ["Coinbase"],
    "CRM": ["Salesforce", "Slack", "Tableau"],
    "UBER": ["Uber", "Uber Eats"],
    "INTC": ["Intel"],
    "DIS": ["Disney", "Walt Disney", "Pixar", "Marvel", "ESPN", "Hulu"],
    "GM": ["General Motors", "GM", "Cruise", "Chevrolet", "Chevy", "Cadillac"],
    "F": ["Ford", "Ford Motor"],
    "MSTR": ["MicroStrategy"],
    "BAC": ["Bank of America", "BofA", "Merrill", "Merrill Lynch"],
    "GS": ["Goldman", "Goldman Sachs"],
}
PRODUCTS = {
    "TSLA": ["Model S", "Model 3", "Model X", "Model Y", "Cybertruck", "Tesla Semi", "Optimus", "Robotaxi",
             "Cybercab", "Autopilot", "FSD", "Full Self-Driving", "Dojo", "Megapack", "Powerwall",
             "Starlink", "Starship", "Falcon", "Grok", "Neuralink", "Gigafactory"],
    "NVDA": ["Blackwell", "Hopper", "Rubin", "Grace", "H100", "H200", "H20", "B200", "GB200", "A100",
             "CUDA", "GeForce", "DGX", "Omniverse", "NVLink", "Mellanox", "Spectrum-X", "Jetson"],
    "PLTR": ["Gotham", "Foundry", "Apollo", "AIP", "Maven"],
    "META": ["Instagram", "WhatsApp", "Messenger", "Threads", "Oculus", "Quest", "Ray-Ban", "Llama",
             "Reality Labs", "Horizon", "Orion"],
    "AAPL": ["iPhone", "iPad", "Mac", "MacBook", "Vision Pro", "Apple Watch", "AirPods", "App Store",
             "iCloud", "Siri", "Apple Intelligence", "Apple Pay", "Apple TV"],
    "MSFT": ["Azure", "Windows", "Office", "Copilot", "Xbox", "Teams", "LinkedIn", "GitHub", "Bing",
             "Activision", "OpenAI", "ChatGPT", "Surface"],
    "GOOGL": ["Gemini", "Bard", "Android", "Chrome", "Pixel", "TPU", "Google Cloud"],
    "AMZN": ["Prime", "Alexa", "Kindle", "Kuiper", "Trainium", "Inferentia", "Bedrock", "Whole Foods",
             "Zoox", "Anthropic"],
    "AMD": ["Ryzen", "EPYC", "Radeon", "Instinct", "MI300", "MI300X", "MI325", "MI350", "MI400", "ROCm"],
    "JPM": ["First Republic"],
    "COIN": ["USDC", "Coinbase One"],
    "CRM": ["Agentforce", "Einstein", "MuleSoft"],
    "UBER": ["Uber One"],
    "INTC": ["Xeon", "Core Ultra", "Gaudi", "Intel Foundry", "18A", "20A", "Mobileye"],
    "DIS": ["Disney+", "Disney Plus", "Star Wars"],
    "GM": ["Ultium", "Bolt", "Silverado"],
    "F": ["F-150", "Lightning", "Mustang Mach-E", "Bronco"],
    "MSTR": ["bitcoin treasury"],
    "BAC": ["Erica"],
    "GS": ["Marcus", "Apple Card"],
}
# Lower-case forms of these are ordinary English words; match them case-sensitively only.
_CASE_SENSITIVE = {"apple", "meta", "amazon", "base", "semi", "quest", "prime", "search", "office",
                   "windows", "teams", "surface", "chrome", "falcon", "grace", "hopper", "foundry",
                   "apollo", "horizon", "strategy", "chase", "cruise", "bolt", "lightning", "core",
                   "marcus", "threads", "messenger", "instinct", "gemini", "erica", "f", "gm", "x corp"}

MONTHS = ["January", "February", "March", "April", "June", "July", "August", "September",
          "October", "November", "December", "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug",
          "Sep", "Sept", "Oct", "Nov", "Dec"]


@dataclass
class Entities:
    ceo_names: list[str] = field(default_factory=list)
    company: list[str] = field(default_factory=list)
    other_people: list[str] = field(default_factory=list)
    other_companies: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)


def _universe() -> list[dict]:
    if not UNIVERSE_CSV.exists():
        return []
    with open(UNIVERSE_CSV) as f:
        return list(csv.DictReader(f))


def _name_parts(full: str) -> list[str]:
    parts = [p for p in re.split(r"\s+", full.strip()) if len(p) > 1]
    return [full] + parts


def entities_for(ticker: str, extra_people: tuple[str, ...] = (), extra_companies: tuple[str, ...] = (),
                 extra_products: tuple[str, ...] = ()) -> Entities:
    """Build the masking set for a video of `ticker`'s CEO. extra_* come from the video metadata
    (host / channel names, guests) so the show and date cannot be inferred either."""
    ticker = ticker.upper()
    rows = _universe()
    e = Entities(tickers=sorted({r["ticker"].upper() for r in rows} | {ticker}))
    for r in rows:
        if r["ticker"].upper() == ticker:
            e.ceo_names += _name_parts(r["name"])
        else:
            e.other_people += _name_parts(r["name"])
    e.company = [ticker] + COMPANY_NAMES.get(ticker, [])
    e.other_companies = [n for t, ns in COMPANY_NAMES.items() if t != ticker for n in ns]
    e.other_companies += list(extra_companies)
    e.other_people += list(extra_people)
    e.products = sorted({p for ps in PRODUCTS.values() for p in ps} | set(extra_products))
    return e


def _term_re(term: str, case_sensitive: bool) -> re.Pattern:
    body = re.escape(term)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<![\w\[])" + body + r"(?![\w\]])", flags)


def mask_text(text: str, ents: Entities) -> tuple[str, dict[str, int]]:
    """Return (masked_text, counts per placeholder)."""
    counts: dict[str, int] = {}
    out = text

    def sub(pattern: re.Pattern, repl: str) -> None:
        nonlocal out
        out, n = pattern.subn(repl, out)
        if n:
            counts[repl] = counts.get(repl, 0) + n

    # 1) dates and years first, so "March 15, 2024" becomes one [DATE]
    mon = "|".join(sorted(MONTHS + ["May"], key=len, reverse=True))
    sub(re.compile(rf"\b(?:{mon})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+(?:19|20)\d{{2}})?\b"), "[DATE]")
    sub(re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{mon})\b(?:,?\s+(?:19|20)\d{{2}})?"), "[DATE]")
    sub(re.compile(r"\b(?:19|20)\d{2}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}/(?:19|20)?\d{2}\b"), "[DATE]")
    sub(re.compile(r"\bF[Yy]\s?'?(?:19|20)?\d{2}\b"), "[YEAR]")
    sub(re.compile(r"\b(?:fiscal|calendar)\s+(?:year\s+)?(?:19|20)\d{2}\b", re.I), "[YEAR]")
    sub(re.compile(r"\b(?:199\d|20[0-3]\d)s?\b"), "[YEAR]")
    sub(re.compile(r"(?<![\w$])'\d{2}\b"), "[YEAR]")
    sub(re.compile(r"\bQ[1-4]\b"), "[QUARTER]")
    sub(re.compile(r"\bMay(?=\s+(?:\d|\[YEAR\]))"), "[MONTH]")
    sub(re.compile(r"\b(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b"), "[MONTH]")

    # 2) names, companies, products, tickers (longest first inside each class)
    def terms(ts, repl, force_cs=False):
        for t in sorted(set(ts), key=len, reverse=True):
            if not t:
                continue
            cs = force_cs or t.lower() in _CASE_SENSITIVE or len(t) <= 3
            sub(_term_re(t, cs), repl)

    sub(re.compile(r"\$[A-Z]{1,5}\b"), "[TICKER]")
    terms(ents.ceo_names, "[CEO]", force_cs=True)
    terms(ents.other_people, "[PERSON]", force_cs=True)
    terms(ents.products, "[PRODUCT]", force_cs=True)
    terms(ents.company, "[COMPANY]")
    terms(ents.other_companies, "[OTHER_COMPANY]")
    terms(ents.tickers, "[TICKER]", force_cs=True)

    # 3) remaining numerals (keep units so numeric claims stay visible)
    sub(re.compile(r"(?<![\w\[])\$?\d(?:[\d,]*\d)?(?:\.\d+)?(?!\d)"), "[NUM]")
    return out, counts


def leak_check(masked: str, ents: Entities) -> list[str]:
    """Residual identifying strings. Empty list means safe to send."""
    hits = re.findall(r"\b(?:19|20)\d{2}\b", masked)
    low = masked.lower()
    for t in ents.ceo_names + ents.company:
        if len(t) > 3 and re.search(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)", low) and \
                t.lower() not in _CASE_SENSITIVE:
            hits.append(t)
    return hits
