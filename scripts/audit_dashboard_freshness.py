"""Inventory active dashboard evidence by actual data date, never file mtime.

Five days means KST calendar-date difference >= 5. Archives and fixed links are
not expected to receive daily data. Generation and observation dates are distinct.
"""
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))


def date_value(value):
    text = str(value or "")
    match = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", text)
    if not match:
        return None
    try:
        return date(*map(int, match.groups())).isoformat()
    except ValueError:
        return None


def audit(root, as_of):
    rows = []
    def add(key, label, tab, path, get_date, **extra):
        p = root / path
        row = dict(id=key, label=label, tab=tab, path=path, **extra)
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
            row["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
            row["data_date"] = date_value(get_date(data))
            row["generated_at"] = data.get("generated_at") or data.get("collected_at")
            row["reported_status"] = data.get("status") or data.get("research_status")
            if data.get("can_use_for_context") is False:
                row.update(availability="EXCLUDED", note="원천 누락·검증 실패. 과거 정상값으로 대체하지 않음")
            if key == "research":
                invalid = data.get("publication_validation", {}).get("source_hashes_match") is False
                row.update(availability="EXCLUDED" if invalid else "RESEARCH_ONLY", note="연구 전용. 정정·중복 및 현재 원천 해시 불일치 때문에 방향 결정에 사용하지 않음" if invalid else "연구 전용; 자동 방향·비중 결정 사용 금지")
            if key == "market-ai" and data.get("publication_kind") == "DATA_REFRESH":
                row["note"] = "검증자료 갱신본. 신규 예측·종목선정 미실시; 기존 예측 이력 보존"
            if key == "candidate-hit":
                row["note"] = "갱신일은 성적 계산일. 마지막 실제 후보 추천일 " + str(data.get("through_recommendation_date"))
            if key in ("candidate-hit", "market-hit"):
                row["evaluation_summary"] = data.get("summary")
            if key == "etf-weights":
                row["note"] = "주간 비교 종료일 기준; 운용사 응답 기준일 미확인 등 원문 한계 유지"
        except (OSError, ValueError, TypeError, KeyError) as e:
            row.update(data_date=None, availability="UNAVAILABLE", note=type(e).__name__)
        finish(row)
        return row

    def finish(row):
        observed = date_value(row.get("data_date"))
        age = (as_of - date.fromisoformat(observed)).days if observed else None
        row.update(age_calendar_days=age, freshness="UNKNOWN" if age is None else "FUTURE_DATE" if age < 0 else "STALE" if age >= 5 else "FRESH")
        row.setdefault("availability", "AVAILABLE")
        rows.append(row)

    add("market-raw", "시장 원본·차트", "market", "market-analysis/latest.json", lambda d:d["as_of"])
    add("market-ai", "시장 검증 요약", "market", "market-analysis/analysis_latest.json", lambda d:d["as_of"])
    add("index-mtf", "국내·니케이 다중 시간대", "market", "market-analysis/index_mtf_validation_latest.json", lambda d:d["trade_date"])
    add("candidate-hit", "후보 누적승률 재계산", "market", "market-analysis/candidate_hit_rate_latest.json", lambda d:d["generated_at"])
    add("market-hit", "시장뷰 누적승률 재계산", "market", "market-analysis/market_view_hit_rate_latest.json", lambda d:d["generated_at"])
    add("us-index", "미국·니케이 10분 통합 보조", "market", "market-analysis/us_index_mtf_analysis.json", lambda d:d["trade_date"])
    add("research", "지수 방향 연구", "market", "market-analysis/index_direction_research_latest.json", lambda d:d["trade_date"])
    add("cash", "현금비중", "cash", "cash-management/latest.json", lambda d:d["trade_date"])
    add("reports", "리포트 검색", "report", "report_data.json", lambda d:d["meta"].get("last_source_checked_through") or d["meta"].get("last_merge_through"))
    add("report-signals", "목표주가 상향·하향", "report", "report_signal_data.json", lambda d:d["meta"].get("target_price_source_checked_through") or d["meta"].get("generated_at"))
    add("daily-report", "당일 리포트", "daily-report", "daily-reports/latest.json", lambda d:d["latest_date"])
    add("news", "당일 뉴스", "daily-report", "news/index.json", lambda d:max(x["cutoff"] for x in d["reports"]))
    add("leaders", "주도주 맵핑", "leaders", "leader-mapping/validation_latest.json", lambda d:d["trade_date"], note="장중 자료. 신고가 보조층의 자료 불일치는 별도 유지")
    add("etf-weights", "ETF비중 주간 비교", "etf-weights", "etf-weights/latest.json", lambda d:d["end_date"])
    add("futures", "선물옵션 검토 본문", "supply", "supply-zone/latest.json", lambda d:d["as_of"])
    add("futures-zip", "선물옵션 공개 검토 ZIP", "supply", "supply-zone/data_bundle_latest.json", lambda d:d["as_of"])
    html = (root / "index.html").read_text(encoding="utf-8")
    found = re.search(r'data-sector-weight-date="([^"]+)"', html)
    if found:
        finish({"id":"sector-cap", "label":"시장 섹터 시총 지도", "tab":"leaders", "path":"index.html", "data_date":found[1], "availability":"HISTORICAL_ONLY", "note":"최신 WICS 구성·보통주 시총 원천 미확보. 과거 참고자료로 접어 보존; 현재 비중 사용 금지"})
    # Fixed routes are not time series. An old connection manifest does not imply stale ticks.
    for key, label, tab in [("charts","국내·해외·환율 지표·대표ETF 차트","all"), ("schedule","일정","schedule"), ("links","링크 모음","links"), ("program-live","프로그램 수급","program-live"), ("cvd-live","선물 CVD","cvd-live")]:
        finish({"id":key,"label":label,"tab":tab,"path":"index.html" if key in ("charts","schedule","links") else "live-monitors/connection.json", "data_date":None, "availability":"LIVE_CHECK_REQUIRED", "note":"외부 API·보호된 수집기 자료. 별도 실제 응답/관측일 검사 필요; 설정파일 수정일로 판정하지 않음"})
    external_path = root / "dashboard-health/live_checks.json"
    external = json.loads(external_path.read_text(encoding="utf-8")) if external_path.is_file() else None
    return {"schema_version":1,"checked_at":datetime.now(KST).isoformat(timespec="seconds"),"as_of":as_of.isoformat(),"threshold_calendar_days":5,"definition":"KST 달력 날짜 차이 5일 이상; 생성시각과 자료 기준일 구분", "items":rows, "external_checks": external,
        "summary":{"items":len(rows),"stale":sum(x["freshness"]=="STALE" for x in rows),"excluded":sum(x["availability"]=="EXCLUDED" for x in rows),"unknown_live_checks":sum(x["availability"]=="LIVE_CHECK_REQUIRED" for x in rows)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(KST).date())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = audit(args.repo_root, args.as_of)
    output = args.output or args.repo_root / "dashboard-health/latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"]))
