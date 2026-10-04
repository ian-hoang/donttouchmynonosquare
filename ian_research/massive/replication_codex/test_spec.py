"""Independent, offline specification audit; no original implementation or data.

Run: PYTHONPATH=massive python3 -m unittest replication_codex.test_spec -v
"""
from datetime import date, datetime, time, timedelta, timezone
from contextlib import redirect_stdout
import io
import json
from math import exp
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from . import pricing
from . import events
from . import report as reporting
from . import trading_calendar as cal

NY = ZoneInfo("America/New_York")


def bar(day, close):
    return {"t": int(datetime.combine(day, time(16), NY).timestamp() * 1000), "c": close}


def sides(strikes):
    return {kind: {k: f"{kind}-{k}" for k in strikes} for kind in ("call", "put")}


class CalendarSpecification(unittest.TestCase):
    def test_holiday_observation_boundaries(self):
        for day in (date(2021, 12, 31), date(2021, 6, 18), date(2024, 11, 29)):
            self.assertTrue(cal.is_session(day), day)
        for day in (date(2023, 1, 2), date(2021, 12, 24), date(2022, 6, 20),
                    date(2025, 1, 9), date(2024, 3, 29), date(2025, 4, 18), date(2026, 4, 3)):
            self.assertFalse(cal.is_session(day), day)

    def test_hand_counted_filing_and_exit_dates(self):
        fixtures = [
            ("2024-03-29", "2024-03-28", "2024-04-01", "2024-04-02", "2024-04-16"),
            ("2025-01-09", "2025-01-08", "2025-01-10", "2025-01-13", "2025-01-28"),
            ("2026-08-31", "2026-08-28", "2026-08-31", "2026-09-01", "2026-09-16"),
        ]
        for filing, pre, filing_session, entry, exit_day in fixtures:
            with self.subTest(filing=filing):
                f = cal.session_on_or_after(date.fromisoformat(filing))
                e = cal.session_after(f)
                self.assertEqual(f.isoformat(), filing_session)
                self.assertEqual(cal.session_before(f).isoformat(), pre)
                self.assertEqual(e.isoformat(), entry)
                self.assertEqual(cal.shift_session(e, 10).isoformat(), exit_day)

    def test_last_completed_session(self):
        self.assertEqual(cal.last_completed_session(datetime(2026, 10, 3, 12, tzinfo=NY)), date(2026, 10, 2))
        self.assertEqual(cal.last_completed_session(datetime(2026, 10, 2, 15, 59, tzinfo=NY)), date(2026, 10, 1))
        self.assertEqual(cal.last_completed_session(datetime(2026, 10, 2, 16, tzinfo=NY)), date(2026, 10, 2))


