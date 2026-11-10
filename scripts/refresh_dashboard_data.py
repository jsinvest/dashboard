"""Refresh published evidence from completed, verified local runs; never run collectors.

No orders, batch execution, Git operations, messaging, or new stock recommendations.
The evidence-only edition is deliberately excluded from forecast hit-rate history.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def refresh(repo, source, day):
    datetime.strptime(day, "%Y%m%d")
    out = repo / "market-analysis"
    folder = source / "output/index_multitimeframe" / day
    val = read(folder / f"validation_{day}.json")
    assert val["trade_date"] == day and val["status"] == "OK" and val["can_use_for_decision"] is True
    manifest = read(folder / f"manifest_{day}.json")
    assert manifest["as_of"] == day
    for item in manifest["files"]:
        assert sha(folder / item["path"]) == item["sha256"], item["path"]
    mtf = read(folder / f"index_mtf_analysis_{day}.json")
    assert mtf["as_of"]["trade_date"] == day
    csv_audits = []
    for market in ("kospi", "kosdaq"):
        path = folder / "data" / f"{market}_daily_{day}.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        dates = [row["date"][:10] for row in rows]
        assert len(dates) == len(set(dates)) and dates == sorted(dates)
        assert dates[-1].replace("-", "") == day
        for row in rows:
            o, h, l, c = (float(row[key]) for key in ("open", "high", "low", "close"))
            assert 0 < l <= min(o, c) <= max(o, c) <= h
        csv_audits.append({"market": market.upper(), "first": dates[0], "last": dates[-1], "rows": len(rows), "duplicate_dates": 0, "sha256": sha(path)})
    # The publisher's build function only copies artifacts. Do not call its Git publisher.
    sys.path.insert(0, str(source))
    publisher = load_module(source / "publish_market_dashboard.py")
    publisher.PUBLISH_DIR = out
    publisher.DASHBOARD_REPO = repo
    zip_module = load_module(source / "dashboard_data_bundle.py")
    def dated_market_zip(requested_day):
        assert requested_day == day
        entries = [(folder / item["path"], "indices/" + item["path"]) for item in manifest["files"]]
        entries += [(folder / f"manifest_{day}.json", "indices/source_manifest.json")]
        for p in [source / "시장판정" / f"breadth_board_{day}.csv", source / "results/impulse_adr" / day / "market_summary.csv", source / "results" / day / "fear_greed" / f"fear_greed_summary_{day}.csv"]:
            entries.append((p, "market/" + p.name))
        return zip_module.create_data_zip(out / "market_data_bundle_latest.zip", entries, bundle_type="verified_dated_market_evidence", as_of=day,
            readme=f"{day} 일자별 검증 지수 원본·누적 OHLC와 해당일 시장 요약입니다. 전체 섹터·스캐너 원장을 모두 포함하는 묶음은 아닙니다. manifest.json의 파일·해시를 확인하세요.",
            notes=["일자별 검증 지수와 시장 요약만 포함; 다른 날짜로 갱신 중인 전역 누적 파일은 제외"])
    publisher.build_market_data_zip = dated_market_zip
    bundle = publisher.build_bundle(day)
    for item in bundle["charts"]:
        item["description"] += " · 장중 수집본과 저녁 확정 지수의 시각을 구분"
    write(out / "latest.json", bundle)
    shutil.copy2(folder / f"index_mtf_analysis_{day}.json", out / "index_mtf_analysis_latest.json")
    shutil.copy2(folder / f"validation_{day}.json", out / "index_mtf_validation_latest.json")

    # Keep source failure states; never substitute an old successful 'latest'.
    usroot = source / "output/us_index_multitimeframe"
    usval = read(usroot / "validation_latest.json")
    assert usval["trade_date"] == day
    uspath = Path(usval["analysis_path"])
    assert sha(uspath) == usval["analysis_sha256"]
    for name in ("us_context_latest.json", "us_index_mtf_analysis.json"):
        shutil.copy2(uspath, out / name)
    for name in ("us_context_validation_latest.json", "us_index_mtf_validation.json"):
        shutil.copy2(usroot / "validation_latest.json", out / name)
    research_path = source / "output/index_direction_model/index_direction_research_latest.json"
    research = read(research_path)
    assert research["trade_date"] == day and research["research_status"] == "RESEARCH_ONLY"
    # A mutable cumulative source can change after the model was produced.
    # Preserve that mismatch and exclude this optional research, without blocking raw data.
    research_mismatches = []
    for path, digest in research["data_quality"]["source_files"].items():
        if not Path(path).is_file() or sha(path) != digest:
            research_mismatches.append(Path(path).name)
    research["publication_validation"] = {"trade_date": day, "source_hashes_match": not research_mismatches, "mismatched_sources": research_mismatches, "can_use_for_decision": False, "note": "연구 전용. 현재 원천 해시 불일치가 있으면 해당 연구 신호도 현재 해석에서 제외"}
    for name in ("index_direction_research_latest.json", "index_direction_research.json"):
        write(out / name, research)

    cash = read(repo / "cash-management/latest.json")
    assert cash["status"] == "OK" and cash["trade_date"] == day
    cash_pct = cash["combined_guidance"]["target_cash_pct"]
    risky_pct = cash["combined_guidance"]["target_risky_pct"]
    old = read(out / "analysis_latest.json")
    if old.get("publication_kind") != "DATA_REFRESH":
        shutil.copy2(out / "analysis_latest.json", out / "analysis_previous_forecast.json")
        shutil.copy2(out / "analysis_latest.md", out / "analysis_previous_forecast.md")
    analysis = dict(old)
    now = datetime.now(KST).isoformat(timespec="seconds")
    limitations = [
        f"자료 기준일 {day}; 게시 시점의 오늘 장이나 신규 예측을 분석한 결과가 아닙니다.",
        "종목 재선정 미실시: 과거 관심종목·가격 조건을 현재 추천으로 이월하지 않았습니다.",
        "미국·니케이 10분 통합 보조는 원천 공백 때문에 PARTIAL, can_use_for_context=false입니다. 과거 정상값은 제외합니다.",
        "방향 연구는 RESEARCH_ONLY이며 중복·정정 이력과 한계를 보존합니다. 자동 방향·비중 근거로 사용하지 않습니다.",
        "장중 시장 폭·ADR·공포탐욕과 저녁 확정 지수는 수집 시각과 대표상품이 다릅니다.",
    ]
    views = []
    for market in ("KOSPI", "KOSDAQ"):
        inst = mtf["instruments"][market]
        daily = inst["timeframes"]["daily"]
        summary = next(row for row in bundle["summaries"] if row["market"] == market)
        evidence = [
            f"키움 확정 일봉 {daily['latest_bar'][:10]} 종가 {daily['ohlc']['close']:,.2f}; 전일 {daily['returns_pct']['1']:+.3f}%, 5일 {daily['returns_pct']['5']:+.3f}%, 20일 {daily['returns_pct']['20']:+.3f}%.",
            f"완료봉 원신호: 월 {mtf['assessment']['markets'][market]['monthly']} / 주 {mtf['assessment']['markets'][market]['weekly']} / 일 {mtf['assessment']['markets'][market]['daily']} / 15분 {mtf['assessment']['markets'][market]['intraday_15m']}. 진행 중 월·주봉 제외.",
            f"장중 원신호: 전체종목 20일 ADR {summary['stocks_adr_20d']}%, ETF ADR {summary['etf_adr_20d']}%, Impulse {summary['impulse']}, 공포탐욕 {summary['fear_greed']} ({summary['fear_stage']}).",
        ]
        views.append({"market": market, "direction": "NEUTRAL", "view": "검증자료 갱신 · 다음 장 방향 예측 미실시", "evidence": evidence, "action": "기존 가격 조건과 추천을 현재 신호로 재사용하지 않고 새 분석 시 재검증"})
    analysis.update({
        "as_of": day, "target_session": "", "generated_at": now,
        "source_generated_at": mtf["generated_at_kst"], "publication_kind": "DATA_REFRESH",
        "headline": f"{day[4:6]}/{day[6:8]} 검증 시장자료 갱신 · 신규 방향 예측·종목 재선정 미실시",
        "market_preference": "지수 약세 원신호 · 시장 폭은 별도 확인", "stance": "자료 점검·갱신", "confidence": "예측 확률 산정 대상 아님",
        "data_validation": {"as_of": day, "phase": "EVIDENCE_REFRESH", "source_dates": "장중 원자료 + 같은 거래일 저녁 확정 지수. 원본·누적 CSV·검증표·해시 대조. 전체 수집 배치 재실행 없음.", "cash_weight": {"trade_date": day, "monthly_status": "OK", "staged_status": "OK", "final_cash_pct": cash_pct, "final_risky_pct": risky_pct, "automatic_order": False}, "stock_selection_performed": False},
        "executive_summary": [f"KOSPI {views[0]['evidence'][0]}", f"KOSDAQ {views[1]['evidence'][0]}", f"기존 검증 현금비중 {cash_pct:g}%, 위험자산 한도 {risky_pct:g}%를 연결했습니다. 이번 자료 갱신에서 재계산·변경하지 않았습니다."] + limitations[:3],
        "elliott_wave_view": {"market": "KOSPI", "as_of": day, "status": "재분석 미실시", "preferred_count": "과거 파동 가격 조건은 원본 Git 이력에 보존하며 현재 가설로 이월하지 않습니다.", "alternate_count": "판단 불가", "immediate_support": "신규 산정 미실시", "critical_invalidation": "신규 산정 미실시", "recovery_confirmation": "신규 산정 미실시", "bearish_count_invalidation": "신규 산정 미실시", "limitations": "이번 작업은 갱신 복구이며 파동 재카운트·매매 시나리오 작성은 포함하지 않습니다."},
        "market_views": views, "cumulative_context": {"coverage": csv_audits, "note": "3일·5일·20일 등 원천 계산값은 지수 원본 JSON과 전체 누적 ZIP에서 확인"},
        "derivatives_overlay": {"status": "SEPARATE_REVIEW", "as_of": read(repo / "supply-zone/latest.json")["as_of"], "note": "선물옵션 메뉴의 별도 원천검토본 참조. 현물 점수에 자동 합산하지 않음"},
        "strong_sectors": [], "weak_sectors": [], "candidate_stocks": [], "final_picks": [],
        "excluded_summary": ["과거 개별종목 추천·관심 조건은 최신 자료로 재검증하기 전 이월하지 않음"],
        "trading_rule": "종목 재선정 미실시. 빈 후보 목록은 전체 종목을 검토한 뒤 부적합 판정한 결과가 아닙니다. 자료 갱신본은 추천·시장 방향 적중률의 신규 신호로 집계하지 않습니다.",
        "risk_flags": limitations, "next_session_checks": ["최신 완료 거래일의 장중·저녁 원천을 다시 대조", "미국·니케이 원천 공백 해소와 can_use_for_context 확인", "새 종목선정 시 ETF 신규·증가·편출·감소 모두 대조"],
        "news_check": {"status": "SEPARATE_NEWS_MENU", "note": "이번 갱신에서 별도 뉴스 영향 분석 미실시. 당일 체크의 출처별 뉴스 참조"},
        "source_note": "refresh_validation_latest.json과 지수 validation·manifest를 참조하세요. 최근 실제 AI 분석은 analysis_previous_forecast.json/.md에 원문 보존합니다. 원본 생성일을 변경하지 않습니다.",
        "cash_monthly": f"{day} 기존 검증 월간 {cash['monthly_primary']['target_cash_pct']:g}%",
        "cash_staged": f"{day} 기존 검증 단계형 {cash['staged_weekly']['target_cash_pct']:g}%",
        "cash_final_reference": f"{day} 현금 {cash_pct:g}% / 위험자산 한도 {risky_pct:g}% · 참고값 · 자동주문 아님",
    })
    # Preserve the renderer's required nested types as well as top-level keys.
    for key in ("executive_summary", "market_views", "risk_flags", "next_session_checks", "candidate_stocks", "final_picks"):
        assert isinstance(analysis[key], list) and isinstance(old[key], list)
    assert isinstance(analysis["elliott_wave_view"], dict)
    assert all(isinstance(row["evidence"], list) for row in views)
    write(out / "analysis_latest.json", analysis)
    (out / "analysis_latest.md").write_text("\n\n".join([analysis["headline"]] + analysis["executive_summary"] + [row['market'] + "\n" + "\n".join(row['evidence']) for row in views] + limitations) + "\n", encoding="utf-8")

    # Bundle only already-public, date-specific reviewed artifacts. Never glob private inputs.
    futures = read(repo / "supply-zone/latest.json")
    fday = futures["as_of"].replace("-", "")
    assert fday == day
    files = {"latest.json"} | {x["file"] for x in futures.get("downloads", [])} | {x["file"] for x in futures.get("charts", [])}
    entries = []
    for name in sorted(files):
        assert Path(name).name == name
        path = repo / "supply-zone" / name
        assert path.is_file() and path.stat().st_size > 0
        for item in futures.get("charts", []):
            if item["file"] == name and item.get("sha256"):
                assert sha(path) == item["sha256"]
        entries.append((path, name))
    z = load_module(source / "dashboard_data_bundle.py")
    metadata = z.create_data_zip(repo / "supply-zone/futures_options_data_bundle_latest.zip", entries, bundle_type="published_reviewed_futures_evidence", as_of=day,
        readme=f"거래일 {day}. 대시보드에 이미 공개된 해당일 검토 JSON·차트만 묶었습니다. 전체 비공개 원장·계좌자료·인증정보를 포함하지 않습니다. 원문 제한과 검증 경고를 그대로 적용하세요.",
        notes=["공개 검토 자료 묶음이며 전체 HTS/OCR·비공개 누적 원장을 모두 수록한 묶음이 아닙니다.", "다른 만기와 야간 자료를 연속 포지션으로 합산하지 않습니다."])
    metadata.update(title="선물옵션 공개 검토 자료 ZIP", futures_contract=futures.get("futures_contract"), coverage="PUBLISHED_REVIEWED_ARTIFACTS_ONLY")
    write(repo / "supply-zone/data_bundle_latest.json", metadata)
    validation = {"status": "OK_WITH_EXCLUSIONS", "trade_date": day, "generated_at": now, "publication_kind": "DATA_REFRESH", "collectors_executed": False, "new_forecast_or_stock_selection": False,
        "index_manifest_files_verified": len(manifest["files"]), "index_validation_sha256": sha(folder / f"validation_{day}.json"), "daily_csv_checks": csv_audits,
        "us_source_status": usval["status"], "us_can_use_for_context": usval["can_use_for_context"], "research_status": "RESEARCH_ONLY",
        "research_quality_warnings": research["data_quality"].get("sector_revision_audit"), "research_source_hash_mismatches": research_mismatches, "futures_bundle_files": len(entries), "limitations": limitations}
    validation["output_sha256"] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.suffix in (".json", ".csv", ".png", ".zip") and p.name != "refresh_validation_latest.json" and (p.name in {"latest.json", "analysis_latest.json", "index_mtf_analysis_latest.json", "index_mtf_validation_latest.json", "us_context_latest.json", "us_context_validation_latest.json", "us_index_mtf_analysis.json", "us_index_mtf_validation.json", "index_direction_research_latest.json", "index_direction_research.json"} or p.name.endswith((".png", ".csv", ".zip")))}
    write(out / "refresh_validation_latest.json", validation)
    print(json.dumps({"status": validation["status"], "trade_date": day, "manifest_files_verified": len(manifest["files"]), "new_recommendations": False, "futures_zip_files": len(entries)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-root", type=Path, default=Path.home() / "Desktop/trading_strength")
    parser.add_argument("--trade-date", required=True)
    args = parser.parse_args()
    refresh(args.repo_root.resolve(), args.source_root.resolve(), args.trade_date)
