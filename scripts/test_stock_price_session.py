import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from stock_price_session import evaluate_price_session, load_and_evaluate, main, verify_wrapper


def bar(stamp, close):
    return {"cntr_tm": stamp, "cur_prc": str(close), "open_pric": str(close),
            "high_pric": str(close), "low_pric": str(close), "trde_qty": "10"}


def fixtures(base=24400, final=24600, code="086450"):
    chart = {"fetched_at": "2026-11-19T15:09:23+09:00",
             "basic": {"stk_cd": code, "base_pric": str(base), "return_code": 0},
             "basic_request": {"stk_cd": code},
             "daily_request": {"stk_cd": code, "base_dt": "20261119", "upd_stkpc_tp": "1"},
             "rows": []}
    for date, close in [("20261119", 26600), ("20261118", final)]:
        row = bar(date + "000000", close)
        row.pop("cntr_tm")
        row.update(dt=date, upd_stkpc_tp="", upd_rt="")
        chart["rows"].append(row)
    minute = {"api_id": "ka10080", "fetched_at": "2026-11-20T21:15:59+09:00",
              "request": {"stk_cd": code, "tic_scope": "5", "upd_stkpc_tp": "0"},
              "response": {"stk_cd": code, "return_code": 0, "stk_min_pole_chart_qry": [
                  bar("20261118195500", final), bar("20261118153000", base)]}}
    return chart, minute


def evaluate(chart, minute, **overrides):
    args = {"trade_date": "20261119", "previous_date": "20261118", "regular_close": "153000",
            "checked_at": "2026-11-20T22:00:00+09:00"}
    args.update(overrides)
    return evaluate_price_session(chart, minute, **args)