class EventSpecification(unittest.TestCase):
    def test_literal_universe_has_99_names_despite_heading(self):
        literal = """AAPL ABBV ABT ACN ADBE AIG AMD AMGN AMT AMZN AVGO AXP BA BAC BK BKNG BLK BMY BRK.B C
CAT CHTR CL CMCSA COF COP COST CRM CSCO CVS CVX DE DHR DIS DUK EMR FDX GD GE GILD
GM GOOGL GS HD HON IBM INTC INTU ISRG JNJ JPM KO LIN LLY LMT LOW MA MCD MDLZ MDT
MET META MMM MO MRK MS MSFT NEE NFLX NKE NOW NVDA ORCL PEP PFE PG PLTR PM PYPL QCOM
RTX SBUX SCHW SO T TGT TMO TMUS TSLA TXN UBER UNP UPS USB V VZ WFC WMT XOM"""
        # Comparison uses sets; the frozen list itself contains 99 unique tickers.
        expected = set(literal.split())
        self.assertEqual(len(expected), 99)
        self.assertEqual(set(events.UNIVERSE), expected)
        self.assertEqual(len(events.UNIVERSE), 99)

    def test_union_tags_normalize_and_deduplicate_cik_day(self):
        rows = {
            "acquisition_agreement": [
                {"cik": "123", "filing_date": "2024-01-03", "tickers": ["brk/b", "NOTINUNIVERSE"], "accession_number": "one"},
                {"cik": "123", "filing_date": "2024-01-03", "tickers": ["BRK.B"], "accession_number": "two"},
                {"cik": "124", "filing_date": "2024-01-03", "tickers": ["aapl"]},
                {"cik": "125", "filing_date": "2023-12-31", "tickers": ["MSFT"]},
                {"cik": "125", "filing_date": "2026-09-01", "tickers": ["MSFT"]},
            ],
            "merger_agreement": [{"cik": "0000000123", "filing_date": "2024-01-03", "tickers": ["BRK.B"]}],
        }
        result, ambiguous = events.form_events(rows)
        self.assertEqual(len(result), 2)
        self.assertEqual(ambiguous, [])
        brk = next(row for row in result if row["ticker"] == "BRK.B")
        self.assertEqual(brk["tags"], ["acquisition_agreement", "merger_agreement"])
        self.assertEqual(brk["accessions"], ["one", "two"])

    def test_cooldown_strict_sixty_days_and_only_last_kept(self):
        dates = ["2024-01-01", "2024-03-01", "2024-03-02", "2024-04-30", "2024-05-02"]
        rows = [dict(ticker="AAPL", filing_date=day, cik="1") for day in reversed(dates)]
        kept, dropped = events.cooldown(rows)
        self.assertEqual([row["filing_date"] for row in kept], ["2024-01-01", "2024-03-02", "2024-05-02"])
        self.assertEqual([row["filing_date"] for row in dropped], ["2024-03-01", "2024-04-30"])

    def test_cooldown_does_not_reset_for_2026(self):
        rows = [dict(ticker="AAPL", filing_date=day, cik="1") for day in ("2025-11-15", "2026-01-14", "2026-01-15")]
        kept, dropped = events.cooldown(rows)
        self.assertEqual([row["filing_date"] for row in kept], ["2025-11-15", "2026-01-15"])
        self.assertEqual(dropped[0]["last_kept"], "2025-11-15")

    def test_peer_exclusion_includes_both_fifth_days(self):
        histories = {ticker: [] for ticker in events.UNIVERSE}
        histories.update({"AAPL": ["2024-01-05"], "MSFT": ["2024-01-15"], "ABBV": ["2024-01-04"], "ABT": ["2024-01-16"]})
        # Two event tickers on one filing date intentionally share one basket.
        cohorts = [dict(filing_date="2024-01-10", ticker=ticker) for ticker in ("AAPL", "MSFT")]
        draws, eligible = events.draw_peers(cohorts, histories)
        self.assertEqual(len(draws), 20)
        self.assertNotIn("AAPL", eligible["2024-01-10"])
        self.assertNotIn("MSFT", eligible["2024-01-10"])
        self.assertIn("ABBV", eligible["2024-01-10"])
        self.assertIn("ABT", eligible["2024-01-10"])
        for draw in draws:
            self.assertEqual(len(set(draw["tickers"])), 6)
            self.assertTrue(set(draw["tickers"]).issubset(eligible["2024-01-10"]))

    def test_peer_history_fetches_both_brk_spellings_and_boundary_dates(self):
        with patch.object(events.data, "get_all", return_value=[]) as get_all:
            events.fetch_one_history("BRK.B")
        self.assertEqual(get_all.call_count, 2)
        arguments = [call.args[1] for call in get_all.call_args_list]
        self.assertEqual({args["tickers"] for args in arguments}, {"BRK.B", "BRK/B"})
        for args in arguments:
            self.assertEqual(args["filing_date.gte"], "2023-12-27")
            self.assertEqual(args["filing_date.lte"], "2026-09-05")
            self.assertNotIn("tertiary_category", args)


