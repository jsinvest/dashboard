"""Check scheduled publication against pinned Git objects and cache-bypassed Pages.

Read-only by default. --repair-futures-bundle rebuilds only the public ZIP and
its descriptor from already-committed reviewed artifacts; never runs collectors,
changes market analysis, commits, pushes, or sends messages.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import urllib.parse
import urllib.request
import zipfile

KST = timezone(timedelta(hours=9))
SPECS = [
    ("market-raw", "시장 원본", "market-analysis/latest.json", "trade", 21),
    ("market-ai", "시장 최종 분석·추천", "market-analysis/analysis_latest.json", "trade", 21),
    ("index-mtf", "국내·니케이 다중 시간대", "market-analysis/index_mtf_validation_latest.json", "trade", 21),
    ("us-index", "미국·니케이 보조자료", "market-analysis/us_index_mtf_analysis.json", "trade", 21),
    ("research", "지수 방향 연구", "market-analysis/index_direction_research_latest.json", "trade", 21),
    ("cash", "현금비중", "cash-management/latest.json", "trade", 21),
    ("leaders", "주도주 맵핑", "leader-mapping/validation_latest.json", "trade", 20),
    ("futures", "선물옵션 본문", "supply-zone/latest.json", "trade", 17),
    ("futures-zip", "선물옵션 공개 ZIP", "supply-zone/data_bundle_latest.json", "trade", 17),
    ("reports", "리포트 검색", "report_data.json", "source", 20),
    ("report-signals", "목표주가 상향·하향", "report_signal_data.json", "source", 20),
    ("daily-report", "당일 리포트", "daily-reports/latest.json", "source", 9),
    ("news", "아침·저녁 뉴스", "news/index.json", "news", 19),
    ("etf", "ETF 주간 비교", "etf-weights/latest.json", "weekly", 9),
    ("candidate-hit", "후보 성적 계산", "market-analysis/candidate_hit_rate_latest.json", "trade", 21),
    ("market-hit", "시장뷰 성적 계산", "market-analysis/market_view_hit_rate_latest.json", "trade", 21),
]


def sha(body):
    return hashlib.sha256(body).hexdigest()


def day(value):
    text = str(value or "")[:10]
    return date.fromisoformat(text if "-" in text else text[:8])


def canonical(body):
    return sha(json.dumps(json.loads(body), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode())


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)


def read_object(root, ref, path):
    return git(root, "show", f"{ref}:{path}")


def evidence_json(body, member=None):
    if member:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            if len(archive.namelist()) != len(set(archive.namelist())) or archive.testzip():
                raise ValueError("시장 자료 ZIP 중복/CRC 오류")
            body = archive.read(member)
    return json.loads(body)


def publication_evidence(read, key, legacy_path):
    """Follow the published manifest's hashed bundle, retaining legacy fallback.

    Follow only known evidence members or the explicitly linked dated review.
    Never select by mtime or turn a stale file into a current research signal.
    """
    if key == "futures-zip":
        manifest_path = "supply-zone/latest.json"
        manifest_body = read(manifest_path)
        futures = json.loads(manifest_body)
        name = "futures_public_review_" + day(futures["as_of"]).strftime("%Y%m%d") + ".zip"
        if name in public_files(futures):
            path = "supply-zone/" + name
            body = read(path)
            verification = verify_review_bundle(body, manifest_body, name, lambda n: read("supply-zone/" + n))
            return path, "latest.json", body, {
                "evidence_manifest": manifest_path, "manifest_sha256": sha(manifest_body),
                "legacy_path": legacy_path, "bundle_format": "dated_public_review", **verification}
    members = {"index-mtf": "index_multitimeframe_validation_latest.json",
               "research": "validation/mandatory_audit.json"}
    if key not in members:
        return legacy_path, None, read(legacy_path), {}
    manifest_path = "market-analysis/latest.json"
    manifest_body = read(manifest_path)
    manifest = json.loads(manifest_body)
    descriptor = manifest.get("data_bundle", {})
    name, declared_hash = descriptor.get("file"), descriptor.get("sha256")
    if not name or not declared_hash:
        return legacy_path, None, read(legacy_path), {}
    if PurePosixPath(name).name != name or "\\" in name or name in (".", ".."):
        raise ValueError("시장 자료 ZIP 참조 경로 오류")
    path = "market-analysis/" + name
    body = read(path)
    if sha(body) != declared_hash:
        raise ValueError("시장 자료 ZIP 선언 해시 불일치")
    if day(descriptor["as_of"]) != day(manifest["as_of"]):
        raise ValueError("시장 본문과 ZIP 기준일 불일치")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        if members[key] not in archive.namelist():
            return legacy_path, None, read(legacy_path), {}
    d = evidence_json(body, members[key])
    if day(d["trade_date"]) != day(manifest["as_of"]) or d.get("status") != "OK":
        raise ValueError("시장 ZIP 검증자료 기준일/상태 불일치")
    metadata = {"evidence_manifest": manifest_path, "manifest_sha256": sha(manifest_body),
                "declared_bundle_sha256": declared_hash, "legacy_path": legacy_path}
    if key == "research":
        handoff = d.get("research_handoff", {})
        if day(handoff.get("trade_date")) != day(manifest["as_of"]) or handoff.get("status") != "RESEARCH_ONLY":
            raise ValueError("시장 ZIP 연구 인계자료 기준일/상태 불일치")
        hashes = [x.get("sha256", "") for x in d.get("sources", [])
                  if str(x.get("path", "")).replace("\\", "/").endswith("/index_direction_research_latest.json")]
        if len(hashes) != 1 or len(hashes[0]) != 64 or any(c not in "0123456789abcdef" for c in hashes[0]):
            raise ValueError("시장 ZIP 연구 원천 해시 누락/중복")
        metadata.update(research_status=handoff["status"], source_research_sha256=hashes[0],
                        research_automatic_effect=handoff.get("automatic_effect"))
    return path, members[key], body, metadata


def calendar_evidence(path, now):
    d = json.loads(path.read_text(encoding="utf-8-sig"))
    if (d.get("status") != "VERIFIED" or day(d.get("trade_date")) != now.date()
            or d.get("calendar_year") != now.year
            or datetime.fromisoformat(d["checked_at_kst"]).astimezone(KST).date() != now.date()):
        raise ValueError("당일 KRX 공식 달력 검증이 필요합니다")
    raw = Path(d["raw_path"]).read_bytes()
    if sha(raw) != d["raw_sha256"]:
        raise ValueError("KRX 달력 원문 해시 불일치")
    rows = json.loads(raw)["block1"]
    holidays = {day(x["calnd_dd"]) for x in rows}
    if len(holidays) != len(rows) or len(rows) != d["holiday_count"]:
        raise ValueError("KRX 휴장일 중복 또는 건수 불일치")
    if not all(x.year == now.year for x in holidays):
        raise ValueError("KRX 휴장일 연도 불일치")
    return holidays, {"path": str(path), "sha256": sha(path.read_bytes()),
                      "raw_sha256": sha(raw), "checked_at_kst": d["checked_at_kst"]}


def trading_day_before(value, holidays):
    year = value.year
    while value.weekday() >= 5 or value in holidays:
        value -= timedelta(days=1)
    if value.year != year:
        raise ValueError("직전 연도의 공식 거래일 달력이 추가로 필요합니다")
    return value


def expected_day(cadence, hour, now, holidays):
    if cadence == "source":
        return None  # Source publication/no-new-report must be checked separately.
    if cadence == "news":
        return now.date() if now.hour >= 7 else now.date() - timedelta(days=1)
    if cadence == "weekly":
        saturday = now.date() - timedelta(days=(now.weekday() - 5) % 7)
        if now < datetime.combine(saturday, time(9), KST):
            saturday -= timedelta(days=7)
        return trading_day_before(saturday - timedelta(days=1), holidays)
    target = now.date() if now.hour >= hour else now.date() - timedelta(days=1)
    return trading_day_before(target, holidays)


def observed_day(key, d):
    if key == "news":
        return day(max(x["cutoff"] for x in d["reports"]))
    if key == "reports":
        return day(d["meta"].get("last_source_checked_through") or d["meta"].get("last_merge_through"))
    if key == "report-signals":
        return day(d["meta"].get("target_price_source_checked_through") or d["meta"].get("generated_at"))
    if key in ("candidate-hit", "market-hit"):
        return day(d["generated_at"])
    return day(d.get("trade_date") or d.get("as_of") or d.get("latest_date") or d.get("end_date"))


def json_issues(key, d, now):
    issues = []
    if key == "market-ai":
        for name in ("executive_summary", "market_views", "risk_flags", "next_session_checks", "candidate_stocks", "final_picks"):
            if not isinstance(d.get(name), list):
                issues.append("SCHEMA:" + name)
        if not isinstance(d.get("elliott_wave_view"), dict):
            issues.append("SCHEMA:elliott_wave_view")
        for view in d.get("market_views", []):
            if not isinstance(view, dict) or not isinstance(view.get("evidence"), list):
                issues.append("SCHEMA:market_views.evidence")
        phase = d.get("data_validation", {}).get("phase")
        if phase == "PROVISIONAL":
            issues.append("FINAL_PENDING" if now.hour < 21 else "FINAL_NOT_PUBLISHED")
        if d.get("publication_kind") == "DATA_REFRESH":
            issues.append("NEW_ANALYSIS_NOT_PERFORMED")
    if d.get("can_use_for_context") is False or d.get("can_use_for_decision") is False:
        issues.append("VALIDATION_EXCLUDED")
    if key == "research" and d.get("publication_validation", {}).get("source_hashes_match") is False:
        issues.append("SOURCE_HASH_MISMATCH")
    if key == "leaders" and d.get("integration_data_status") not in (None, "OK", "VERIFIED", "MATCHED"):
        issues.append("LEADER_AUXILIARY:" + str(d["integration_data_status"]))
    if key == "news":
        target = now.date() if now.hour >= 7 else now.date() - timedelta(days=1)
        editions = {x.get("edition") for x in d["reports"] if day(x["cutoff"]) == target}
        required = {"morning", "evening"} if now.hour >= 19 or now.hour < 7 else {"morning"}
        if not required.issubset(editions):
            issues.append("NEWS_EDITION_MISSING")
    return issues


def fetch(base, path, stamp):
    url = base.rstrip("/") + "/" + urllib.parse.quote(path, safe="/") + "?upload_audit=" + stamp
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "DashboardUploadAudit/1"}), timeout=25) as response:
        return response.read()


def public_files(d):
    """Only the publisher's explicit public charts/downloads; never raw inputs."""
    result = {"latest.json": None}
    for group in ("charts", "downloads"):
        for item in d.get(group, []):
            name = item["file"]
            if PurePosixPath(name).name != name or "\\" in name or name in (".", ".."):
                raise ValueError("공개 참조 파일 경로가 안전하지 않습니다: " + name)
            result[name] = item.get("sha256")
    return result


