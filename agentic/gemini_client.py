"""Gemini structured-output client with a write-once disk cache.

Reproducibility contract
- Cache key = sha256 of the canonical JSON of {model, prompt, schema, config}. "prompt" includes
  the system instruction and the prompt-template version, "config" the seed / temperature /
  thinking level. Any change to any of them is a new key; nothing is ever overwritten.
- Records live in data/cache/llm/<key[:2]>/<key>.json with the request, raw response text,
  parsed JSON, model_version reported by the API, token usage, SDK version and UTC time.
  data/cache/ is gitignored. Ship data/cache/llm/ as a release asset or copy the small JSON
  files into a committed folder so judges reproduce labels without a key.
- offline=True (or POKERFACE_LLM_OFFLINE=1) turns a cache miss into CacheMiss. Use it for every
  backtest run so labels can never change silently after the hypothesis is frozen.
- Calls are sequential, one process, with a minimum gap between requests (free tier) and
  exponential backoff on 429 / 5xx.

Temperature: the request asked for temperature 0 + seed. Google's Gemini 3 guide says to keep
temperature at the default 1.0 and warns that lower values can cause looping
(ai.google.dev/gemini-api/docs/gemini-3). We therefore leave temperature unset by default,
always send a fixed seed, and get determinism from the cache. Pass temperature=0.0 to override.

Model ids (ai.google.dev/gemini-api/docs/models, checked 2026-10-02): default
gemini-3.5-flash-lite (stable, has a free tier). Override with $GEMINI_MODEL.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache" / "llm"
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")


class CacheMiss(LookupError):
    pass


class InvalidResponse(ValueError):
    pass


def _schema_dict(schema: Any) -> dict:
    if isinstance(schema, dict):
        return schema
    if hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()
    raise TypeError("schema must be a JSON-schema dict or a pydantic model class")


def cache_key(model: str, prompt: str, schema: dict, config: dict) -> str:
    blob = json.dumps({"model": model, "prompt": prompt, "schema": schema, "config": config},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _env_key() -> str | None:
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if k:
        return k
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                v = line.split("=", 1)[1].split("#", 1)[0].strip()
                return v or None
    return None


def google_transport(api_key: str | None = None) -> Callable[[dict], dict]:
    """Real API call. Returns {"text", "model_version", "usage"}. Imported lazily."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key or _env_key())

    def call(req: dict) -> dict:
        cfg = req["config"]
        kw: dict[str, Any] = dict(response_mime_type="application/json",
                                  response_json_schema=req["schema"], seed=cfg["seed"])
        if cfg.get("system"):
            kw["system_instruction"] = cfg["system"]
        if cfg.get("temperature") is not None:
            kw["temperature"] = cfg["temperature"]
        if cfg.get("thinking_level"):
            kw["thinking_config"] = types.ThinkingConfig(thinking_level=cfg["thinking_level"])
        if cfg.get("max_output_tokens"):
            kw["max_output_tokens"] = cfg["max_output_tokens"]
        r = client.models.generate_content(model=req["model"], contents=req["prompt"],
                                           config=types.GenerateContentConfig(**kw))
        usage = r.usage_metadata.model_dump(exclude_none=True) if r.usage_metadata else {}
        return {"text": r.text, "model_version": getattr(r, "model_version", None), "usage": usage}

    return call


class GeminiClient:
    def __init__(self, model: str = DEFAULT_MODEL, cache_dir: Path | str = CACHE_DIR, *,
                 offline: bool | None = None, seed: int = 7, temperature: float | None = None,
                 thinking_level: str | None = "low", max_output_tokens: int | None = 8192,
                 min_interval_s: float = 6.0, max_retries: int = 5,
                 transport: Callable[[dict], dict] | None = None):
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.offline = (os.environ.get("POKERFACE_LLM_OFFLINE") == "1") if offline is None else offline
        self.seed, self.temperature, self.thinking_level = seed, temperature, thinking_level
        self.max_output_tokens = max_output_tokens
        self.min_interval_s, self.max_retries = min_interval_s, max_retries
        self._transport = transport
        self._last_call = 0.0
        self.n_api_calls = 0
        self.n_cache_hits = 0

    def _path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def _send(self, req: dict) -> dict:
        if self._transport is None:
            self._transport = google_transport()
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval_s - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            try:
                self.n_api_calls += 1
                return self._transport(req)
            except Exception as e:  # retry only rate limits and server errors
                code = getattr(e, "code", None) or getattr(e, "status_code", None)
                if code not in (429, 500, 502, 503, 504) or attempt == self.max_retries:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
        raise RuntimeError("unreachable")

    def generate_json(self, prompt: str, schema: Any, *, system: str | None = None,
                      validator: Callable[[dict], Any] | None = None) -> dict:
        """Structured JSON for `prompt`, from cache when possible. `validator` (e.g. a pydantic
        model's model_validate) must accept the parsed JSON; invalid output is never cached."""
        sch = _schema_dict(schema)
        config = {"seed": self.seed, "temperature": self.temperature, "thinking_level": self.thinking_level,
                  "max_output_tokens": self.max_output_tokens, "system": system}
        key = cache_key(self.model, prompt, sch, config)
        path = self._path(key)
        if path.exists():
            self.n_cache_hits += 1
            return json.loads(path.read_text())["parsed"]
        if self.offline:
            raise CacheMiss(f"offline and no cache entry {path.name} (model={self.model})")
        req = {"model": self.model, "prompt": prompt, "schema": sch, "config": config}
        resp = self._send(req)
        try:
            parsed = json.loads(resp["text"])
        except (TypeError, json.JSONDecodeError) as e:
            raise InvalidResponse(f"non-JSON response for key {key[:12]}: {str(resp.get('text'))[:200]}") from e
        if validator is not None:
            try:
                validator(parsed)
            except Exception as e:
                raise InvalidResponse(f"schema validation failed for key {key[:12]}: {e}") from e
        try:
            from importlib.metadata import version
            sdk = version("google-genai")
        except Exception:
            sdk = None
        rec = {"key": key, "request": req, "response_text": resp["text"], "parsed": parsed,
               "model_version": resp.get("model_version"), "usage": resp.get("usage"),
               "sdk": sdk, "created_utc": datetime.now(timezone.utc).isoformat()}
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1))
        tmp.replace(path)
        return parsed
