"""One file per idea. Each file ends with `STRATEGY = YourClass`. The file name is the strategy's name."""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path


def available() -> list[str]:
    here = Path(__file__).parent
    return sorted(m.name for m in pkgutil.iter_modules([str(here)]) if not m.name.startswith("_") and m.name != "base")


def get(name: str):
    if name not in available():
        raise SystemExit(f"No strategy '{name}'. Available: {', '.join(available()) or 'none'}")
    strategy = importlib.import_module(f"strategies.{name}").STRATEGY()
    strategy.name = name
    return strategy
