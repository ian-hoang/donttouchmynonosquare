"""Build wide daily panels (dates x tickers) for the residual-momentum rebuild from the cached grouped bars.

Input: data/cache/massive_grouped/grouped_YYYY.parquet + tickers_cs.parquet (made by alpha_ideas/smooth_losers/fetch_data.py).
Output: data/cache/resmom/panel.pkl  {close, close_raw, dv, ret, ff}
Run: uv run python resmom/panel.py
"""
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GROUPED = ROOT / "data" / "cache" / "massive_grouped"
OUT = ROOT / "data" / "cache" / "resmom"
START, END = "2010-01-01", "2026-09-30"
RET_LO, RET_HI = -0.70, 2.00       # daily returns outside this band -> NaN (teammate's convention)
MAX_GAP = 5                        # a return spanning more than 5 missing sessions -> NaN


def load_ff() -> pd.DataFrame:
    z = zipfile.ZipFile(ROOT / "data" / "cache" / "F-F_Research_Data_Factors_daily_CSV.zip")
    lines = [l for l in z.read(z.namelist()[0]).decode("latin1").splitlines()
             if l[:8].strip().isdigit() and len(l.split(",")) >= 5]
    ff = pd.read_csv(io.StringIO("\n".join(lines)), header=None, names=["date", "mkt", "smb", "hml", "rf"])
    ff.index = pd.to_datetime(ff.pop("date").astype(str).str.strip(), format="%Y%m%d")
    return ff / 100


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cs = set(pd.read_parquet(GROUPED / "tickers_cs.parquet").ticker)
    years = range(int(START[:4]), int(END[:4]) + 1)
    g = pd.concat([pd.read_parquet(GROUPED / f"grouped_{y}.parquet") for y in years], ignore_index=True)
    g = g[g.ticker.isin(cs | {"SPY"}) & g.date.between(START, END)]
    g["dv"] = g.close_raw * g.volume
    # keep tickers that could ever enter a liquid universe (cuts the matrix size)
    ok = g[(g.close_raw >= 5) & (g.dv >= 1e6)].ticker.unique()
    g = g[g.ticker.isin(ok)]
    wide = {c: g.pivot(index="date", columns="ticker", values=c).astype("float64") for c in ("close", "close_raw", "dv")}
    close = wide["close"]
    sessions = close.index
    # return vs the last available close, NaN if the gap is longer than MAX_GAP sessions
    pos = pd.DataFrame(np.where(close.notna(), np.arange(len(sessions))[:, None], np.nan), index=sessions, columns=close.columns)
    last_pos = pos.ffill().shift(1)
    last_px = close.ffill().shift(1)
    ret = close / last_px - 1
    ret = ret.where(close.notna() & ((pos - last_pos) <= MAX_GAP + 1))
    n_bad = int(((ret < RET_LO) | (ret > RET_HI)).sum().sum())
    ret_raw = ret.copy()
    ret = ret.where((ret >= RET_LO) & (ret <= RET_HI))
    pd.to_pickle({**wide, "ret": ret, "ret_unfiltered": ret_raw, "ff": load_ff()}, OUT / "panel.pkl")
    print(f"panel {close.shape}, sessions {sessions[0]:%Y-%m-%d}..{sessions[-1]:%Y-%m-%d}; "
          f"returns outside ({RET_LO}, {RET_HI}) set NaN: {n_bad}")


if __name__ == "__main__":
    main()
