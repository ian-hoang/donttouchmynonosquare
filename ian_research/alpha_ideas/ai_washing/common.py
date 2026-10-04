"""Shared paths, API sessions and small helpers for the AI-washing test (see PREREGISTRATION.md)."""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GROUPED = ROOT / "data" / "cache" / "massive_grouped"
CACHE = ROOT / "data" / "cache" / "ai_washing"  # gitignored (data/cache/)
CACHE.mkdir(parents=True, exist_ok=True)

SEC_UA = "Ian Hoang ianhoang.dev@gmail.com"  # approved by Ian on 2026-10-03, SEC requests only
MASSIVE = "https://api.massive.com"

PRICE_START, PRICE_END = "2020-01-01", "2026-09-30"
RELEASE_START, RELEASE_END = "2020-07-01", "2026-06-30"  # acceptance dates (New York time)


def massive_key() -> str:
    sys.path.insert(0, str(ROOT / "massive"))
    from eightk import load_api_key  # read-only import of the existing key loader
    return load_api_key()


_local = threading.local()


def massive_session() -> requests.Session:
    s = getattr(_local, "massive", None)
    if s is None:
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {massive_key()}"
        _local.massive = s
    return s


def massive_get(url: str, params: dict | None = None) -> tuple[int, dict]:
    """GET with retries on 429/5xx. Returns (status, json or {})."""
    for attempt in range(8):
        r = massive_session().get(url if url.startswith("http") else MASSIVE + url, params=params, timeout=60)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(2 ** attempt, 30))
            continue
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {}
    r.raise_for_status()
    return r.status_code, {}


def massive_all(path: str, params: dict) -> list[dict]:
    status, j = massive_get(path, params)
    if status != 200:
        raise RuntimeError(f"{path} {params} -> {status} {str(j)[:200]}")
    out = list(j.get("results") or [])
    while j.get("next_url"):
        status, j = massive_get(j["next_url"])
        if status != 200:
            raise RuntimeError(f"next page -> {status}")
        out.extend(j.get("results") or [])
    return out


class RateLimiter:
    """Global token bucket shared by threads: at most `rate` requests per second (SEC allows 10)."""

    def __init__(self, rate: float):
        self.interval = 1.0 / rate
        self.lock = threading.Lock()
        self.next_t = time.monotonic()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next_t)
            self.next_t = t + self.interval
        if t > now:
            time.sleep(t - now)


SEC_LIMIT = RateLimiter(8.0)


def sec_session() -> requests.Session:
    s = getattr(_local, "sec", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": SEC_UA, "Accept-Encoding": "gzip, deflate"})
        _local.sec = s
    return s


def sec_get(url: str, stream: bool = False) -> requests.Response | None:
    """Rate-limited SEC GET with backoff. Returns None on 404."""
    for attempt in range(8):
        SEC_LIMIT.wait()
        try:
            r = sec_session().get(url, timeout=60, stream=stream)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 404:
            return None
        if r.status_code in (403, 429, 500, 502, 503, 504):
            time.sleep(min(5 * 2 ** attempt, 120))
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"SEC GET failed repeatedly: {url}")


def write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(obj))
    tmp.replace(path)