def verify_review_bundle(body, futures_body, bundle_name, read_public):
    """Validate the dated ZIP explicitly linked by the public review body."""
    futures = json.loads(futures_body)
    manifest_name = "review_manifest_" + day(futures["as_of"]).strftime("%Y%m%d") + ".json"
    expected = set(public_files(futures)) - {bundle_name}
    if bundle_name not in public_files(futures):
        raise ValueError("공개 본문에 연결되지 않은 검토 ZIP")
    eol_members = []
    def same_content(name, archived, published):
        if archived == published:
            return True
        if PurePosixPath(name).suffix.lower() not in {".json", ".csv", ".html", ".txt", ".md"}:
            return False
        # Git's Windows checkout conversion is not a data correction. Permit
        # only UTF-8 text CRLF/LF differences, retaining the actual ZIP hashes.
        try:
            equal = archived.decode("utf-8").replace("\r\n", "\n") == published.decode("utf-8").replace("\r\n", "\n")
        except UnicodeDecodeError:
            return False
        if equal and name not in eol_members:
            eol_members.append(name)
        return equal
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or z.testzip():
            raise ValueError("검토 ZIP 중복/CRC 오류")
        if set(names) != expected | {manifest_name}:
            raise ValueError("검토 ZIP 공개 파일 목록 불일치")
        if not same_content("latest.json", z.read("latest.json"), futures_body):
            raise ValueError("검토 ZIP과 공개 본문 불일치")
        manifest = json.loads(z.read(manifest_name))
        if day(manifest["as_of"]) != day(futures["as_of"]) or manifest.get("contract") != futures.get("futures_contract"):
            raise ValueError("검토 ZIP 기준일/계약 불일치")
        records = manifest["files"]
        if len(records) != len(expected) or {x["file"] for x in records} != expected:
            raise ValueError("검토 ZIP 검증 목록 불일치")
        for record in records:
            name = record["file"]
            content = z.read(name)
            if sha(content) != record["sha256"] or not same_content(name, content, read_public(name)):
                raise ValueError("검토 ZIP 공개 파일 해시 불일치: " + name)
    return {"eol_normalized_members": sorted(eol_members),
            "archive_hash_policy": "Manifest hashes checked on original ZIP bytes; public UTF-8 text permits CRLF/LF conversion only."}


