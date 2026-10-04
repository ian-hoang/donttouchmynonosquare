"""Shared research harness for the GQH Systematic Trading track."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
RESULTS = ROOT / "results"
