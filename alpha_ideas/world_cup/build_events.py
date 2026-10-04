"""Step 2 — matches -> loss/win events with their event day (PREREGISTRATION.md "Timing"). Uses no returns.

Run from the repo root:  uv run python alpha_ideas/world_cup/build_events.py
Writes data/cache/world_cup/matches.parquet and events.parquet, and prints the cross-check against martj42.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache" / "world_cup"
YEARS = [2006, 2010, 2014, 2018, 2022, 2026]
DEFAULT_OFFSET = {2006: "+02:00", 2010: "+02:00", 2022: "+03:00"}   # host-country time where the file has no offset
DEFAULT_TIME_2006 = "21:00"                                          # 2006 has no kickoff times (see PREREGISTRATION)
KNOCKOUT = {"Round of 32", "Round of 16", "Quarter-final", "Quarter-finals", "Quarterfinals", "Semi-final",
            "Semi-finals", "Semifinals", "Match for third place", "Third place play-off", "Third-place play-off", "Final"}

# country -> (ETF tickers in date order with their first/last valid date, exchange time zone, local open, weekdays)
MON_FRI, SUN_THU = (0, 1, 2, 3, 4), (6, 0, 1, 2, 3)
ETF = {
    "Germany": ("EWG", "Europe/Berlin", "09:00", MON_FRI), "England": ("EWU", "Europe/London", "08:00", MON_FRI),
    "France": ("EWQ", "Europe/Paris", "09:00", MON_FRI), "Spain": ("EWP", "Europe/Madrid", "09:00", MON_FRI),
    "Italy": ("EWI", "Europe/Rome", "09:00", MON_FRI), "Netherlands": ("EWN", "Europe/Amsterdam", "09:00", MON_FRI),
    "Belgium": ("EWK", "Europe/Brussels", "09:00", MON_FRI), "Switzerland": ("EWL", "Europe/Zurich", "09:00", MON_FRI),
    "Sweden": ("EWD", "Europe/Stockholm", "09:00", MON_FRI), "Austria": ("EWO", "Europe/Vienna", "09:00", MON_FRI),
    "Denmark": ("EDEN", "Europe/Copenhagen", "09:00", MON_FRI), "Norway": ("NORW", "Europe/Oslo", "09:00", MON_FRI),
    "Poland": ("EPOL", "Europe/Warsaw", "09:00", MON_FRI), "Portugal": ("PGAL", "Europe/Lisbon", "08:00", MON_FRI),
    "Greece": ("GREK", "Europe/Athens", "10:00", MON_FRI), "Turkey": ("TUR", "Europe/Istanbul", "10:00", MON_FRI),
    "Russia": ("RSX", "Europe/Moscow", "10:00", MON_FRI), "Ireland": ("EIRL", "Europe/Dublin", "08:00", MON_FRI),
    "United States": ("SPY", "America/New_York", "09:30", MON_FRI),
    "Canada": ("EWC", "America/Toronto", "09:30", MON_FRI), "Mexico": ("EWW", "America/Mexico_City", "08:30", MON_FRI),
    "Brazil": ("EWZ", "America/Sao_Paulo", "10:00", MON_FRI),
    "Argentina": ("ARGT", "America/Argentina/Buenos_Aires", "11:00", MON_FRI),
    "Chile": ("ECH", "America/Santiago", "09:30", MON_FRI), "Colombia": ("GXG|COLO", "America/Bogota", "09:30", MON_FRI),
    "Peru": ("EPU", "America/Lima", "09:00", MON_FRI), "Japan": ("EWJ", "Asia/Tokyo", "09:00", MON_FRI),
    "South Korea": ("EWY", "Asia/Seoul", "09:00", MON_FRI), "Australia": ("EWA", "Australia/Sydney", "10:00", MON_FRI),
    "Saudi Arabia": ("KSA", "Asia/Riyadh", "10:00", SUN_THU), "Qatar": ("QAT", "Asia/Qatar", "09:30", SUN_THU),
    "New Zealand": ("ENZL", "Pacific/Auckland", "10:00", MON_FRI),
    "South Africa": ("EZA", "Africa/Johannesburg", "09:00", MON_FRI), "Egypt": ("EGPT", "Africa/Cairo", "10:00", SUN_THU),
    "Nigeria": ("NGE", "Africa/Lagos", "10:00", MON_FRI),
}
# openfootball / martj42 spellings -> one name
ALIASES = {"USA": "United States", "Korea Republic": "South Korea", "Korea": "South Korea", "Republic of Korea": "South Korea",
           "IR Iran": "Iran", "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast", "Czechia": "Czech Republic",
           "Serbia and Montenegro": "Serbia", "Bosnia-Herzegovina": "Bosnia and Herzegovina",
           "Bosnia & Herzegovina": "Bosnia and Herzegovina",
           "Türkiye": "Turkey", "Turkiye": "Turkey", "Cabo Verde": "Cape Verde", "Curacao": "Curaçao",
           "DR Congo": "DR Congo", "Congo DR": "DR Congo"}


def norm(name: str) -> str:
    return ALIASES.get(name.strip(), name.strip())


def parse_openfootball() -> pd.DataFrame:
    rows = []
    for y in YEARS:
        d = json.loads((CACHE / f"openfootball_{y}.json").read_text())
        for m in d["matches"]:
            sc = m.get("score")
            if isinstance(sc, list):
                sc = {"ft": sc}
            if not sc or "ft" not in sc:
                continue
            ft, et, pen = sc.get("ft"), sc.get("et"), sc.get("p")
            final = et if et else ft
            t = (m.get("time") or (DEFAULT_TIME_2006 if y == 2006 else None)).strip()
            parts = t.split()
            hhmm = parts[0]
            off = parts[1].replace("UTC", "") if len(parts) > 1 else DEFAULT_OFFSET[y]
            off = off if ":" in off else f"{off[0]}{int(off[1:]):02d}:00"
            kickoff = pd.Timestamp(f"{m['date']} {hhmm}{off}").tz_convert("UTC")
            rows.append({"year": y, "round": m["round"], "date": pd.Timestamp(m["date"]),
                         "team1": norm(m["team1"]), "team2": norm(m["team2"]), "ft1": ft[0], "ft2": ft[1],
                         "g1": final[0], "g2": final[1], "et": bool(et), "p1": pen[0] if pen else None,
                         "p2": pen[1] if pen else None, "kickoff_utc": kickoff, "time_given": m.get("time") is not None})
    df = pd.DataFrame(rows)
    df["knockout"] = df["round"].isin(KNOCKOUT)
    df["pens"] = df["p1"].notna()
    win1 = (df["g1"] > df["g2"]) | (df["pens"] & (df["p1"] > df["p2"]))
    win2 = (df["g2"] > df["g1"]) | (df["pens"] & (df["p2"] > df["p1"]))
    df["winner"] = df["team1"].where(win1, df["team2"].where(win2))
    df["loser"] = df["team2"].where(win1, df["team1"].where(win2))
    minutes = 115 + 35 * df["et"] + 15 * df["pens"]
    df["end_utc"] = df["kickoff_utc"] + pd.to_timedelta(minutes, unit="min")
    return df


def cross_check(of: pd.DataFrame) -> None:
    res = pd.read_csv(CACHE / "martj42_results.csv", parse_dates=["date"])
    so = pd.read_csv(CACHE / "martj42_shootouts.csv", parse_dates=["date"])
    res = res[res["tournament"] == "FIFA World Cup"].copy()
    for c in ["home_team", "away_team"]:
        res[c] = res[c].map(norm)
    so["winner"] = so["winner"].map(norm)
    so["key"] = so.apply(lambda r: (r["date"], frozenset({norm(r["home_team"]), norm(r["away_team"])})), axis=1)
    sow = dict(zip(so["key"], so["winner"]))
    res["key"] = res.apply(lambda r: (r["date"], frozenset({r["home_team"], r["away_team"]})), axis=1)
    rk = {k: row for k, row in zip(res["key"], res.to_dict("records"))}
    problems, matched = [], 0
    for r in of.itertuples():
        key = (r.date, frozenset({r.team1, r.team2}))
        if key not in rk:
            # allow a one-day date difference (time zones), then report
            alt = [k for k in rk if k[1] == key[1] and abs((k[0] - r.date).days) <= 1]
            if not alt:
                problems.append(f"{r.year} {r.round} {r.date.date()} {r.team1}-{r.team2}: not in martj42")
                continue
            key = alt[0]
        x = rk[key]
        g = {x["home_team"]: x["home_score"], x["away_team"]: x["away_score"]}
        if (g.get(r.team1), g.get(r.team2)) != (r.g1, r.g2):
            problems.append(f"{r.year} {r.round} {r.date.date()} {r.team1}-{r.team2}: openfootball {r.g1}-{r.g2}, "
                            f"martj42 {g.get(r.team1)}-{g.get(r.team2)}")
        if r.pens and sow.get(key) != r.winner:
            problems.append(f"{r.year} {r.round} {r.date.date()} {r.team1}-{r.team2}: shootout winner openfootball "
                            f"{r.winner}, martj42 {sow.get(key)}")
        matched += 1
    print(f"cross-check: {matched}/{len(of)} matches found in martj42; disagreements: {len(problems)}")
    for p in problems:
        print("   ", p)


def event_day(end_utc: pd.Timestamp, country: str) -> pd.Timestamp:
    """Local date of the first home session that opens after the match ends."""
    _, tz, open_hm, days = ETF[country]
    end_local = end_utc.tz_convert(tz)
    d = end_local.normalize().tz_localize(None)
    for k in range(0, 10):
        day = d + pd.Timedelta(days=k)
        if day.weekday() in days:
            open_ts = pd.Timestamp(f"{day.date()} {open_hm}").tz_localize(tz)
            if open_ts > end_local:
                return day
    raise RuntimeError("no session found")


def main():
    of = parse_openfootball()
    print("matches per tournament:", of.groupby("year").size().to_dict(),
          "| knockout:", of[of["knockout"]].groupby("year").size().to_dict())
    print("round names:", sorted(of["round"].unique()))
    assert of.loc[of["knockout"], "loser"].notna().all(), "every knockout match must have a loser"
    cross_check(of)
    teams = sorted(set(of["team1"]) | set(of["team2"]))
    print(f"\nteams with a country ETF: {sorted(t for t in teams if t in ETF)}")
    print(f"teams without one (excluded): {sorted(t for t in teams if t not in ETF)}")

    us_days = pd.DatetimeIndex(sorted(pd.to_datetime([b["t"] for b in json.loads((CACHE / 'aggs_SPY.json').read_text())],
                                                     unit="ms").normalize()))
    ev = []
    for m in of.itertuples():
        for side, team, opp in [("loss", m.loser, m.winner), ("win", m.winner, m.loser)]:
            if team is None or pd.isna(team) or team not in ETF:
                continue
            d_home = event_day(m.end_utc, team)
            k = us_days.searchsorted(d_home)
            d_us = us_days[k] if k < len(us_days) else pd.NaT
            ev.append({"year": m.year, "round": m.round, "knockout": m.knockout, "side": side, "team": team,
                       "opponent": opp, "etf": ETF[team][0], "match_date": m.date, "kickoff_utc": m.kickoff_utc,
                       "end_utc": m.end_utc, "et": m.et, "pens": m.pens, "home_session": d_home, "event_date": d_us,
                       "score": f"{m.team1} {m.g1}-{m.g2} {m.team2}" + (f" (p {m.p1}-{m.p2})" if m.pens else "")})
    ev = pd.DataFrame(ev)
    of.to_parquet(CACHE / "matches.parquet", index=False)
    ev.to_parquet(CACHE / "events.parquet", index=False)

    print("\nmapped events by tournament (knockout losses / group losses / all wins):")
    s = ev.groupby("year").apply(lambda g: pd.Series({
        "KO losses": int(((g["side"] == "loss") & g["knockout"]).sum()),
        "group losses": int(((g["side"] == "loss") & ~g["knockout"]).sum()),
        "wins": int((g["side"] == "win").sum())}), include_groups=False)
    print(s.to_string())
    print("\nall knockout losses (timing audit):")
    ko = ev[(ev["side"] == "loss") & ev["knockout"]].sort_values("end_utc")
    for e in ko.itertuples():
        print(f"  {e.year} {e.round:22s} {e.team:13s} {e.etf:8s} {e.score:45s} ends "
              f"{e.end_utc.tz_convert('America/New_York'):%a %Y-%m-%d %H:%M} ET -> home session {e.home_session:%a %m-%d}"
              f" -> US {e.event_date:%a %Y-%m-%d}")


if __name__ == "__main__":
    main()