class MarkSpecification(unittest.TestCase):
    def test_timestamp_uses_new_york_date(self):
        timestamp = int(datetime(2024, 7, 5, 0, 30, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(pricing.bar_date({"t": timestamp}), date(2024, 7, 4))

    def test_freshness_counts_three_sessions_not_calendar_days(self):
        # Thu before Good Friday -> Mon, Tue, Wed = exactly 3 sessions.
        values = [pricing.BarMark(2.0, date(2024, 3, 28))]
        self.assertIsNotNone(pricing.mark(values, date(2024, 4, 3)))
        self.assertIsNone(pricing.mark(values, date(2024, 4, 4)))

    def test_future_bars_cannot_rescue_missing_mark(self):
        self.assertIsNone(pricing.mark([pricing.BarMark(2.0, date(2024, 4, 4))], date(2024, 4, 3)))

    def test_latest_eligible_bar_is_selected(self):
        values = [pricing.BarMark(4.0, date(2024, 4, 3)), pricing.BarMark(3.0, date(2024, 4, 2)),
                  pricing.BarMark(5.0, date(2024, 4, 4))]
        self.assertEqual(pricing.mark(values, date(2024, 4, 3)).close, 4.0)


class SelectionSpecification(unittest.TestCase):
    def test_nearest_expiry_not_replaced_when_too_few_pairs(self):
        day = date(2024, 1, 2)
        chain = {day + timedelta(days=3): sides([90, 100]), day + timedelta(days=7): sides([90, 100, 110])}
        result = pricing.estimate_spot(chain, day, object())
        self.assertIsNone(result["spot"])
        self.assertEqual(result["drop_reason"], "near_expiry_fewer_than_3_pairs")

    def test_spot_calendar_lookback_is_separate_from_main_mark(self):
        pre = date(2024, 4, 12)
        expiry = date(2024, 4, 19)
        old = date(2024, 4, 5)  # pre-7, five sessions old, valid for spot only.
        discount = exp(-0.04 * 7 / 365)
        class Client:
            def bars(self, contract, start, end):
                close = 5 if contract == "call-100" else 100 * discount + 5 - 100
                return [bar(old, close)]
        result = pricing.estimate_spot({expiry: sides([90, 100, 110])}, pre, Client())
        self.assertAlmostEqual(result["spot"], 100)
        self.assertIsNone(pricing.mark([pricing.BarMark(5, old)], pre))

    def test_missing_spot_strike_moves_to_nearest_untried(self):
        pre = date(2024, 4, 12)
        expiry = date(2024, 4, 19)
        discount = exp(-0.04 * 7 / 365)
        class Client:
            def bars(self, contract, start, end):
                kind, raw_strike = contract.split("-")
                strike = float(raw_strike)
                if strike == 110:
                    return []
                estimate = 108 if strike == 100 else 100
                put = 20.0
                close = estimate - strike * discount + put if kind == "call" else put
                return [bar(pre, close)]
        result = pricing.estimate_spot({expiry: sides([80, 90, 100, 110, 120])}, pre, Client())
        self.assertEqual([attempt["strike"] for attempt in result["attempts"]], [100, 110, 120])
        self.assertAlmostEqual(result["spot"], 100)

    def test_sold_call_need_not_have_matching_put(self):
        pre = date(2024, 1, 2)
        expiry = pre + timedelta(days=120)
        pair = sides([90, 100, 110])
        pair["call"][105] = "unpaired-call-105"
        result = pricing.select_expiry_and_strikes({expiry: pair}, pre, 100)
        self.assertEqual(result["strike"], 105)
        self.assertEqual(result["atm_strike"], 100)

    def test_expiry_bounds_and_ties(self):
        pre = date(2024, 1, 2)
        chain = {pre + timedelta(days=d): sides([90, 100, 110]) for d in (89, 110, 130, 181)}
        result = pricing.select_expiry_and_strikes(chain, pre, 100)
        self.assertEqual(result["expiry"], (pre + timedelta(days=110)).isoformat())


class SyntheticClient:
    """Complete synthetic trade yielding 1% gross less 0.4% spread cost."""
    pre = date(2024, 3, 28)
    entry = date(2024, 4, 2)
    exit_day = date(2024, 4, 16)
    near = date(2024, 4, 5)
    expiry = date(2024, 7, 26)

    def __init__(self, missing_exit_stock=False, quote_overrides=None):
        self.missing_exit_stock = missing_exit_stock
        self.quote_overrides = quote_overrides or {}
        self.quote_calls = []

    def chain(self, ticker, as_of):
        assert as_of == self.pre
        result = []
        for prefix, expiration, strikes in (("N", self.near, [90, 100, 110]), ("L", self.expiry, [90, 100, 105, 110])):
            for strike in strikes:
                for kind in ("call", "put"):
                    if strike == 105 and kind == "put":
                        continue
                    result.append({"contract_type": kind, "expiration_date": str(expiration),
                                   "strike_price": strike, "ticker": f"{prefix}-{kind}-{strike}"})
        return result

    def bars(self, contract, start, end):
        prefix, kind, raw_strike = contract.split("-")
        strike = float(raw_strike)
        if prefix == "N":
            discount = exp(-0.04 * (self.near - self.pre).days / 365)
            call = max(100 - strike * discount, 0) + 5
            put = max(strike * discount - 100, 0) + 5
            return [bar(self.pre, call if kind == "call" else put)]
        if strike == 105:
            return [bar(self.entry, 2.0), bar(self.exit_day, 1.0)]
        result = []
        for day in (self.pre, self.entry, self.exit_day):
            if self.missing_exit_stock and kind == "put" and day == self.exit_day:
                continue
            put = strike * exp(-0.04 * (self.expiry - day).days / 365) + 10 - 100
            result.append(bar(day, 10 if kind == "call" else put))
        return result

    def get_json(self, path, params):
        self.quote_calls.append((path, params))
        quote = {"sip_timestamp": int(datetime.combine(self.entry, time(16), NY).timestamp() * 1_000_000_000),
                 "bid_price": 1.8, "ask_price": 2.2}
        quote.update(self.quote_overrides)
        return {"results": [quote]}


class WholeTradeSpecification(unittest.TestCase):
    def run_trade(self, client):
        return pricing.price_trade("TEST", date(2024, 3, 29), client=client, completed_session=date(2026, 10, 2))

    def test_full_trade_cost_and_dates(self):
        client = SyntheticClient()
        result = self.run_trade(client)
        self.assertEqual(result["status"], "valid", result)
        self.assertEqual((result["entry"], result["exit"]), ("2024-04-02", "2024-04-16"))
        self.assertAlmostEqual(result["gross"], 0.01)
        self.assertAlmostEqual(result["cost"], 0.004)
        self.assertAlmostEqual(result["net"], 0.006)
        self.assertEqual(client.quote_calls[0][1]["timestamp.lte"], "2024-04-02T20:00:00Z")

    def test_exit_stock_price_required_even_when_sold_call_exists(self):
        client = SyntheticClient(missing_exit_stock=True)
        result = self.run_trade(client)
        self.assertEqual(result["drop_reason"], "missing_exit_stock_price")
        self.assertEqual(client.quote_calls, [])

    def test_crossed_last_quote_is_rejected(self):
        client = SyntheticClient(quote_overrides={"bid_price": 2.2, "ask_price": 1.8})
        result = self.run_trade(client)
        self.assertEqual(result["drop_reason"], "invalid_entry_quote_prices")
        self.assertEqual(len(client.quote_calls), 1)

    def test_previous_day_quote_is_rejected(self):
        old_quote = int(datetime(2024, 4, 1, 16, tzinfo=NY).timestamp() * 1_000_000_000)
        result = self.run_trade(SyntheticClient(quote_overrides={"sip_timestamp": old_quote}))
        self.assertEqual(result["drop_reason"], "entry_quote_not_same_day_at_or_before_close")

    def test_exit_beyond_completed_session_is_rejected(self):
        result = pricing.price_trade("TEST", date(2024, 3, 29), client=SyntheticClient(), completed_session=date(2024, 4, 15))
        self.assertEqual(result["drop_reason"], "exit_not_completed")


class ReportSpecification(unittest.TestCase):
    def test_metrics_sample_std_strict_win_and_unannualized_sharpe(self):
        result = reporting.metrics([-0.02, 0.01, 0.04])
        self.assertAlmostEqual(result["mean"], 0.01)
        self.assertAlmostEqual(result["median"], 0.01)
        self.assertAlmostEqual(result["std"], 0.03)
        self.assertAlmostEqual(result["per_trade_sharpe"], 1 / 3)
        self.assertAlmostEqual(result["win_rate"], 2 / 3)
        self.assertEqual(reporting.metrics([0.0])["win_rate"], 0)
        self.assertIsNone(reporting.metrics([0.01])["std"])
        self.assertIsNone(reporting.metrics([])["mean"])

    @staticmethod
    def trade(ticker, filing, net):
        day = date.fromisoformat(filing)
        return dict(ticker=ticker, filing_date=filing, net=net, status="valid", drop_reason=None,
                    entry=str(day + timedelta(days=1)), exit=str(day + timedelta(days=15)),
                    expiry=str(day + timedelta(days=120)), strike=100)

    def generate_report(self, trades):
        cache_root = Path(__file__).resolve().parent / "cache"
        cache_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="spec-report-", dir=cache_root) as directory:
            dest = Path(directory)
            peer_rows = []
            draws = []
            dates = sorted({t["filing_date"] for t in trades})
            for day in dates:
                for ticker in ("ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT"):
                    has_price = ticker in {"ABBV", "ABT", "AMGN"} and day != "2024-01-11"
                    peer_rows.append(dict(ticker=ticker, filing_date=day, status="valid" if has_price else "dropped",
                                          net={"ABBV": 0, "ABT": 0.02, "AMGN": 0.04}.get(ticker)))
            for seed in range(20):
                for day in dates:
                    basket = ["ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD"] if seed < 10 else ["AMGN", "AMT", "ACN", "ADBE", "AIG", "AMD"]
                    draws.append(dict(seed=seed, filing_date=day, tickers=basket))
            cohort_rows = [dict(ticker=t["ticker"], cik=str(i), filing_date=t["filing_date"], window=events.window(t["filing_date"]))
                           for i, t in enumerate(trades)]
            cohort = dict(before=cohort_rows, kept=cohort_rows, cooldown_drops=[], ambiguous_cik_days=[], raw_counts={})
            for name, payload in (("cohort.json", cohort), ("event_results.json", trades), ("peer_results.json", peer_rows),
                                  ("peer_draws.json", draws), ("run_manifest.json", {})):
                (dest / name).write_text(json.dumps(payload))
            with patch.object(reporting.data, "CACHE", dest), patch.object(reporting, "HERE", dest), redirect_stdout(io.StringIO()):
                reporting.report()
            return json.loads((dest / "independent_summary.json").read_text())

    def test_report_weights_events_and_seeds_with_missing_peers(self):
        summary = self.generate_report([
            self.trade("AAPL", "2024-01-10", 0.03), self.trade("MSFT", "2024-01-10", 0.01),
            self.trade("GILD", "2024-01-11", 0.05), self.trade("AAPL", "2026-01-10", -0.02),
            self.trade("MSFT", "2026-01-10", 0.02),
        ])
        insample = summary["2024-25"]
        self.assertEqual(insample["n"], 3)
        self.assertAlmostEqual(insample["mean"], 0.03)
        self.assertAlmostEqual(insample["peer_gap_mean_across_seeds"], -0.005)
        self.assertAlmostEqual(insample["peer_gap_min"], -0.02)
        self.assertAlmostEqual(insample["peer_gap_max"], 0.01)
        self.assertEqual(insample["seeds"][0]["paired_events"], 2)
        self.assertEqual(insample["seeds"][0]["missing_events"], 1)
        self.assertAlmostEqual(insample["seeds"][0]["mean_valid_peers"], 4 / 3)
        self.assertAlmostEqual(insample["seeds"][10]["mean_valid_peers"], 2 / 3)
        self.assertAlmostEqual(summary["2026"]["peer_gap_mean_across_seeds"], -0.025)

    def test_report_handles_empty_and_single_trade_windows(self):
        summary = self.generate_report([self.trade("AAPL", "2024-01-10", 0.03)])
        self.assertEqual(summary["2024-25"]["n"], 1)
        self.assertIsNone(summary["2024-25"]["per_trade_sharpe"])
        self.assertEqual(summary["2026"]["n"], 0)


if __name__ == "__main__":
    unittest.main()
