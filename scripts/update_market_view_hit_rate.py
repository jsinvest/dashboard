#!/usr/bin/env python3
"""Evaluate published KOSPI/KOSDAQ market views on the next full session.

The historical prose was not originally stored with a machine-readable
direction.  A dated semantic audit below classifies only a clear directional
tilt as UP or DOWN.  Conflicted, relative-only, or box-market views are kept as
NEUTRAL observations and excluded from directional accuracy.

For a directional view, accuracy is measured from the last completed session's
close before the target session to the target session's close.  If a view was
published after that session had already opened, the following full session is
used so an in-progress day is never scored as a forecast.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


KST = timezone(timedelta(hours=9))
SCHEMA_VERSION = "1.0"
DEFAULT_ANALYSIS_REL = Path("market-analysis") / "analysis_latest.json"
DEFAULT_OUTPUT_REL = Path("market-analysis") / "market_view_hit_rate_latest.json"
DEFAULT_VALIDATION_REL = Path("market-analysis") / "market_view_hit_rate_validation_latest.json"
DEFAULT_INDEX_ROOT = Path.home() / "Desktop" / "trading_strength" / "output" / "index_multitimeframe"


# Historical semantic audit.  These labels are deliberately conservative:
# relative strength alone is NEUTRAL because it does not predict an absolute
# rise, and conflicting/box descriptions are not forced into a direction.
DIRECTION_AUDIT: dict[tuple[str, str], tuple[str, str]] = {
    ("20260806", "KOSPI"): ("NEUTRAL", "상대 우위이지만 공세 전환 전으로 절대 방향 미제시"),
    ("20260806", "KOSDAQ"): ("UP", "선택적 반등을 명시"),
    ("20260810", "KOSPI"): ("NEUTRAL", "안정 우위이나 추세 확인 부족"),
    ("20260810", "KOSDAQ"): ("UP", "탄력 우위를 명시"),
    ("20260811", "KOSPI"): ("DOWN", "방어 국면을 명시"),
    ("20260811", "KOSDAQ"): ("UP", "시장 폭 우위를 명시"),
    ("20260812", "KOSPI"): ("UP", "방어적 반등을 명시"),
    ("20260812", "KOSDAQ"): ("UP", "순환매 준비 구간을 명시"),
    ("20260813", "KOSPI"): ("NEUTRAL", "강한 현물 수급과 야간 약세의 충돌"),
    ("20260813", "KOSDAQ"): ("DOWN", "당일 확산과 Impulse 약화·신규 추격 보류"),
    ("20260814", "KOSPI"): ("UP", "상대 우위와 확산 확인"),
    ("20260814", "KOSDAQ"): ("NEUTRAL", "ADR 회복과 Impulse BLUE가 충돌"),
    ("20260818", "KOSPI"): ("DOWN", "야간 급락 반영·시초 하방 확인 우선"),
    ("20260818", "KOSDAQ"): ("DOWN", "방어 국면·신규선정 없음"),
    ("20260819", "KOSPI"): ("DOWN", "광범위한 위험회피를 명시"),
    ("20260819", "KOSDAQ"): ("NEUTRAL", "지수 방어와 내부 약세·좁은 반등이 충돌"),
    ("20260820", "KOSPI"): ("UP", "강한 반등을 명시"),
    ("20260820", "KOSDAQ"): ("UP", "종목 확산이 넓은 반등을 명시"),
    ("20260821", "KOSPI"): ("DOWN", "지수 착시형 방어장·대부분 종목 하락"),
    ("20260821", "KOSDAQ"): ("DOWN", "광범위한 위험회피를 명시"),
    ("20260824", "KOSPI"): ("DOWN", "일봉 박스 안 장중 하방을 명시"),
    ("20260824", "KOSDAQ"): ("UP", "조건부 반등장을 명시"),
    ("20260825", "KOSPI"): ("UP", "단기 반등을 명시"),
    ("20260825", "KOSDAQ"): ("UP", "단기 탄력 우위를 명시"),
    ("20260826", "KOSPI"): ("UP", "조건부 상방 우세를 명시"),
    ("20260826", "KOSDAQ"): ("NEUTRAL", "중립·선별 종목장"),
    ("20260827", "KOSPI"): ("NEUTRAL", "중립·박스"),
    ("20260827", "KOSDAQ"): ("NEUTRAL", "중립·박스"),
    ("20260828", "KOSPI"): ("DOWN", "단기 하방 우세를 명시"),
    ("20260828", "KOSDAQ"): ("NEUTRAL", "단기 상대우위와 중기 중립-하락의 혼조"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="게시된 시장뷰의 다음 거래일 방향 적중률 누적")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--analysis", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--index-root", type=Path, default=DEFAULT_INDEX_ROOT)
    parser.add_argument("--price-date", help="사용할 검증 지수자료 기준일 YYYYMMDD")
    return parser.parse_args()


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


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 최상위가 객체가 아닙니다: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {result.stderr.strip()}")
    return result.stdout


def parse_published_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def extract_snapshot(payload: dict[str, Any], source_ref: str) -> dict[str, Any] | None:
    as_of = normalize_ymd(payload.get("as_of"))
    views = payload.get("market_views")
    if not as_of or not isinstance(views, list):
        return None
    domestic: list[dict[str, Any]] = []
    for row in views:
        if not isinstance(row, dict):
            continue
        market = str(row.get("market") or "").strip().upper()
        if market not in {"KOSPI", "KOSDAQ"}:
            continue
        explicit = str(row.get("direction") or "").strip().upper()
        audited = DIRECTION_AUDIT.get((as_of, market))
        if explicit in {"UP", "DOWN", "NEUTRAL"}:
            direction = explicit
            rationale = "게시 JSON의 구조화 direction"
            classification_source = "published_structured_direction"
        elif audited:
            direction, rationale = audited
            classification_source = "historical_semantic_audit"
        else:
            direction = "UNCLASSIFIED"
            rationale = "구조화 방향과 보수적 과거 분류표가 없음"
            classification_source = "unclassified"
        domestic.append(
            {
                "market": market,
                "view": str(row.get("view") or "").strip(),
                "action": str(row.get("action") or "").strip(),
                "direction": direction,
                "classification_rationale": rationale,
                "classification_source": classification_source,
            }
        )
    if not domestic:
        return None
    return {
        "as_of": as_of,
        "target_session": normalize_ymd(payload.get("target_session")),
        "published_at": parse_published_at(payload.get("generated_at")),
        "source_ref": source_ref,
        "views": domestic,
    }


def load_snapshots(repo_root: Path, analysis_path: Path) -> list[dict[str, Any]]:
    relative = analysis_path.relative_to(repo_root).as_posix()
    snapshots: dict[str, dict[str, Any]] = {}
    for commit in run_git(repo_root, "log", "--format=%H", "--", relative).splitlines():
        commit = commit.strip()
        if not commit:
            continue
        try:
            payload = json.loads(run_git(repo_root, "show", f"{commit}:{relative}"))
            snapshot = extract_snapshot(payload, commit[:12])
        except (RuntimeError, json.JSONDecodeError, ValueError):
            continue
        if snapshot and snapshot["as_of"] not in snapshots:
            snapshots[snapshot["as_of"]] = snapshot

    if analysis_path.exists():
        payload = read_json(analysis_path)
        current = extract_snapshot(payload, "WORKTREE")
        if current:
            snapshots[current["as_of"]] = current
    return [snapshots[key] for key in sorted(snapshots)]


def find_verified_index_bundle(index_root: Path, requested: str) -> tuple[Path, dict[str, Any]]:
    candidates = [requested] if requested else sorted(
        [path.name for path in index_root.iterdir() if path.is_dir() and re.fullmatch(r"\d{8}", path.name)],
        reverse=True,
    )
    for trade_date in candidates:
        folder = index_root / trade_date
        validation_path = folder / f"validation_{trade_date}.json"
        if not validation_path.exists():
            continue
        validation = read_json(validation_path)
        instruments = validation.get("instruments") if isinstance(validation.get("instruments"), dict) else {}
        if (
            validation.get("status") == "OK"
            and validation.get("can_use_for_decision") is True
            and all(instruments.get(market, {}).get("can_use_for_decision") is True for market in ("KOSPI", "KOSDAQ"))
        ):
            return folder, validation
    raise RuntimeError("KOSPI·KOSDAQ 모두 검증 통과한 지수 다중시간대 번들을 찾지 못했습니다.")


def load_daily(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            trade_date = normalize_ymd(row.get("date"))
            try:
                close = float(row.get("close") or "nan")
            except ValueError:
                continue
            if trade_date and math.isfinite(close) and close > 0:
                rows.append({"date": trade_date, "close": close})
    rows.sort(key=lambda row: row["date"])
    if len({row["date"] for row in rows}) != len(rows):
        raise RuntimeError(f"지수 일봉 날짜 중복: {path}")
    return rows


def choose_target(snapshot: dict[str, Any], trading_dates: list[str]) -> str:
    explicit = snapshot["target_session"]
    if explicit:
        return explicit
    published_at = snapshot["published_at"]
    as_of = snapshot["as_of"]
    if published_at:
        published_date = published_at.strftime("%Y%m%d")
        # Before the open, that day's full session is still forecastable.
        if published_at.timetz().replace(tzinfo=None) < time(9, 0) and published_date in trading_dates:
            return published_date
        later = [trade_date for trade_date in trading_dates if trade_date > published_date]
        if later:
            return later[0]
    later = [trade_date for trade_date in trading_dates if trade_date > as_of]
    return later[0] if later else ""


def accuracy_stats(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    directional = [row for row in rows if row["direction"] in {"UP", "DOWN"}]
    evaluated = [row for row in directional if row["outcome"] in {"WIN", "LOSS"}]
    wins = sum(row["outcome"] == "WIN" for row in evaluated)
    losses = sum(row["outcome"] == "LOSS" for row in evaluated)
    return {
        "views": len(rows),
        "directional_views": len(directional),
        "evaluated": len(evaluated),
        "pending": sum(row["outcome"] == "PENDING" for row in directional),
        "wins": wins,
        "losses": losses,
        "accuracy_pct": round(wins / len(evaluated) * 100, 2) if evaluated else None,
        "neutral_observations": sum(row["direction"] == "NEUTRAL" for row in rows),
        "unclassified": sum(row["direction"] == "UNCLASSIFIED" for row in rows),
    }


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    analysis_path = (args.analysis or repo_root / DEFAULT_ANALYSIS_REL).resolve()
    output_path = (args.output or repo_root / DEFAULT_OUTPUT_REL).resolve()
    validation_path = (args.validation or repo_root / DEFAULT_VALIDATION_REL).resolve()
    requested_date = normalize_ymd(args.price_date)

    snapshots = load_snapshots(repo_root, analysis_path)
    if not snapshots:
        raise RuntimeError("게시 이력에서 국내 market_views를 찾지 못했습니다.")
    folder, index_validation = find_verified_index_bundle(args.index_root.resolve(), requested_date)
    price_date = normalize_ymd(index_validation.get("trade_date"))
    daily_paths = {
        "KOSPI": folder / "data" / f"kospi_daily_{price_date}.csv",
        "KOSDAQ": folder / "data" / f"kosdaq_daily_{price_date}.csv",
    }
    daily = {market: load_daily(path) for market, path in daily_paths.items()}
    if any(rows[-1]["date"] != price_date for rows in daily.values()):
        raise RuntimeError("지수 일봉 최신일과 검증 기준일이 일치하지 않습니다.")

    records: list[dict[str, Any]] = []
    for snapshot in snapshots:
        for view in snapshot["views"]:
            market = view["market"]
            rows = daily[market]
            dates = [row["date"] for row in rows]
            target_date = choose_target(snapshot, dates)
            target_index = dates.index(target_date) if target_date in dates else -1
            base_date = dates[target_index - 1] if target_index > 0 else None
            base_close = rows[target_index - 1]["close"] if target_index > 0 else None
            target_close = rows[target_index]["close"] if target_index >= 0 else None
            return_pct: float | None = None
            if base_close is not None and target_close is not None:
                return_pct = round((target_close / base_close - 1.0) * 100.0, 4)

            direction = view["direction"]
            if direction == "NEUTRAL":
                outcome = "NEUTRAL_OBSERVATION" if return_pct is not None else "PENDING"
            elif direction == "UNCLASSIFIED":
                outcome = "UNCLASSIFIED"
            elif return_pct is None:
                outcome = "PENDING"
            elif direction == "UP":
                outcome = "WIN" if return_pct > 0 else "LOSS"
            else:
                outcome = "WIN" if return_pct < 0 else "LOSS"

            records.append(
                {
                    "id": f"{snapshot['as_of']}:{market}",
                    "recommendation_date": snapshot["as_of"],
                    "published_at": snapshot["published_at"].isoformat(timespec="seconds") if snapshot["published_at"] else None,
                    "base_session": base_date,
                    "target_session": target_date or None,
                    "market": market,
                    "view": view["view"],
                    "direction": direction,
                    "classification_rationale": view["classification_rationale"],
                    "classification_source": view["classification_source"],
                    "base_close": base_close,
                    "target_close": target_close,
                    "next_session_return_pct": return_pct,
                    "outcome": outcome,
                    "recommendation_source": snapshot["source_ref"],
                }
            )

    records.sort(key=lambda row: (row["recommendation_date"], row["market"]), reverse=True)
    summary = accuracy_stats(records)
    by_market = {market: accuracy_stats(row for row in records if row["market"] == market) for market in ("KOSPI", "KOSDAQ")}
    by_direction = {direction: accuracy_stats(row for row in records if row["direction"] == direction) for direction in ("UP", "DOWN")}
    by_date: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["recommendation_date"]].append(row)
    for recommendation_date in sorted(grouped, reverse=True):
        by_date.append({"recommendation_date": recommendation_date, **accuracy_stats(grouped[recommendation_date])})

    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "through_recommendation_date": max(snapshot["as_of"] for snapshot in snapshots),
        "price_data_through": price_date,
        "rule": {
            "population": "게시된 KOSPI·KOSDAQ market_views의 추천일별 마지막 게시본",
            "direction": "명확한 절대 방향만 UP/DOWN; 상대우위·충돌·박스는 NEUTRAL",
            "target": "게시 후 첫 완전한 거래일",
            "return_formula": "(대상 거래일 종가 / 직전 거래일 종가 - 1) * 100",
            "up_win": "UP이고 다음 거래일 종가수익률 > 0",
            "down_win": "DOWN이고 다음 거래일 종가수익률 < 0",
            "neutral": "방향 적중률 분모에서 제외하고 실제 변동만 기록",
            "timing_guard": "장 시작 후 게시된 뷰는 진행 중인 장을 평가하지 않고 그다음 완전한 거래일을 사용",
        },
        "summary": summary,
        "by_market": by_market,
        "by_direction": by_direction,
        "by_recommendation_date": by_date,
        "data_quality": {
            "index_bundle": str(folder),
            "index_validation_status": index_validation.get("status"),
            "index_can_use_for_decision": index_validation.get("can_use_for_decision"),
            "index_files": {market: str(path) for market, path in daily_paths.items()},
            "index_file_sha256": {market: sha256_path(path) for market, path in daily_paths.items()},
            "recommendation_dates": len(snapshots),
            "records": len(records),
            "duplicate_record_ids": len(records) - len({row["id"] for row in records}),
        },
        "records": records,
    }
    write_json(output_path, payload)

    validation_status = "OK" if summary["unclassified"] == 0 and payload["data_quality"]["duplicate_record_ids"] == 0 else "PARTIAL"
    validation = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": validation_status,
        "can_render_verified_records": True,
        "output": str(output_path),
        "output_sha256": sha256_path(output_path),
        "analysis": str(analysis_path),
        "analysis_sha256": sha256_path(analysis_path),
        "price_date": price_date,
        "index_validation": str(folder / f"validation_{price_date}.json"),
        "index_validation_sha256": sha256_path(folder / f"validation_{price_date}.json"),
        "record_count": len(records),
        "directional_evaluated": summary["evaluated"],
        "directional_pending": summary["pending"],
        "neutral_observations": summary["neutral_observations"],
        "unclassified": summary["unclassified"],
        "duplicate_record_ids": payload["data_quality"]["duplicate_record_ids"],
        "notes": [
            "중립·상대우위·충돌형 문장은 방향 승률 분모에서 제외합니다.",
            "과거 문장 분류는 결과를 보지 않고 문구 의미만으로 고정한 보수적 감사표를 사용합니다.",
            "앞으로는 market_views에 UP/DOWN/NEUTRAL direction을 게시 시점에 저장합니다.",
        ],
    }
    write_json(validation_path, validation)
    print(
        f"[DONE] views={summary['views']} directional={summary['directional_views']} "
        f"evaluated={summary['evaluated']} W/L={summary['wins']}/{summary['losses']} "
        f"accuracy={summary['accuracy_pct']} pending={summary['pending']} neutral={summary['neutral_observations']}"
    )
    print(f"  output: {output_path}")
    print(f"  validation: {validation_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
