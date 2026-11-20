"""Reconcile a KRX reference price with dated regular/aftermarket bars.

This is a diagnostic boundary check, not stock selection or full history QA.
It never collects prices, changes a source, publishes, or sends a message.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sys

KST = timezone(timedelta(hours=9))
VERSION = "2026-11-20-session-boundary-v1"
OFFICIAL_CHART_NOTICE = "https://evt.kiwoom.com/e/home/event/VEvent20260093View?from=012"


class EvidenceError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code, self.detail = code, detail
        super().__init__(detail)


def require(condition, code, detail):
    if not condition:
        raise EvidenceError(code, detail)


def date_text(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{8}", value), "INVALID_DATE", str(value))
    return datetime.strptime(value, "%Y%m%d").date()


def instant(value):
    require(isinstance(value, str), "INVALID_FETCH_TIME", "fetched_at must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            "NAIVE_FETCH_TIME", "Timezone-aware collection evidence is required")
    return parsed.astimezone(KST)


def number(value, *, positive=True, directional=True):
    require(not isinstance(value, bool) and value is not None, "INVALID_NUMBER", "Missing/bool numeric value")
    try:
        text = str(value).strip().replace(",", "")
        require(bool(text), "INVALID_NUMBER", "Empty numeric value")
        result = Decimal(text)
        if directional:
            result = abs(result)  # Kiwoom price signs describe direction.
    except InvalidOperation as exc:
        raise EvidenceError("INVALID_NUMBER", "Invalid price or volume") from exc
    require(result.is_finite() and (result > 0 if positive else result >= 0),
            "INVALID_NUMBER", "Non-finite/nonpositive price or invalid volume")
    return result


def ohlcv(row):
    prices = {key: number(row.get(key)) for key in ("open_pric", "high_pric", "low_pric", "cur_prc")}
    require(prices["high_pric"] >= max(prices.values()) and prices["low_pric"] <= min(prices.values()),
            "INVALID_OHLC", "OHLC values are outside the declared range")
    number(row.get("trde_qty"), positive=False, directional=False)
    if "trde_prica" in row:
        number(row["trde_prica"], positive=False, directional=False)
    return prices


def has_adjustment(row):
    flag = str(row.get("upd_stkpc_tp", "")).strip()
    rate = str(row.get("upd_rt", "")).strip()
    return flag not in ("", "0") or rate not in ("", "0", "0.0", "0.00")


def payload_sha(value):
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def evaluate_price_session(chart_raw, intraday_raw, *, trade_date, previous_date,
                           regular_close, checked_at=None):
    """Explain only the declared previous-day KRX closing-price boundary.

    Requests must be captured in the input. A legacy wrapper may additionally
    carry source_raw/request_evidence references, verified by the CLI. Internal
    gaps can represent no trades; no complete-history approval is inferred.
    """
    result = {
        "policy_version": VERSION, "status": "UNRESOLVED", "issues": [],
        "trade_date": trade_date, "previous_date": previous_date,
        "regular_close": regular_close, "market": "KRX",
        "can_use_completed_history": False,
        "completed_history_scope": "Only the declared previous-day closing-price boundary; not the entire series",
        "intraday_provisional": None, "current_day_completion_verified": False,
        "recommendation_approved": False, "full_history_validation_passed": False,
        "independent_exchange_price_verified": False,
        "internal_bar_grid_completeness_verified": False,
        "aftermarket_completion_verified": False, "session_calendar_verified": False,
        "calendar_verified": False,
        "regular_close_provenance": "CALLER_SUPPLIED_SUPPORTED_TIME_NOT_CALENDAR_VERIFIED",
        "scope_note": "Different sessions may have different valid closes. This check does not select stocks or approve publication.",
        "official_chart_notice": OFFICIAL_CHART_NOTICE,
    }
    try:
        require(isinstance(chart_raw, dict) and isinstance(intraday_raw, dict), "INVALID_INPUT", "Objects required")
        result["input_payload_sha256"] = {"chart": payload_sha(chart_raw), "intraday": payload_sha(intraday_raw)}
        trade, prior = date_text(trade_date), date_text(previous_date)
        require(prior < trade, "INVALID_DATE_ORDER", "previous_date must precede trade_date")
        require(isinstance(regular_close, str) and re.fullmatch(r"\d{6}", regular_close),
                "INVALID_REGULAR_CLOSE", "Explicit HHMMSS regular close is required")
        require(regular_close in ("153000", "163000"), "UNSUPPORTED_REGULAR_CLOSE",
                "Only 15:30 and 16:30 are supported; other calendars need an explicit policy extension")
        close_clock = datetime.strptime(regular_close, "%H%M%S").time()
        require(close_clock.second == 0 and close_clock.minute % 5 == 0 and close_clock.hour < 20,
                "INVALID_REGULAR_CLOSE", "Regular boundary must align to a 5-minute bar before 20:00")

        basic = chart_raw.get("basic", {})
        require(isinstance(basic, dict), "INVALID_BASIC_OBJECT", "Basic source must be an object")
        code = basic.get("stk_cd")
        require(isinstance(code, str) and re.fullmatch(r"\d{6}", code),
                "UNSUPPORTED_MARKET", "This comparison requires an explicit six-digit KRX code")
        result["code"] = code
        basic_request, daily_request = chart_raw.get("basic_request"), chart_raw.get("daily_request")
        require(isinstance(basic_request, dict) and isinstance(daily_request, dict),
                "MISSING_REQUEST_METADATA", "Capture basic_request and daily_request; do not infer market from the price")
        require(basic_request.get("stk_cd") == code and daily_request.get("stk_cd") == code,
                "MARKET_OR_CODE_MISMATCH", "Basic/daily request codes must match the KRX response code")
        require(daily_request.get("base_dt") == trade_date,
                "REQUEST_DATE_MISMATCH", "Daily request date does not match the declared snapshot")
        require(str(daily_request.get("upd_stkpc_tp")) in ("0", "1"),
                "UNKNOWN_ADJUSTMENT_MODE", "Daily adjusted/unadjusted request mode is required")
        request_evidence = chart_raw.get("request_evidence")
        result["request_metadata_provenance"] = (
            "COLLECTOR_CODE_REVIEW_NOT_CAPTURED_HTTP" if "source_raw" in chart_raw
            else "REQUEST_FIELDS_IN_SOURCE_NOT_INDEPENDENTLY_VERIFIED")
        if isinstance(request_evidence, dict):
            result["request_evidence_kind"] = request_evidence.get("kind")
        require(basic.get("return_code") in (None, 0, "0"), "SOURCE_API_FAILURE", "Basic request failed")

        chart_time, minute_time = instant(chart_raw.get("fetched_at")), instant(intraday_raw.get("fetched_at"))
        end = datetime.combine(prior, datetime.strptime("200000", "%H%M%S").time(), KST)
        require(chart_time.date() == trade, "BASIC_REFERENCE_DATE_UNVERIFIED", "The undated basic reference must be collected on trade_date")
        require(chart_time > end and minute_time > end,
                "PREVIOUS_SESSION_NOT_FINISHED", "Both observations must follow the previous day's 20:00 close")
        if checked_at is not None:
            check_time = instant(checked_at)
            require(max(chart_time, minute_time) <= check_time, "FUTURE_COLLECTION", "Source collection is later than the diagnostic time")
            result["checked_at"] = check_time.isoformat()
        result["source_fetched_at"] = {"chart": chart_time.isoformat(), "intraday": minute_time.isoformat()}
        result["intraday_provisional"] = chart_time.time() < datetime.strptime("200000", "%H%M%S").time()
        result["current_day_snapshot_status"] = ("INTRADAY_PROVISIONAL" if result["intraday_provisional"]
                                                   else "CURRENT_DAY_COMPLETION_NOT_VERIFIED")

        rows = chart_raw.get("rows")
        require(isinstance(rows, list) and len(rows) >= 2 and all(isinstance(r, dict) for r in rows),
                "MISSING_DAILY_ROWS", "At least the prior and current dated daily observations are required")
        dates = [r.get("dt") for r in rows]
        parsed_dates = [date_text(d) for d in dates]
        require(len(dates) == len(set(dates)), "DUPLICATE_DAILY_DATE", "Duplicate daily dates")
        require(max(parsed_dates) == trade and all(d <= chart_time.date() for d in parsed_dates),
                "DAILY_DATE_MISMATCH", "Daily rows contain a missing current date or a future date")
        before = [d for d in dates if d < trade_date]
        require(bool(before) and max(before) == previous_date,
                "PREVIOUS_DATE_MISMATCH", "The declared previous date is not the latest completed daily row")
        for row in rows:
            ohlcv(row)
        previous = next(r for r in rows if r["dt"] == previous_date)
        current = next(r for r in rows if r["dt"] == trade_date)
        require(not has_adjustment(previous) and not has_adjustment(current),
                "ADJUSTMENT_REQUIRES_RECONCILIATION", "Rights/price adjustment near the comparison boundary needs separate evidence")

        req, response = intraday_raw.get("request", {}), intraday_raw.get("response", {})
        require(isinstance(req, dict) and isinstance(response, dict),
                "INVALID_INTRADAY_OBJECT", "Intraday request and response must be objects")
        require(intraday_raw.get("api_id") == "ka10080", "UNEXPECTED_INTRADAY_API", "Expected ka10080 source evidence")
        require(req.get("stk_cd") == code and response.get("stk_cd") == code,
                "MARKET_OR_CODE_MISMATCH", "Intraday KRX request and response codes must match the daily source")
        require(str(req.get("tic_scope")) == "5" and str(req.get("upd_stkpc_tp")) == "0",
                "INTRADAY_MODE_MISMATCH", "Expected unadjusted five-minute evidence")
        require(response.get("return_code") in (None, 0, "0"), "SOURCE_API_FAILURE", "Intraday request failed")
        minute_rows = response.get("stk_min_pole_chart_qry")
        require(isinstance(minute_rows, list) and bool(minute_rows) and all(isinstance(r, dict) for r in minute_rows),
                "MISSING_INTRADAY_ROWS", "Intraday source is empty")
        stamps = [r.get("cntr_tm") for r in minute_rows]
        require(all(isinstance(s, str) and re.fullmatch(r"\d{14}", s) for s in stamps),
                "INVALID_BAR_TIME", "Expected YYYYMMDDHHMMSS timestamps")
        require(len(stamps) == len(set(stamps)), "DUPLICATE_INTRADAY_TIME", "Duplicate intraday timestamps")
        for row, stamp in zip(minute_rows, stamps):
            parsed = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=KST)
            require(parsed <= minute_time, "FUTURE_BAR", "A bar timestamp is after source collection")
            require(parsed.minute % 5 == 0 and parsed.second == 0,
                    "INVALID_BAR_TIME", "Five-minute timestamp is off-grid")
            ohlcv(row)
        day_rows = sorted((r for r in minute_rows if r["cntr_tm"].startswith(previous_date)), key=lambda r: r["cntr_tm"])
        require(bool(day_rows), "PREVIOUS_INTRADAY_DATE_MISSING", "No bars for the declared previous date")
        regular_stamp = previous_date + regular_close
        regular = next((r for r in day_rows if r["cntr_tm"] == regular_stamp), None)
        require(regular is not None, "REGULAR_CLOSE_BAR_MISSING", "Exact regular closing bar missing; a nearby bar is insufficient")
        require(number(regular.get("trde_qty"), positive=False, directional=False) > 0,
                "REGULAR_CLOSE_NOT_TRADED", "Regular closing boundary needs a positive traded quantity")
        require(not has_adjustment(regular) and not has_adjustment(day_rows[-1]),
                "ADJUSTMENT_REQUIRES_RECONCILIATION", "Intraday boundary carries a price adjustment")
        base, daily = number(basic.get("base_pric")), number(previous.get("cur_prc"))
        regular_price, after_price = number(regular.get("cur_prc")), number(day_rows[-1].get("cur_prc"))
        final_interval = day_rows[-1]["cntr_tm"] == previous_date + "195500"
        result["evidence"] = {
            "base_price": float(base), "previous_daily_close": float(daily),
            "regular_close_bar": {"timestamp": regular_stamp, "close": float(regular_price)},
            "aftermarket_last_bar": {"timestamp": day_rows[-1]["cntr_tm"], "close": float(after_price),
                                      "final_interval_present": final_interval},
            "previous_date_bar_count": len(day_rows), "daily_adjustment_mode": str(daily_request["upd_stkpc_tp"]),
            "intraday_adjustment_mode": "0", "base_matches_regular": base == regular_price,
            "daily_matches_aftermarket": daily == after_price,
        }
        require(base == regular_price, "REFERENCE_REGULAR_CLOSE_MISMATCH", "Reference price does not match the exact KRX regular closing bar")
        if base != daily:
            require(final_interval, "AFTERMARKET_CLOSE_BAR_MISSING",
                    "The 19:55 final five-minute interval is not evidenced; inactivity or truncation is unresolved")
        if final_interval:
            require(number(day_rows[-1].get("trde_qty"), positive=False, directional=False) > 0,
                    "AFTERMARKET_CLOSE_NOT_TRADED", "Final aftermarket boundary needs a positive traded quantity")
            require(daily == after_price, "DAILY_AFTERMARKET_CLOSE_MISMATCH", "Previous daily price does not match the final KRX aftermarket interval")
            result["aftermarket_completion_verified"] = True
        result["status"] = "CONSISTENT" if base == daily else "SESSION_DIFFERENCE_CONFIRMED"
        result["can_use_completed_history"] = True
        result["interpretation"] = ("Reference and daily value match the exact regular close; aftermarket completion is reported separately" if base == daily
                                    else "The difference is explained by regular versus aftermarket closing boundaries")
    except EvidenceError as exc:
        result["issues"].append({"code": exc.code, "detail": exc.detail})
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        result["issues"].append({"code": "MALFORMED_INPUT", "detail": str(exc)})
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def verify_wrapper(chart):
    """A legacy metadata wrapper must preserve and hash its source and code."""
    if "source_raw" not in chart:
        return []
    references = []
    for name in ("source_raw", "request_evidence"):
        ref = chart.get(name, {})
        require(isinstance(ref, dict) and isinstance(ref.get("path"), str)
                and isinstance(ref.get("sha256"), str) and re.fullmatch(r"[a-fA-F0-9]{64}", ref["sha256"]),
                "INVALID_LEGACY_REFERENCE", f"{name} needs a source path and SHA256")
        path = Path(ref["path"])
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == ref["sha256"].lower(), "LEGACY_REFERENCE_HASH_MISMATCH", name)
        references.append({"kind": name, "path": str(path), "sha256": actual})
    original = read_json(chart["source_raw"]["path"])
    require(all(chart.get(k) == original.get(k) for k in ("fetched_at", "basic", "rows")),
            "LEGACY_SOURCE_CHANGED", "Metadata wrapper changes original chart values")
    return references


def load_and_evaluate(chart_path, intraday_path, *, trade_date, previous_date,
                      regular_close, checked_at=None):
    """Apply the same source-reference checks used by the CLI to file inputs."""
    chart_path, intraday_path = Path(chart_path), Path(intraday_path)
    try:
        chart, intraday = read_json(chart_path), read_json(intraday_path)
        refs = verify_wrapper(chart)
        result = evaluate_price_session(chart, intraday, trade_date=trade_date,
                                        previous_date=previous_date, regular_close=regular_close,
                                        checked_at=checked_at or datetime.now(timezone.utc).isoformat())
        result["input_files"] = [{"kind": kind, "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                                 for kind, path in (("chart", chart_path), ("intraday", intraday_path))]
        result["verified_legacy_references"] = refs
    except (EvidenceError, OSError, ValueError, TypeError) as exc:
        result = {"policy_version": VERSION, "status": "UNRESOLVED", "trade_date": trade_date,
                  "previous_date": previous_date, "can_use_completed_history": False,
                  "recommendation_approved": False, "aftermarket_completion_verified": False,
                  "issues": [{"code": getattr(exc, "code", "INPUT_READ_FAILURE"), "detail": str(exc)}]}
    return result


def output_overlaps_source(output_path, chart_path, intraday_path):
    """Resolve aliases/symlinks before any result file can be written."""
    protected = [Path(chart_path), Path(intraday_path)]
    try:
        chart = read_json(chart_path)
        if isinstance(chart, dict):
            for key in ("source_raw", "request_evidence"):
                ref = chart.get(key)
                if isinstance(ref, dict) and isinstance(ref.get("path"), str):
                    protected.append(Path(ref["path"]))
    except (OSError, ValueError, TypeError):
        pass  # Reading failure is handled by load_and_evaluate; direct inputs stay protected.
    output_key = os.path.normcase(str(Path(output_path).resolve()))
    return any(output_key == os.path.normcase(str(p.resolve())) for p in protected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart-raw", required=True, type=Path)
    parser.add_argument("--intraday-raw", required=True, type=Path)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--previous-date", required=True)
    parser.add_argument("--regular-close", required=True, help="HHMMSS from verified session calendar, e.g. 153000 or CSAT 163000")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if output_overlaps_source(args.output, args.chart_raw, args.intraday_raw):
        print(json.dumps({"status": "UNRESOLVED", "issues": [{"code": "OUTPUT_OVERLAPS_SOURCE",
                         "detail": "Diagnostic output cannot overwrite input or referenced source evidence"}]}), file=sys.stderr)
        return 2
    result = load_and_evaluate(args.chart_raw, args.intraday_raw, trade_date=args.trade_date,
                               previous_date=args.previous_date, regular_close=args.regular_close)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output), "issues": result["issues"]}, ensure_ascii=True))
    return 2 if result["status"] == "UNRESOLVED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
