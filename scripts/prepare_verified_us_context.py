"""Copy a validated US/Nikkei context run into dashboard assets; no Git or collection."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def prepare(repo, run_root, source_root, research):
    validation_path = run_root / "validation_latest.json"
    validation = read(validation_path)
    assert validation["status"] == "OK" and validation["can_use_for_context"] is True
    analysis_path = Path(validation["analysis_path"])
    assert sha(analysis_path) == validation["analysis_sha256"]
    assert sha(source_root / "us_index_mtf_daily.py") == validation["script_sha256"]
    for item in validation["artifacts"]:
        assert sha(item["path"]) == item["sha256"], item["path"]
    analysis = read(analysis_path)
    assert analysis["trade_date"] == validation["trade_date"]
    keys = ("NASDAQ", "SOX", "DOW", "NIKKEI225")
    assert set(analysis["indices"]) == set(keys)
    for key in keys:
        check = validation["checks"][key]
        assert check["status"] == "OK" and check["intraday_can_use"] is True
    nikkei = validation["checks"]["NIKKEI225"]
    assert nikkei["intraday_active_window_gaps"] == []
    assert nikkei["intraday_analysis_window"]["daily_session_crosscheck"] == "MATCH"
    for path, digest in nikkei["input_hashes"].items():
        assert sha(path) == digest, path
    out = repo / "market-analysis"
    assets = out / "us-context"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("us_context_latest.json", "us_index_mtf_analysis.json"):
        shutil.copy2(analysis_path, out / name)
    for name in ("us_context_validation_latest.json", "us_index_mtf_validation.json"):
        shutil.copy2(validation_path, out / name)
    indices = []
    for key in keys:
        item = analysis["indices"][key]
        chart = Path(item["chart"])
        shutil.copy2(chart, assets / chart.name)
        for suffix in ("daily", "monthly", "weekly", "intraday_10m"):
            path = analysis_path.parent / f"{key}_{suffix}.csv"
            shutil.copy2(path, assets / path.name)
        indices.append({"key": key, "name": item["name"], "source_session_date": item["source_session_date"],
                        "timeframes": item["timeframes"], "chart": "us-context/" + chart.name})
    payload = {"schema_version": 1, "trade_date": analysis["trade_date"], "source_session_date": analysis["source_session_date"],
               "generated_at": analysis["generated_at"], "status": "OK", "can_use_for_context": True,
               "source_role": analysis["source_role"], "indices": indices, "nikkei_window": nikkei["intraday_analysis_window"],
               "retained_source_gaps": nikkei["intraday_source_gaps"], "limitations": analysis["limitations"],
               "source_analysis_file": "us_context_latest.json", "source_analysis_sha256": sha(analysis_path),
               "validation_file": "us_context_validation_latest.json", "validation_sha256": sha(validation_path)}

    # A separate stable snapshot corrects mutable-source hash drift without
    # creating a new published forecast, ledger entry, order, or allocation.
    if research:
        model = read(research)
        assert model["research_status"] == "RESEARCH_ONLY"
        mismatches = [Path(path).name for path, digest in model["data_quality"]["source_files"].items() if sha(path) != digest]
        assert not mismatches, mismatches
        model["publication_validation"] = {"trade_date": model["trade_date"], "source_hashes_match": True,
            "source_count_verified": len(model["data_quality"]["source_files"]), "mismatched_sources": [],
            "can_use_for_decision": False, "snapshot_recomputation": True,
            "optional_source_warnings": [] if model["squeeze_research"].get("status") == "OK_RESEARCH_ONLY" else [{"source":"Squeeze", "status":model["squeeze_research"].get("status"), "reason":model["squeeze_research"].get("reason"), "excluded":True}],
            "note": "마지막 검증 완료 지수 기준일의 고정 입력으로 연구를 재계산. 신규 사전 예측 게시·정식 모델 승격 아님. 원천의 중복·정정 한계와 RESEARCH_ONLY 유지"}
        for name in ("index_direction_research_latest.json", "index_direction_research.json"):
            write(out / name, model)
    sys.path.insert(0, str(source_root))
    from dashboard_data_bundle import create_data_zip
    entries = [(Path(item["path"]), "run/" + Path(item["path"]).relative_to(analysis_path.parent).as_posix()) for item in validation["artifacts"]]
    entries += [(validation_path, "run/validation.json"), (source_root / "us_index_mtf_daily.py", "producer/us_index_mtf_daily.py")]
    nikkei_source_folder = None
    for path in nikkei["input_hashes"]:
        p = Path(path)
        entries.append((p, "upstream_nikkei/" + p.name))
        nikkei_source_folder = p.parent.parent
    if nikkei_source_folder:
        for name in [f"validation_{analysis['trade_date']}.json", f"manifest_{analysis['trade_date']}.json"]:
            entries.append((nikkei_source_folder / name, "upstream_nikkei/" + name))
        for p in sorted((nikkei_source_folder / "raw").glob("nikkei225_*")):
            entries.append((p, "upstream_nikkei/raw/" + p.name))
    metadata = create_data_zip(out / "us_context_evidence_latest.zip", entries,
        bundle_type="verified_us_nikkei_context", as_of=analysis["trade_date"],
        readme="미국 완료장과 같은 한국 기준일 니케이 보조 자료. 니케이 과거 원천 누락은 보존하며 10분 계산은 누락 이후의 완전 연속 구간에서 새로 시작합니다. 원천을 채우거나 공백 전후를 연결하지 않습니다. Yahoo 지연 보조 원천입니다.",
        notes=analysis["limitations"])
    payload["evidence_zip"] = metadata
    write(out / "us_context_public.json", payload)
    write(out / "us_context_public_validation.json", {"status": "OK", "trade_date": payload["trade_date"],
        "source_artifacts_verified": len(validation["artifacts"]), "source_analysis_sha256": sha(analysis_path),
        "public_output_sha256": sha(out / "us_context_public.json"), "public_zip_sha256": metadata["sha256"],
        "source_gap_recovered": False, "nikkei_active_window": payload["nikkei_window"],
        "note": "현재 계산 구간만 검증 통과. 10월 15일 원천 누락 복구를 뜻하지 않음"})
    print(json.dumps({"status": "OK", "trade_date": payload["trade_date"], "us_session": payload["source_session_date"], "nikkei_window": payload["nikkei_window"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=Path.home() / "Desktop/trading_strength")
    parser.add_argument("--research", type=Path)
    args = parser.parse_args()
    prepare(args.repo_root, args.run_root, args.source_root, args.research)
