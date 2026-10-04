"""Step 2 — SEC EDGAR data for universe companies (see PREREGISTRATION.md).

Run from the repo root:  uv run python alpha_ideas/ai_washing/fetch_sec.py
  1. submissions JSON per CIK  -> earnings 8-Ks (form 8-K, item 2.02) and 10-K filing dates, SIC code
  2. first EX-99* document of each earnings 8-K (streamed from the full submission .txt, stops once read)
  3. XBRL company facts per CIK -> capex and R&D facts (only the concepts we use are kept)
Everything is cached under data/cache/ai_washing/sec/ so the script can be stopped and resumed.
SEC fair-access: one User-Agent with a contact, <= 8 requests/second across all threads.
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from common import CACHE, RELEASE_END, RELEASE_START, sec_get, write_json

SEC = CACHE / "sec"
SUBS, EX99, FACTS = SEC / "submissions", SEC / "ex99", SEC / "facts"
for p in (SUBS, EX99, FACTS):
    p.mkdir(parents=True, exist_ok=True)

TENK_FROM = "2019-01-01"   # 10-K dates needed for the latest 10-K before the earliest release
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
         "PaymentsForCapitalImprovements"]
RND = ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"]
MAX_BYTES = 25_000_000     # stop reading a submission after this many bytes if no EX-99 has appeared


# ------------------------------------------------------------------------------------------- submissions
def _rows(block: dict) -> pd.DataFrame:
    cols = ["accessionNumber", "filingDate", "acceptanceDateTime", "form", "items", "primaryDocument"]
    return pd.DataFrame({c: block.get(c, []) for c in cols})


def submissions(cik: str) -> dict:
    path = SUBS / f"CIK{cik}.json"
    if path.exists():
        return json.loads(path.read_text())
    r = sec_get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    if r is None:
        write_json(path, {"missing": True})
        return {"missing": True}
    j = r.json()
    frames = [_rows(j["filings"]["recent"])]
    for f in j["filings"].get("files", []):
        if f.get("filingTo", "9999") >= TENK_FROM and f.get("filingFrom", "0000") <= RELEASE_END:
            r2 = sec_get(f"https://data.sec.gov/submissions/{f['name']}")
            if r2 is not None:
                frames.append(_rows(r2.json()))
    df = pd.concat(frames, ignore_index=True)
    keep = df[(df["form"].isin(["8-K", "10-K"])) & (df["filingDate"] >= TENK_FROM)]
    out = {"cik": cik, "name": j.get("name"), "sic": j.get("sic"), "sicDescription": j.get("sicDescription"),
           "tickers": j.get("tickers"), "filings": keep.to_dict(orient="list")}
    write_json(path, out)
    return out


# ------------------------------------------------------------------------------------------- EX-99 text
def ex99(cik: str, acc: str) -> dict:
    meta_path = EX99 / f"{acc}.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}.txt"
    r = sec_get(url, stream=True)
    meta = {"acc": acc, "cik": cik, "status": "missing_filing", "type": None, "filename": None, "n_docs_seen": 0}
    if r is None:
        write_json(meta_path, meta)
        return meta
    state, cur_type, cur_file, buf, nbytes, pending = "out", None, None, [], 0, b""
    try:
        for chunk in r.iter_content(chunk_size=65536):
            nbytes += len(chunk)
            pending += chunk
            *lines, pending = pending.split(b"\n")
            for raw in lines:
                line = raw.decode("utf-8", errors="replace")
                s = line.strip()
                if state == "out":
                    if s == "<DOCUMENT>":
                        state, cur_type, cur_file = "head", None, None
                        meta["n_docs_seen"] += 1
                elif state == "head":
                    if s.startswith("<TYPE>"):
                        cur_type = s[6:].strip().upper()
                    elif s.startswith("<FILENAME>"):
                        cur_file = s[10:].strip()
                    elif s.startswith("<TEXT>"):
                        if cur_type and cur_type.startswith("EX-99"):
                            state, buf = "grab", [line[line.find("<TEXT>") + 6:]]
                        else:
                            state = "skip"
                elif state == "skip":
                    if s == "</DOCUMENT>":
                        state = "out"
                elif state == "grab":
                    if s.startswith("</TEXT>"):
                        state = "done"
                        break
                    buf.append(line)
            if state == "done" or nbytes > MAX_BYTES:
                break
    finally:
        r.close()
    if state == "done":
        meta.update(type=cur_type, filename=cur_file)
        if cur_file and cur_file.lower().endswith(".pdf"):
            meta["status"] = "pdf"
        else:
            with gzip.open(EX99 / f"{acc}.txt.gz", "wt", encoding="utf-8") as fh:
                fh.write("\n".join(buf))
            meta["status"] = "ok"
    else:
        meta["status"] = "no_ex99" if nbytes <= MAX_BYTES else "no_ex99_capped"
    write_json(meta_path, meta)
    return meta


# ------------------------------------------------------------------------------------------- company facts
def facts(cik: str) -> list[dict]:
    path = FACTS / f"CIK{cik}.json"
    if path.exists():
        return json.loads(path.read_text())
    r = sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    rows = []
    if r is not None:
        gaap = r.json().get("facts", {}).get("us-gaap", {})
        for concept in CAPEX + RND:
            for u in gaap.get(concept, {}).get("units", {}).get("USD", []):
                rows.append({"concept": concept, **{k: u.get(k) for k in
                             ["start", "end", "val", "accn", "fy", "fp", "form", "filed"]}})
    write_json(path, rows)
    return rows


# ------------------------------------------------------------------------------------------- driver
def run_pool(fn, args, label, workers=8):
    t0, done, out = time.time(), 0, []
    with ThreadPoolExecutor(workers) as pool:
        futs = [pool.submit(fn, *a) for a in args]
        for f in as_completed(futs):
            out.append(f.result())
            done += 1
            if done % 500 == 0 or done == len(args):
                rate = done / max(time.time() - t0, 1e-9)
                print(f"  {label}: {done:,}/{len(args):,}  ({rate:.1f}/s, ~{(len(args) - done) / max(rate, 1e-9) / 60:.0f} min left)",
                      flush=True)
    return out


def main():
    uni = pd.read_parquet(CACHE / "universe.parquet")
    ciks = sorted(uni.loc[uni["month_end"] <= RELEASE_END, "cik"].unique())
    print(f"universe CIKs: {len(ciks):,}")

    subs = run_pool(submissions, [(c,) for c in ciks], "submissions")
    comp, rel, tenk = [], [], []
    for s in subs:
        if s.get("missing"):
            continue
        comp.append({k: s.get(k) for k in ["cik", "name", "sic", "sicDescription"]})
        f = pd.DataFrame(s["filings"])
        if f.empty:
            continue
        f["cik"] = s["cik"]
        tenk.append(f[f["form"] == "10-K"][["cik", "accessionNumber", "filingDate"]])
        e = f[(f["form"] == "8-K") & f["items"].fillna("").str.split(",").apply(lambda x: "2.02" in [i.strip() for i in x])]
        rel.append(e)
    pd.DataFrame(comp).to_parquet(SEC / "companies.parquet", index=False)
    pd.concat(tenk).to_parquet(SEC / "tenk_filings.parquet", index=False)
    rel = pd.concat(rel, ignore_index=True)
    acc_utc = pd.to_datetime(rel["acceptanceDateTime"], utc=True)
    rel["accepted_et"] = acc_utc.dt.tz_convert("America/New_York").dt.tz_localize(None)
    rel = rel[(rel["accepted_et"] >= RELEASE_START) & (rel["accepted_et"] < pd.Timestamp(RELEASE_END) + pd.Timedelta(days=1))]
    rel.to_parquet(SEC / "earnings_8k.parquet", index=False)
    print(f"earnings 8-Ks (item 2.02) {RELEASE_START}..{RELEASE_END}: {len(rel):,} filings, "
          f"{rel['accessionNumber'].nunique():,} unique accessions, {rel['cik'].nunique():,} companies")

    # Speed filter only (changes no result): a release is used either as an event (the company is in the universe at
    # the month-end before it, i.e. a member month-end in [t-35d, t)) or as a baseline release for an event within
    # the next 15 months. Both need a member month-end in [t-35 days, t+16 months).
    mem = uni.groupby("cik")["month_end"].apply(lambda s: np.sort(pd.to_datetime(s).to_numpy()))
    lo = (rel["accepted_et"] - pd.Timedelta(days=35)).to_numpy()
    hi = (rel["accepted_et"] + pd.DateOffset(months=16)).to_numpy()
    needed = []
    for c, a, b in zip(rel["cik"], lo, hi):
        arr = mem.get(c)
        k = np.searchsorted(arr, a, side="left") if arr is not None else 0
        needed.append(arr is not None and k < len(arr) and arr[k] < b)
    rel["needed"] = needed
    print(f"press releases needed by the test: {int(rel['needed'].sum()):,} of {len(rel):,}")
    jobs = (rel[rel["needed"]].drop_duplicates("accessionNumber")[["cik", "accessionNumber"]]
            .itertuples(index=False, name=None))
    metas = run_pool(ex99, list(jobs), "EX-99 press releases", workers=16)
    m = pd.DataFrame(metas)
    print("EX-99 status:", m["status"].value_counts().to_dict())
    m.to_parquet(SEC / "ex99_meta.parquet", index=False)

    run_pool(facts, [(c,) for c in ciks], "XBRL company facts")
    print("done")


if __name__ == "__main__":
    sys.exit(main())
