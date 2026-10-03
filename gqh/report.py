"""Figures and the markdown summary that run_all.py writes to results/<strategy>/."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def md_table(df: pd.DataFrame, fmt="{:.4f}") -> str:
    def cell(v):
        return fmt.format(v) if isinstance(v, float) else str(v)

    head = [str(df.index.name or "")] + [str(c) for c in df.columns]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for idx, row in df.iterrows():
        lines.append("| " + " | ".join([str(idx)] + [cell(v) for v in row]) + " |")
    return "\n".join(lines)


def equity_curve(net: pd.Series, gross: pd.Series, oos_start, path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot((1 + gross).cumprod(), lw=1, ls="--", color="0.55", label="Gross of costs")
    ax.plot((1 + net).cumprod(), lw=1.6, color="#1f5fbf", label="Net of costs")
    if oos_start is not None and net.index.max() >= oos_start:
        ax.axvspan(oos_start, net.index.max(), color="#f2b134", alpha=0.18, label="Out-of-sample")
    ax.set_yscale("log")
    dollars = matplotlib.ticker.FuncFormatter(lambda y, _: f"${y:g}")
    ax.yaxis.set_major_formatter(dollars)
    ax.yaxis.set_minor_formatter(dollars)
    ax.set_ylabel("Growth of $1 (log scale)")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def compare_curves(curves: dict, path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for label, net in curves.items():
        ax.plot((1 + net).cumprod(), lw=1.3, label=label)
    ax.set_yscale("log")
    dollars = matplotlib.ticker.FuncFormatter(lambda y, _: f"${y:g}")
    ax.yaxis.set_major_formatter(dollars)
    ax.yaxis.set_minor_formatter(dollars)
    ax.set_ylabel("Growth of $1 (log scale)")
    ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def bars_by_year(yearly: pd.Series, oos_year: int | None, path, title: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 3.5))
    colors = ["#f2b134" if oos_year and y >= oos_year else "#1f5fbf" for y in yearly.index]
    ax.bar(yearly.index.astype(str), yearly.values * 100, color=colors)
    ax.axhline(0, color="0.3", lw=0.8)
    ax.set_ylabel("Net return (%)")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plateau(values, sharpes, chosen, param: str, path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot([str(v) for v in values], sharpes, marker="o", color="#1f5fbf")
    if chosen in values:
        i = list(values).index(chosen)
        ax.plot(str(chosen), sharpes[i], marker="o", ms=11, mfc="none", mec="#d1495b", mew=2, label="Chosen")
        ax.legend(frameon=False)
    ax.axhline(0, color="0.3", lw=0.8)
    ax.set_xlabel(param)
    ax.set_ylabel("In-sample Sharpe (net)")
    ax.set_title(f"Parameter plateau: {param}")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