class PriceSessionTests(unittest.TestCase):
    def test_null_nested_source_objects_are_unresolved(self):
        for target, key in [('chart', 'basic'), ('minute', 'request'), ('minute', 'response')]:
            with self.subTest(key=key):
                chart, minute = fixtures()
                (chart if target == 'chart' else minute)[key] = None
                self.assertEqual(evaluate(chart, minute)['status'], 'UNRESOLVED')

    def assert_issue(self, result, code):
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertFalse(result["can_use_completed_history"])
        self.assertEqual(result["issues"][0]["code"], code)

    def test_two_real_price_regressions_are_session_differences(self):
        for base, final, code in [(24400, 24600, "086450"), (42150, 47000, "035760")]:
            with self.subTest(code=code):
                result = evaluate(*fixtures(base, final, code))
                self.assertEqual(result["status"], "SESSION_DIFFERENCE_CONFIRMED")
                self.assertTrue(result["can_use_completed_history"])
                self.assertTrue(result["intraday_provisional"])
                self.assertFalse(result["current_day_completion_verified"])
                self.assertFalse(result["recommendation_approved"])
                self.assertFalse(result["full_history_validation_passed"])

    def test_equal_prices_still_require_boundary_evidence(self):
        chart, minute = fixtures(24400, 24400)
        self.assertEqual(evaluate(chart, minute)["status"], "CONSISTENT")
        minute["response"]["stk_min_pole_chart_qry"].pop()
        self.assert_issue(evaluate(chart, minute), "REGULAR_CLOSE_BAR_MISSING")

    def test_equal_regular_prices_do_not_need_untraded_final_interval(self):
        chart, minute = fixtures(24400, 24400)
        minute["response"]["stk_min_pole_chart_qry"][0]["cntr_tm"] = "20261118195000"
        result = evaluate(chart, minute)
        self.assertEqual(result["status"], "CONSISTENT")
        self.assertFalse(result["aftermarket_completion_verified"])
        self.assertFalse(result["current_day_completion_verified"])
        self.assertFalse(result["recommendation_approved"])

    def test_equal_daily_reference_does_not_hide_conflicting_aftermarket_bar(self):
        chart, minute = fixtures(24400, 24400)
        minute["response"]["stk_min_pole_chart_qry"][0] = bar("20261118195500", 25000)
        self.assert_issue(evaluate(chart, minute), "DAILY_AFTERMARKET_CLOSE_MISMATCH")

    def test_missing_final_interval_is_not_assumed_inactive(self):
        chart, minute = fixtures()
        minute["response"]["stk_min_pole_chart_qry"][0]["cntr_tm"] = "20261118195000"
        self.assert_issue(evaluate(chart, minute), "AFTERMARKET_CLOSE_BAR_MISSING")

    def test_wrong_regular_close_requires_exact_boundary(self):
        self.assert_issue(evaluate(*fixtures(), regular_close="163000"), "REGULAR_CLOSE_BAR_MISSING")

    def test_unsupported_regular_boundary_cannot_be_invented(self):
        self.assert_issue(evaluate(*fixtures(), regular_close="000000"), "UNSUPPORTED_REGULAR_CLOSE")

    def test_calendar_and_request_provenance_are_not_overclaimed(self):
        result = evaluate(*fixtures())
        self.assertFalse(result["calendar_verified"])
        self.assertIn("NOT_CALENDAR_VERIFIED", result["regular_close_provenance"])
        self.assertIn("NOT_INDEPENDENTLY_VERIFIED", result["request_metadata_provenance"])

    def test_csat_regular_boundary_is_explicit(self):
        chart, minute = fixtures()
        chart["fetched_at"] = "2026-11-20T15:00:00+09:00"
        chart["daily_request"]["base_dt"] = "20261120"
        for row in chart["rows"]:
            row["dt"] = "20261120" if row["dt"] == "20261119" else "20261119"
        for row in minute["response"]["stk_min_pole_chart_qry"]:
            row["cntr_tm"] = "20261119" + ("163000" if row["cntr_tm"].endswith("153000") else "195500")
        result = evaluate(chart, minute, trade_date="20261120", previous_date="20261119", regular_close="163000")
        self.assertEqual(result["status"], "SESSION_DIFFERENCE_CONFIRMED")

    def test_source_errors_are_not_relaxed(self):
        chart, minute = fixtures()
        chart["basic"]["base_pric"] = "24500"
        self.assert_issue(evaluate(chart, minute), "REFERENCE_REGULAR_CLOSE_MISMATCH")
        chart, minute = fixtures()
        chart["rows"][1].update(cur_prc="24700", high_pric="24700")
        self.assert_issue(evaluate(chart, minute), "DAILY_AFTERMARKET_CLOSE_MISMATCH")

    def test_market_and_symbol_are_not_interchangeable(self):
        for key, value in [("stk_cd", "086450_NX"), ("stk_cd", "035760")]:
            chart, minute = fixtures()
            minute["request"][key] = value
            self.assert_issue(evaluate(chart, minute), "MARKET_OR_CODE_MISMATCH")

    def test_missing_request_metadata_is_unresolved(self):
        chart, minute = fixtures()
        del chart["daily_request"]
        self.assert_issue(evaluate(chart, minute), "MISSING_REQUEST_METADATA")

    def test_adjustment_event_blocks_raw_adjusted_comparison(self):
        for field, value in [("upd_stkpc_tp", "8"), ("upd_rt", "-50.00")]:
            chart, minute = fixtures()
            chart["rows"][1][field] = value
            self.assert_issue(evaluate(chart, minute), "ADJUSTMENT_REQUIRES_RECONCILIATION")

    def test_duplicates_and_bad_ohlc_are_rejected(self):
        chart, minute = fixtures()
        chart["rows"].append(copy.deepcopy(chart["rows"][0]))
        self.assert_issue(evaluate(chart, minute), "DUPLICATE_DAILY_DATE")
        chart, minute = fixtures()
        minute["response"]["stk_min_pole_chart_qry"].append(copy.deepcopy(minute["response"]["stk_min_pole_chart_qry"][0]))
        self.assert_issue(evaluate(chart, minute), "DUPLICATE_INTRADAY_TIME")
        chart, minute = fixtures()
        chart["rows"][1]["low_pric"] = "99999"
        self.assert_issue(evaluate(chart, minute), "INVALID_OHLC")

    def test_dates_and_fetch_times_are_checked(self):
        chart, minute = fixtures()
        self.assert_issue(evaluate(chart, minute, previous_date="20261117"), "PREVIOUS_DATE_MISMATCH")
        chart["fetched_at"] = "2026-11-18T19:00:00+09:00"
        self.assert_issue(evaluate(chart, minute), "BASIC_REFERENCE_DATE_UNVERIFIED")
        chart, minute = fixtures()
        minute["fetched_at"] = "2026-11-18T19:00:00+09:00"
        self.assert_issue(evaluate(chart, minute), "PREVIOUS_SESSION_NOT_FINISHED")
        chart, minute = fixtures()
        minute["fetched_at"] = "2026-11-20T21:15:59"
        self.assert_issue(evaluate(chart, minute), "NAIVE_FETCH_TIME")
        chart, minute = fixtures()
        self.assert_issue(evaluate(chart, minute, checked_at="2026-11-20T20:00:00+09:00"), "FUTURE_COLLECTION")

    def test_future_intraday_row_is_rejected(self):
        chart, minute = fixtures()
        minute["response"]["stk_min_pole_chart_qry"].append(bar("20261123100000", 24400))
        self.assert_issue(evaluate(chart, minute), "FUTURE_BAR")

    def test_nonfinite_prices_are_rejected(self):
        chart, minute = fixtures()
        chart["basic"]["base_pric"] = "NaN"
        self.assert_issue(evaluate(chart, minute), "INVALID_NUMBER")

    def test_negative_volume_is_not_a_directional_price_sign(self):
        chart, minute = fixtures()
        minute["response"]["stk_min_pole_chart_qry"][0]["trde_qty"] = "-10"
        self.assert_issue(evaluate(chart, minute), "INVALID_NUMBER")

    def test_untraded_boundary_is_not_an_observed_close(self):
        for i, code in [(0, "AFTERMARKET_CLOSE_NOT_TRADED"), (1, "REGULAR_CLOSE_NOT_TRADED")]:
            chart, minute = fixtures()
            minute["response"]["stk_min_pole_chart_qry"][i]["trde_qty"] = "0"
            self.assert_issue(evaluate(chart, minute), code)

    def test_legacy_wrapper_preserves_original_and_hashes(self):
        chart, _ = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            original = Path(tmp) / "raw.json"
            generator = Path(tmp) / "collector.py"
            original.write_text(json.dumps({k: chart[k] for k in ("fetched_at", "basic", "rows")}), encoding="utf-8")
            generator.write_text("# inspected collector\n", encoding="utf-8")
            for key, path in [("source_raw", original), ("request_evidence", generator)]:
                chart[key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            self.assertEqual(len(verify_wrapper(chart)), 2)
            chart["basic"]["base_pric"] = "1"
            with self.assertRaisesRegex(ValueError, "changes original"):
                verify_wrapper(chart)

    def test_loader_rejects_changed_legacy_hash(self):
        chart, minute = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "source.json"
            original.write_text(json.dumps(chart), encoding="utf-8")
            chart["source_raw"] = {"path": str(original), "sha256": "0" * 64}
            (root / "chart.json").write_text(json.dumps(chart), encoding="utf-8")
            (root / "minute.json").write_text(json.dumps(minute), encoding="utf-8")
            result = load_and_evaluate(root / "chart.json", root / "minute.json", trade_date="20261119",
                                       previous_date="20261118", regular_close="153000")
            self.assert_issue(result, "LEGACY_REFERENCE_HASH_MISMATCH")

    def test_cli_success_and_unresolved_exit_codes(self):
        chart, minute = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "chart.json").write_text(json.dumps(chart), encoding="utf-8")
            (root / "minute.json").write_text(json.dumps(minute), encoding="utf-8")
            args = ["--chart-raw", str(root / "chart.json"), "--intraday-raw", str(root / "minute.json"),
                    "--trade-date", "20261119", "--previous-date", "20261118", "--regular-close", "153000",
                    "--output", str(root / "result.json")]
            self.assertEqual(main(args), 0)
            result = json.loads((root / "result.json").read_text(encoding="utf-8"))
            self.assertTrue(result["input_files"])
            minute["response"]["stk_min_pole_chart_qry"].pop()
            (root / "minute.json").write_text(json.dumps(minute), encoding="utf-8")
            self.assertEqual(main(args), 2)

    def test_cli_cannot_overwrite_inputs_or_legacy_evidence(self):
        chart, minute = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, generator = root / "original.json", root / "collector.py"
            original.write_text(json.dumps(chart), encoding="utf-8")
            generator.write_text("# original evidence\n", encoding="utf-8")
            for key, path in [("source_raw", original), ("request_evidence", generator)]:
                chart[key] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            chart_path, minute_path = root / "chart.json", root / "minute.json"
            chart_path.write_text(json.dumps(chart), encoding="utf-8")
            minute_path.write_text(json.dumps(minute), encoding="utf-8")
            args = ["--chart-raw", str(chart_path), "--intraday-raw", str(minute_path),
                    "--trade-date", "20261119", "--previous-date", "20261118", "--regular-close", "153000"]
            for path in (chart_path, minute_path, original, generator):
                before = path.read_bytes()
                self.assertEqual(main(args + ["--output", str(path)]), 2)
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
