"""Intraday experiments, separate from the daily-return strategy interface."""
from importlib import import_module

NAMES = ("liquidity_fatigue", "queue_sacrifice", "missing_beat")


def get(name):
    if name not in NAMES:
        raise ValueError(f"Unknown microstructure strategy {name!r}; choose from {NAMES}")
    return import_module(f"microstrategies.{name}")
