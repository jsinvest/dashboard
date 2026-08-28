#!/usr/bin/env python3
"""Build the dashboard history for AI candidate-stock hit rates.

Each published ``candidate_stocks`` entry is treated as one signal.  The signal
is evaluated on the next Korean market session using that session's open and
high prices:

* WIN:  high / open - 1 >= 1%
* DRAW: 0% < high / open - 1 < 1%
* LOSS: high / open - 1 <= 0%

Pending and unavailable observations are never included in the win-rate
denominator.  Historical candidate snapshots are reconstructed from Git so a
new ``analysis_latest.json`` does not erase older recommendations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


KST = timezone(timedelta(hours=9))
SCHEMA_VERSION = "1.0"
WIN_THRESHOLD_PCT = 1.0
DEFAULT_ANALYSIS_REL = Path("market-analysis") / "analysis_latest.json"
DEFAULT_OUTPUT_REL = Path("market-analysis") / "candidate_hit_rate_latest.json"
DEFAULT_VALIDATION_REL = Path("market-analysis") / "candidate_hit_rate_validation_latest.json"
DEFAULT_LEGACY_REL = Path("outputs") / "recommendation_high_20260827" / "source.json"
DEFAULT_RESTAPI_DIR = Path.home() / "Desktop" / "restapi"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="추천 후보 다음 거래일 시가→고가 적중률 누적")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--analysis", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--legacy-source", type=Path)
    parser.add_argument("--restapi-dir", type=Path, default=DEFAULT_RESTAPI_DIR)
    parser.add_argument("--api-end-date", help="키움 조회 종료일 YYYYMMDD, 기본값은 오늘(KST)")
    parser.add_argument("--skip-api", action="store_true", help="키움 REST를 호출하지 않고 기존 검증값만 사용")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 최상위가 객체가 아닙니다: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {result.stderr.strip()}")
    return result.stdout


def normalize_ymd(value: Any) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) < 8:
        return ""
    candidate = digits[:8]
    try:
        datetime.strptime(candidate, "%Y%m%d")
    except ValueError:
        return ""
    return candidate


def normalize_code(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"(\d{6})", text)
    return match.group(1) if match else ""


def finite_price(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "").lstrip("+-")
    if not text:
        return None
    try:
        number = abs(float(text))
    except ValueError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def is_candidate_list(value: Any) -> bool:
    return isinstance(value, list) and any(isinstance(row, dict) and normalize_code(row.get("code")) for row in value)


def snapshot_from_payload(payload: dict[str, Any], source_ref: str) -> dict[str, Any] | None:
    as_of = normalize_ymd(payload.get("as_of"))
    candidates = payload.get("candidate_stocks")
    if not as_of or not is_candidate_list(candidates):
        return None

    final_rows = payload.get("final_picks") if isinstance(payload.get("final_picks"), list) else []
    final_by_code: dict[str, dict[str, Any]] = {}
    for row in final_rows:
        if not isinstance(row, dict):
            continue
        code = normalize_code(row.get("code"))
        if code:
            final_by_code[code] = row

    clean_candidates: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    duplicate_count = 0
    for row in candidates:
        if not isinstance(row, dict):
            continue
        code = normalize_code(row.get("code"))
        if not code:
            continue
        if code in seen_codes:
            duplicate_count += 1
            continue
        seen_codes.add(code)
        final_row = final_by_code.get(code, {})
        clean_candidates.append(
            {
                "market": str(row.get("market") or final_row.get("market") or "").strip(),
                "code": code,
                "name": str(row.get("name") or final_row.get("name") or code).strip(),
                "sector": str(row.get("sector") or final_row.get("sector") or "").strip(),
                "stage": str(row.get("stage") or "").strip(),
                "is_final_pick": bool(final_row),
                "final_priority": final_row.get("priority") if final_row else None,
            }
        )

    return {
        "as_of": as_of,
        "target_session": normalize_ymd(payload.get("target_session")),
        "source_ref": source_ref,
        "candidates": clean_candidates,
        "duplicate_candidates_removed": duplicate_count,
    }


def load_git_snapshots(repo_root: Path, analysis_path: Path) -> list[dict[str, Any]]:
    relative = analysis_path.relative_to(repo_root).as_posix()
    commits = [line.strip() for line in run_git(repo_root, "log", "--format=%H", "--", relative).splitlines() if line.strip()]
    snapshots_by_date: dict[str, dict[str, Any]] = {}

    # Git log is newest first.  The first candidate-bearing publication for a
    # date is the final surviving revision for that recommendation date.
    for commit in commits:
        try:
            raw = run_git(repo_root, "show", f"{commit}:{relative}")
            payload = json.loads(raw)
            snapshot = snapshot_from_payload(payload, commit[:12])
        except (RuntimeError, json.JSONDecodeError, ValueError):
            continue
        if snapshot and snapshot["as_of"] not in snapshots_by_date:
            snapshots_by_date[snapshot["as_of"]] = snapshot

    # A not-yet-committed analysis is still a real current recommendation and
    # must be registered without overwriting an older date's committed record.
    if analysis_path.exists():
        current_payload = read_json(analysis_path)
        current = snapshot_from_payload(current_payload, "WORKTREE")
        if current:
            head_snapshot = snapshots_by_date.get(current["as_of"])
            if head_snapshot is None:
                snapshots_by_date[current["as_of"]] = current
            else:
                current_digest = hashlib.sha256(
                    json.dumps(current_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
                ).hexdigest()
                try:
                    head_raw = run_git(repo_root, "show", f"{head_snapshot['source_ref']}:{relative}")
                    head_payload = json.loads(head_raw)
                    head_digest = hashlib.sha256(
                        json.dumps(head_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest()
                except Exception:
                    head_digest = ""
                if current_digest != head_digest:
                    snapshots_by_date[current["as_of"]] = current

    return [snapshots_by_date[key] for key in sorted(snapshots_by_date)]


def load_legacy_rows(path: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, str]]:
    rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    session_by_as_of: dict[str, str] = {}
    if not path.exists():
        return rows_by_key, session_by_as_of
    payload = read_json(path)
    details = payload.get("details")
    if not isinstance(details, list):
        return rows_by_key, session_by_as_of
    for row in details:
        if not isinstance(row, dict):
            continue
        as_of = normalize_ymd(row.get("as_of"))
        code = normalize_code(row.get("code"))
        entry_date = normalize_ymd(row.get("entry_date"))
        open_price = finite_price(row.get("open"))
        high_price = finite_price(row.get("high"))
        if not as_of or not code or not entry_date or open_price is None or high_price is None:
            continue
        if high_price < open_price:
            continue
        rows_by_key[(as_of, code)] = {
            "entry_date": entry_date,
            "open": open_price,
            "high": high_price,
        }
        session_by_as_of.setdefault(as_of, entry_date)
    return rows_by_key, session_by_as_of


def build_kiwoom_client(restapi_dir: Path) -> Any:
    if not restapi_dir.is_dir():
        raise FileNotFoundError(f"키움 REST 프로젝트 폴더가 없습니다: {restapi_dir}")
    sys.path.insert(0, str(restapi_dir))
    from foreign_institution_k200_tracker import KiwoomRestClient, find_credentials, load_config

    config = load_config()
    app_key, secret_key = find_credentials(config)
    return KiwoomRestClient(app_key, secret_key)


def fetch_code_rows(client: Any, code: str, start_date: str, end_date: str) -> dict[str, dict[str, float]]:
    raw_rows = client.ka10081(code, end_date, start_date)
    parsed: dict[str, dict[str, float]] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        trade_date = normalize_ymd(row.get("dt"))
        open_price = finite_price(row.get("open_pric"))
        high_price = finite_price(row.get("high_pric"))
        if not trade_date or open_price is None or high_price is None or high_price < open_price:
            continue
        parsed[trade_date] = {"open": open_price, "high": high_price}
    return parsed


def compute_stats(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    outcomes = Counter(str(row.get("outcome")) for row in rows)
    evaluated = outcomes["WIN"] + outcomes["DRAW"] + outcomes["LOSS"]
    returns = [float(row["max_return_pct"]) for row in rows if row.get("max_return_pct") is not None]
    return {
        "signals": len(rows),
        "evaluated": evaluated,
        "pending": outcomes["PENDING"],
        "unavailable": outcomes["DATA_UNAVAILABLE"],
        "wins": outcomes["WIN"],
        "draws": outcomes["DRAW"],
        "losses": outcomes["LOSS"],
        "win_rate_pct": round(outcomes["WIN"] / evaluated * 100, 2) if evaluated else None,
        "non_loss_rate_pct": round((outcomes["WIN"] + outcomes["DRAW"]) / evaluated * 100, 2) if evaluated else None,
        "average_max_return_pct": round(sum(returns) / len(returns), 4) if returns else None,
        "median_max_return_pct": round(statistics.median(returns), 4) if returns else None,
    }


def classify(open_price: float, high_price: float) -> tuple[float, str]:
    max_return_pct = (high_price / open_price - 1.0) * 100.0
    if max_return_pct >= WIN_THRESHOLD_PCT - 1e-12:
        outcome = "WIN"
    elif max_return_pct > 0:
        outcome = "DRAW"
    else:
        outcome = "LOSS"
    return round(max_return_pct, 4), outcome


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    analysis_path = (args.analysis or repo_root / DEFAULT_ANALYSIS_REL).resolve()
    output_path = (args.output or repo_root / DEFAULT_OUTPUT_REL).resolve()
    validation_path = (args.validation or repo_root / DEFAULT_VALIDATION_REL).resolve()
    legacy_path = (args.legacy_source or repo_root / DEFAULT_LEGACY_REL).resolve()
    api_end_date = normalize_ymd(args.api_end_date or datetime.now(KST).strftime("%Y%m%d"))
    if not api_end_date:
        raise ValueError("--api-end-date는 YYYYMMDD 형식이어야 합니다.")

    snapshots = load_git_snapshots(repo_root, analysis_path)
    if not snapshots:
        raise RuntimeError("Git 이력과 현재 분석 파일에서 candidate_stocks를 찾지 못했습니다.")

    legacy_rows, legacy_sessions = load_legacy_rows(legacy_path)
    for snapshot in snapshots:
        if not snapshot["target_session"]:
            snapshot["target_session"] = legacy_sessions.get(snapshot["as_of"], "")

    codes = sorted({candidate["code"] for snapshot in snapshots for candidate in snapshot["candidates"]})
    earliest_needed = min(snapshot["as_of"] for snapshot in snapshots)
    rows_by_code: dict[str, dict[str, dict[str, float]]] = {}
    api_errors: dict[str, str] = {}
    api_client_error = ""

    if not args.skip_api:
        try:
            client = build_kiwoom_client(args.restapi_dir.resolve())
        except Exception as exc:
            client = None
            api_client_error = f"{type(exc).__name__}: {exc}"
        if client is not None:
            for index, code in enumerate(codes, start=1):
                try:
                    rows_by_code[code] = fetch_code_rows(client, code, earliest_needed, api_end_date)
                except Exception as exc:
                    api_errors[code] = f"{type(exc).__name__}: {exc}"
                print(f"[{index}/{len(codes)}] {code} rows={len(rows_by_code.get(code, {}))}")

    # Infer missing next-session dates from the earliest verified market bar
    # after each recommendation date.  The inference uses all candidates for
    # that date, never a later bar of a suspended individual stock.
    for snapshot in snapshots:
        if snapshot["target_session"]:
            continue
        later_dates = [
            trade_date
            for candidate in snapshot["candidates"]
            for trade_date in rows_by_code.get(candidate["code"], {})
            if trade_date > snapshot["as_of"]
        ]
        if later_dates:
            snapshot["target_session"] = min(later_dates)

    records: list[dict[str, Any]] = []
    duplicate_total = sum(int(snapshot["duplicate_candidates_removed"]) for snapshot in snapshots)
    for snapshot in snapshots:
        as_of = snapshot["as_of"]
        entry_date = snapshot["target_session"]
        for candidate in snapshot["candidates"]:
            code = candidate["code"]
            price_row = rows_by_code.get(code, {}).get(entry_date) if entry_date else None
            data_source = "Kiwoom REST ka10081"
            if price_row is None:
                fallback = legacy_rows.get((as_of, code))
                if fallback and (not entry_date or fallback["entry_date"] == entry_date):
                    entry_date = entry_date or fallback["entry_date"]
                    price_row = {"open": fallback["open"], "high": fallback["high"]}
                    data_source = "기존 Kiwoom REST ka10081 검증 원천"

            open_price: float | None = None
            high_price: float | None = None
            max_return_pct: float | None = None
            if entry_date and entry_date > api_end_date:
                outcome = "PENDING"
                data_source = "다음 거래일 대기"
            elif price_row is not None:
                open_price = float(price_row["open"])
                high_price = float(price_row["high"])
                max_return_pct, outcome = classify(open_price, high_price)
            else:
                outcome = "DATA_UNAVAILABLE"
                data_source = "일봉 확인 불가"

            records.append(
                {
                    "id": f"{as_of}:{code}",
                    "recommendation_date": as_of,
                    "entry_date": entry_date or None,
                    "market": candidate["market"],
                    "code": code,
                    "name": candidate["name"],
                    "sector": candidate["sector"],
                    "stage": candidate["stage"],
                    "is_final_pick": candidate["is_final_pick"],
                    "final_priority": candidate["final_priority"],
                    "open": open_price,
                    "high": high_price,
                    "max_return_pct": max_return_pct,
                    "outcome": outcome,
                    "price_source": data_source,
                    "recommendation_source": snapshot["source_ref"],
                }
            )

    records.sort(key=lambda row: (row["recommendation_date"], row["market"], row["code"]), reverse=True)
    summary = compute_stats(records)
    final_summary = compute_stats(row for row in records if row["is_final_pick"])
    by_market = {
        market: compute_stats(row for row in records if row["market"] == market)
        for market in sorted({row["market"] for row in records if row["market"]})
    }
    by_date = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["recommendation_date"]].append(row)
    for recommendation_date in sorted(grouped, reverse=True):
        stats = compute_stats(grouped[recommendation_date])
        entry_dates = sorted({row["entry_date"] for row in grouped[recommendation_date] if row["entry_date"]})
        by_date.append(
            {
                "recommendation_date": recommendation_date,
                "entry_date": entry_dates[0] if len(entry_dates) == 1 else None,
                **stats,
            }
        )

    unavailable_due = [row for row in records if row["outcome"] == "DATA_UNAVAILABLE"]
    pending = [row for row in records if row["outcome"] == "PENDING"]
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "through_recommendation_date": max(snapshot["as_of"] for snapshot in snapshots),
        "price_data_through": api_end_date,
        "population": "market-analysis/analysis_latest.json의 candidate_stocks; 추천일별 마지막 게시본",
        "rule": {
            "entry": "추천 다음 거래일 시가",
            "exit_reference": "같은 거래일 고가",
            "return_formula": "(고가 / 시가 - 1) * 100",
            "win": "시가 대비 고가 +1.00% 이상",
            "draw": "시가 대비 고가 0% 초과, +1.00% 미만",
            "loss": "시가 대비 고가 0% 이하",
            "denominator": "WIN + DRAW + LOSS; PENDING과 DATA_UNAVAILABLE 제외",
            "lookahead_note": "당일 고점을 사전에 알 수 없으므로 실현수익이 아닌 후보 선별력의 사후 상한 평가",
        },
        "summary": summary,
        "final_pick_reference": final_summary,
        "by_market": by_market,
        "by_recommendation_date": by_date,
        "data_quality": {
            "recommendation_dates": len(snapshots),
            "first_recommendation_date": min(snapshot["as_of"] for snapshot in snapshots),
            "duplicate_candidates_removed": duplicate_total,
            "unique_codes": len(codes),
            "api_requested": not args.skip_api,
            "api_codes_succeeded": len(rows_by_code),
            "api_codes_failed": len(api_errors),
            "api_client_error": api_client_error or None,
            "unavailable_due_records": len(unavailable_due),
            "pending_records": len(pending),
            "legacy_source_used": sum(1 for row in records if row["price_source"].startswith("기존")),
        },
        "records": records,
    }
    write_json(output_path, payload)

    validation_status = "OK" if not unavailable_due and not api_errors and not api_client_error else "PARTIAL"
    validation = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": validation_status,
        "can_render_verified_records": True,
        "complete_due_coverage": not unavailable_due,
        "output": str(output_path),
        "output_sha256": sha256_path(output_path),
        "analysis": str(analysis_path),
        "analysis_sha256": sha256_path(analysis_path),
        "recommendation_dates": [snapshot["as_of"] for snapshot in snapshots],
        "record_count": len(records),
        "evaluated_count": summary["evaluated"],
        "pending_count": summary["pending"],
        "unavailable_count": summary["unavailable"],
        "duplicate_record_ids": len(records) - len({row["id"] for row in records}),
        "api_errors": api_errors,
        "notes": [
            "승률 분모에는 판정 완료된 승·무·패만 포함합니다.",
            "후보군은 추천일별 마지막으로 게시된 candidate_stocks를 사용합니다.",
            "다음 거래일 일봉이 없는 종목은 다른 날짜로 넘겨 평가하지 않습니다.",
        ],
    }
    write_json(validation_path, validation)

    print(
        f"[DONE] dates={len(snapshots)} signals={summary['signals']} evaluated={summary['evaluated']} "
        f"W/D/L={summary['wins']}/{summary['draws']}/{summary['losses']} pending={summary['pending']} "
        f"unavailable={summary['unavailable']} status={validation_status}"
    )
    print(f"  output: {output_path}")
    print(f"  validation: {validation_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