def verify_bundle(descriptor, body, futures, read_public):
    if sha(body) != descriptor["sha256"] or len(body) != descriptor["bytes"]:
        raise ValueError("ZIP 해시/크기 불일치")
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or z.testzip():
            raise ValueError("ZIP 중복/CRC 오류")
        manifest = json.loads(z.read("manifest.json"))
        expected = set(public_files(futures))
        records = manifest["files"]
        if descriptor["file_count"] != len(records) or manifest["file_count"] != len(records):
            raise ValueError("ZIP 파일 건수 불일치")
        if len(records) != len(expected) or {x["path"] for x in records} != expected:
            raise ValueError("ZIP 공개 파일 목록 불일치")
        if set(names) != expected | {"manifest.json", "GPT_README.txt"}:
            raise ValueError("ZIP에 승인된 공개 파일 외 항목이 있습니다")
        if day(manifest["as_of"]) != day(futures["as_of"]) or day(descriptor["as_of"]) != day(futures["as_of"]):
            raise ValueError("ZIP과 선물옵션 본문 기준일 불일치")
        for record in records:
            content = z.read(record["path"])
            if sha(content) != record["sha256"] or content != read_public(record["path"]):
                raise ValueError("ZIP 내부 공개 원문 불일치: " + record["path"])


def repair_bundle(root, ref, now):
    futures = json.loads(read_object(root, ref, "supply-zone/latest.json"))
    validation = futures.get("data_validation", {})
    if not validation.get("ready_for_editorial_review") or day(validation.get("trade_date")) != day(futures["as_of"]):
        raise ValueError("게시된 선물옵션 본문의 검증·기준일이 불충분합니다")
    try:
        current = json.loads(read_object(root, ref, "supply-zone/data_bundle_latest.json"))
        verify_bundle(current, read_object(root, ref, "supply-zone/" + current["file"]), futures,
                      lambda n: read_object(root, ref, "supply-zone/" + n))
        return {"status": "UNCHANGED", **current}
    except (ValueError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile):
        pass
    contents = {}
    for name, expected_hash in public_files(futures).items():
        content = read_object(root, ref, "supply-zone/" + name)
        if not content or (expected_hash and sha(content) != expected_hash):
            raise ValueError("공개 참조 파일 누락/해시 불일치: " + name)
        contents[name] = content
    manifest = {"bundle_type": "published_reviewed_futures_evidence", "as_of": day(futures["as_of"]).strftime("%Y%m%d"),
                "generated_at": now.isoformat(), "file_count": len(contents),
                "notes": ["공개 검토 자료만 수록. 비공개 원장·계좌·인증정보는 수록하지 않음"],
                "files": [{"path": n, "bytes": len(b), "sha256": sha(b)} for n, b in sorted(contents.items())]}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("GPT_README.txt", "이미 게시된 같은 거래일 검토 JSON·차트·다운로드만 수록합니다. 원문 한계와 월물 구분을 유지하세요.\n")
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, content in sorted(contents.items()):
            z.writestr(name, content)
    body = output.getvalue()
    descriptor = {"file": "futures_options_data_bundle_latest.zip", "as_of": manifest["as_of"], "generated_at": now.isoformat(),
                  "file_count": len(contents), "bytes": len(body), "sha256": sha(body),
                  "title": "선물옵션 공개 검토 자료 ZIP", "futures_contract": futures.get("futures_contract"),
                  "coverage": "PUBLISHED_REVIEWED_ARTIFACTS_ONLY", "source_review_sha256": sha(contents["latest.json"]),
                  "source_commit": git(root, "rev-parse", ref).decode().strip()}
    verify_bundle(descriptor, body, futures, contents.__getitem__)
    for name, content in [(descriptor["file"], body), ("data_bundle_latest.json", (json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n").encode())]:
        destination = root / "supply-zone" / name
        # Do not overwrite another task's modified or staged bundle.
        if git(root, "status", "--porcelain", "--", "supply-zone/" + name).strip():
            raise ValueError("다른 미커밋 ZIP 변경이 있습니다: " + name)
    for name, content in [(descriptor["file"], body), ("data_bundle_latest.json", (json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n").encode())]:
        destination = root / "supply-zone" / name
        temporary = destination.with_suffix(destination.suffix + ".audit-tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)
    return descriptor


def check_assets(root, commit, path, d, base, stamp):
    assets = {}
    for group in ("charts", "downloads"):
        for item in d.get(group, []):
            name = item.get("file") or item.get("image")
            if not name or PurePosixPath(name).name != name or "\\" in name:
                raise ValueError("공개 차트/다운로드 참조 경로 오류")
            assets[name] = item.get("sha256")
    folder = str(PurePosixPath(path).parent)
    def check(pair):
        name, declared = pair
        content = read_object(root, commit, folder + "/" + name)
        if not content or (declared and sha(content) != declared):
            raise ValueError("차트/다운로드 원문 해시 불일치: " + name)
        public = fetch(base, folder + "/" + name, stamp)
        if sha(public) != sha(content):
            raise ValueError("공개 차트/다운로드 해시 불일치: " + name)
        return name
    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(check, assets.items()))


def audit(root, workspace, source, ref, base, now, calendar_path):
    commit = git(root, "rev-parse", ref).decode().strip()
    holidays, calendar = calendar_evidence(calendar_path, now)
    stamp = now.strftime("%Y%m%d%H%M%S")
    def inspect(spec):
        key, label, path, cadence, hour = spec
        expected = expected_day(cadence, hour, now, holidays)
        row = dict(id=key, label=label, path=path, cadence=cadence, expected_date=expected.isoformat() if expected else None, issues=[])
        try:
            path, member, body, metadata = publication_evidence(lambda p: read_object(root, commit, p), key, path)
            row.update(path=path, zip_member=member, **metadata)
            d = evidence_json(body, member)
            actual = observed_day(key, d)
            row.update(remote_date=actual.isoformat(), git_sha256=sha(body), validation_status=d.get("status") or d.get("research_status"))
            if expected and actual < expected:
                row["issues"].append("EXPECTED_DATE_NOT_PUBLISHED")
            if actual > now.date():
                row["issues"].append("FUTURE_DATE")
            row["issues"].extend(json_issues(key, d, now))
            local = workspace / path
            if local.is_file():
                try:
                    local_body = local.read_bytes()
                    local_d = evidence_json(local_body, member)
                    row.update(local_date=observed_day(key, local_d).isoformat(), primary_checkout_matches_remote=sha(local_body) == sha(body))
                except (ValueError, KeyError, zipfile.BadZipFile) as e:
                    row.update(local_evidence_status="UNAVAILABLE:" + type(e).__name__, primary_checkout_matches_remote=False)
            published = fetch(base, path, stamp)
            public_d = evidence_json(published, member)
            matches = sha(published) == sha(body) if member else canonical(published) == canonical(body)
            row.update(public_sha256=sha(published), public_date=observed_day(key, public_d).isoformat(), pages_matches_commit=matches)
            if not row["pages_matches_commit"]:
                row["issues"].append("PAGES_DIFFERS_FROM_PINNED_COMMIT")
            if key in ("reports", "report-signals", "daily-report"):
                row["source_publication_check"] = "REQUIRED_IF_NO_NEW_ROWS; data age alone is not a failure"
            if key == "futures-zip":
                futures = json.loads(read_object(root, commit, "supply-zone/latest.json"))
                if member:
                    row["public_zip_verification"] = verify_review_bundle(
                        published, read_object(root, commit, "supply-zone/latest.json"), PurePosixPath(path).name,
                        lambda n: read_object(root, commit, "supply-zone/" + n))
                    row["public_zip_contents_verified"] = True
                elif day(d["as_of"]) != day(futures["as_of"]):
                    row["issues"].append("BUNDLE_REVIEW_DATE_MISMATCH")
                else:
                    archive = fetch(base, "supply-zone/" + d["file"], stamp)
                    verify_bundle(d, archive, futures, lambda n: read_object(root, commit, "supply-zone/" + n))
                    row["public_zip_contents_verified"] = True
            if key == "etf":
                row["period"] = {"start": d.get("start_date"), "end": d.get("end_date")}
            if key in ("market-raw", "futures"):
                row["public_assets_verified"] = check_assets(root, commit, path, d, base, stamp)
        except Exception as e:
            row["issues"].append("CHECK_FAILED:" + type(e).__name__ + ":" + str(e)[:180])
        return row
    with ThreadPoolExecutor(max_workers=5) as pool:
        items = list(pool.map(inspect, SPECS))
    state = workspace / ".codex_tmp" / ("daily_market_" + now.strftime("%Y%m%d") + "_state.json")
    state_note = {"path": str(state), "present": state.is_file()}
    if state.is_file():
        d = json.loads(state.read_text(encoding="utf-8-sig"))
        state_note["stages"] = {k: {a: v.get(a) for a in ("status", "exit_code", "completed_at", "reason") if a in v} for k, v in d.items() if isinstance(v, dict)}
        state_note["note"] = "A historical stage failure does not prove a current stall; inspect recovery and active processes."
    sources = []
    for rel in ("cash_management/wise_daily/wise_final_latest.json", "cash_management/monthly/validation_latest.json",
                "cash_management/staged/validation_latest.json", "index_multitimeframe/validation_latest.json",
                "us_index_multitimeframe/validation_latest.json", "index_direction_model/index_direction_research_latest.json",
                "leader_mapping_integrated/validation_latest.json", "market_context_runner/validation_latest.json"):
        p = source / "output" / rel
        record = {"path": str(p)}
        try:
            body = p.read_bytes()
            d = json.loads(body)
            record.update(sha256=sha(body), trade_date=d.get("trade_date"), status=d.get("status") or d.get("research_status"),
                          can_use_for_decision=d.get("can_use_for_decision"), can_use_for_context=d.get("can_use_for_context"))
        except (OSError, ValueError) as e:
            record["error"] = type(e).__name__
        sources.append(record)
    return {"checked_at": now.isoformat(), "pinned_commit": commit, "calendar": calendar, "items": items,
            "state_evidence": state_note, "source_snapshots": sources, "summary": {"items": len(items), "items_with_findings": sum(bool(x["issues"]) for x in items)},
            "public_dom_verified": False, "public_dom_note": "Separate rendered DOM QA is required. Check the actual authentication gate; never bypass one.",
            "scope": "Schedule/date/JSON/schema/Pages and reviewed ZIP verification. Not full source/OCR or independent market-data validation. Fixed reference maps excluded; live API/links need separate response checks."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "Documents/New project")
    parser.add_argument("--source-root", type=Path, default=Path.home() / "Desktop/trading_strength")
    parser.add_argument("--ref", default="origin/main")
    parser.add_argument("--base-url", default="https://jsinvest.github.io/dashboard/")
    parser.add_argument("--now", type=datetime.fromisoformat)
    parser.add_argument("--calendar", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repair-futures-bundle", action="store_true")
    args = parser.parse_args()
    now = (args.now or datetime.now(KST)).astimezone(KST)
    if args.repair_futures_bundle:
        print(json.dumps(repair_bundle(args.repo_root, args.ref, now), ensure_ascii=False))
    else:
        paths = sorted((args.source_root / "output/eod_admin_task" / now.strftime("%Y%m%d")).glob("calendar_validation_*.json"))
        calendar = args.calendar or (paths[-1] if paths else None)
        if calendar is None:
            parser.error("당일 공식 달력 검증을 먼저 실행하세요: scripts/verify_krx_trading_calendar.ps1 -TradeDate YYYYMMDD")
        payload = audit(args.repo_root, args.workspace_root, args.source_root, args.ref, args.base_url, now, calendar)
        output = args.output or args.workspace_root / "reports/dashboard-health" / (now.strftime("%Y%m%d_%H%M%S") + ".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(output), **payload["summary"], "findings": [{"id": x["id"], "date": x.get("remote_date"), "issues": x["issues"]} for x in payload["items"] if x["issues"]]}, ensure_ascii=False))
