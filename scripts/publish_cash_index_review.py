"""Validate reviewed evidence and stage existing dashboard files; no push or UI."""
from __future__ import annotations
import argparse
import json
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
import build_cash_index_review as build


def primary_chart(evidence_dir, editorial, target):
    f = build.read_frame(evidence_dir / "KOSPI_daily_20260907.csv")
    f = build.mtf.add_indicators(f, "sma", (5, 10, 20)).tail(35)
    fig, ax = plt.subplots(figsize=(15, 9))
    cfg = dict(build.mtf.TIMEFRAME_CONFIG["daily"], chart_bars=35, chart_periods=(5, 10, 20))
    build.mtf.plot_candles(ax, f, cfg, "코스피 현물 · 일봉 구조 지도 · 2026-09-07")
    ax.set_ylim(6270, 7360)
    ax.set_xlim(-1, len(f)+.5)
    label_y = [7255, 7070, 6860, 6695, 6395]
    labels = ["중기 회복 확인\n7,211.87~7,216.62\n60일선 + 8/18 고점", "현재 상단 시험\n6,954.12~6,996.12\n8/21·8/27 고점", "가까운 반등 유지선\n6,867.91\n당일 저점 · 반복 지지 아님", "갭 하단 + 20일선\n6,727.59~6,746.14\n이탈 시 반등 약화", "반복 저점 핵심 지지\n6,400.81~6,439.49\n8/19·8/25·9/3 저점"]
    for level, y, label in zip(editorial["levels"], label_y, labels):
        color = "#bd1f32" if level["side"] == "resistance" else "#145cbc"
        low, high = level["low"], level["high"]
        if high > low:
            ax.axhspan(low, high, color=color, alpha=.11)
        ax.axhline(high, color=color, linewidth=1.2, linestyle="--")
        ax.annotate(label, xy=(len(f)-1, (low+high)/2), xytext=(len(f)+2, y), fontsize=10,
            color=color, va="center", annotation_clip=False,
            arrowprops=dict(arrowstyle="->", color=color),
            bbox=dict(boxstyle="round,pad=.45", facecolor="white", edgecolor=color))
    fig.text(.07, .96, "6,867.91 유지: 단기 반등 / 이탈·재회복 실패: 갭 되밀림 경계", fontsize=11)
    fig.text(.06, .025, "최근 35일 지지·저항 확대: 세로축 밖의 고저가는 생략 · 지수 포인트(선물 가격 아님)\n강도는 반복 가격 반응·이평 중첩의 상대 평가이며 체결 매물량·예측 성공률이 아닙니다. 전체 고저가는 월·주·일봉 원본 차트에 표시합니다.", fontsize=10)
    fig.subplots_adjust(left=.07, right=.72, top=.90, bottom=.14)
    fig.savefig(target, dpi=140)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence-dir", required=True, type=Path)
    p.add_argument("--editorial", required=True, type=Path)
    p.add_argument("--install", action="store_true")
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    evidence = build.read_json(a.evidence_dir / "cash_index_evidence.json")
    validation = build.read_json(a.evidence_dir / "validation.json")
    editorial = build.read_json(a.editorial)
    day = evidence["trade_date"]
    assert editorial["trade_date"] == validation["trade_date"] == day == "20260907"
    assert validation["ready_for_editorial_review"]
    for row in validation["artifacts"]:
        path = a.evidence_dir / row["path"]
        assert build.mtf.sha256_file(path) == row["sha256"], path
    assert len(editorial["indices"]) == len(evidence["indices"]) == 5
    indices = []
    for review in editorial["indices"]:
        index = next(x for x in evidence["indices"] if x["key"] == review["key"])
        for tf in ["monthly", "weekly", "daily", "intraday_10m"]:
            assert isinstance(review[tf], str) and len(review[tf]) > 10
            assert index["timeframes"][tf]["bar_status"] == "complete"
        assert index["ten_minute_validation"]["latest_session_ohlcv_preserved"]
        candidates = []
        for tf in ["monthly", "weekly", "daily", "intraday_10m"]:
            frame = pd.read_csv(a.evidence_dir / f"{index['key']}_{tf}_{day}.csv")
            columns = [c for c in frame if c in build.OHLCV[:4] or c.startswith(("sma", "ema"))]
            candidates.extend(frame[columns].to_numpy().flatten().tolist())
        for level in review["reference_levels"]:
            assert any(abs(float(x)-level) < .015 for x in candidates if pd.notna(x)), (index["key"], level)
        for source in [index["daily_source"], index["intraday_source"]]:
            assert build.mtf.sha256_file(Path(source["path"])) == source["sha256"], source["path"]
        indices.append({**index, "review": review})
    files_dir = a.evidence_dir.parent / "publication"
    files_dir.mkdir(exist_ok=True)
    main_chart = f"cash_KOSPI_structure_{day}.png"
    primary_chart(a.evidence_dir, editorial, files_dir / main_chart)
    payload = {"schema_version": "cash-index-review-v1", "analysis_basis": "CASH_INDEX_MTF", "as_of": "2026-09-07",
        "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(), "evidence_generated_at": evidence["generated_at"],
        "review_status": "AI_REVIEWED_CONDITIONAL_SCENARIOS", "execution_ready": False,
        "primary_market": "KOSPI", "review": editorial, "indices": indices, "primary_chart": main_chart,
        "derivatives_evidence": evidence["derivatives_evidence"], "data_validation": validation,
        "source_manifests": evidence["source_manifests"], "evidence_sha256": build.mtf.sha256_file(a.evidence_dir / "cash_index_evidence.json"),
        "review_sha256": build.mtf.sha256_file(a.editorial),
        "downloads": [{"label": "이번 현물 분석·차트·20개 시간대 CSV·수급·검증 ZIP", "file": f"cash_index_review_{day}.zip"},
            {"label": "분석 JSON", "file": "latest.json"}, {"label": "검증 결과", "file": f"cash_review_validation_{day}.json"}]}
    md = [f"# 현물 다중 시간대 분석 · {payload['as_of']}", "", editorial["headline"], "", editorial["summary"], "", editorial["cross_market"]]
    for i in indices:
        r = i["review"]
        md.extend(["", f"## {i['name']} · {i['source_session_date']}", "", r["view"]])
        for tf, name in [("monthly", "월봉"), ("weekly", "주봉"), ("daily", "일봉"), ("intraday_10m", "10분봉"), ("hold", "유지·회복"), ("failure", "훼손")]:
            md.extend(["", f"{name}: {r[tf]}"])
    md.extend(["", "## 누적 수급 보조 근거", "", editorial["flow_interpretation"], "", "## 한계", "", *[f"- {x}" for x in editorial["limitations"]]])
    (files_dir / f"cash_review_{day}.md").write_text("\n".join(md)+"\n", encoding="utf-8")
    build.write_json(files_dir / "latest.json", payload)
    build.write_json(files_dir / f"cash_review_validation_{day}.json", validation)
    for index in indices:
        shutil.copy2(a.evidence_dir / index["chart"], files_dir / index["chart"])
    with zipfile.ZipFile(files_dir / f"cash_index_review_{day}.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for item in a.evidence_dir.iterdir():
            if item.is_file():
                z.write(item, f"evidence/{item.name}")
        z.write(a.editorial, "review/editorial.json")
        z.write(files_dir / "latest.json", "review/latest.json")
        z.write(files_dir / main_chart, "review/"+main_chart)
    with zipfile.ZipFile(files_dir / f"cash_index_review_{day}.zip") as z:
        assert z.testzip() is None
    if a.install:
        backup = a.evidence_dir.parent / "before_publication"
        backup.mkdir(exist_ok=True)
        targets = [(build.REST / "output/supply_zone_latest.json", "rest_supply_zone_latest.json"),
            (root / "supply-zone/latest.json", "dashboard_supply_zone_latest.json"),
            (root / "index.html", "index.html"),
            (build.REST / "input/k200_futures_investor_net_daily.csv", "flow_history.csv")]
        for src, name in targets:
            if src.exists() and not (backup / name).exists():
                shutil.copy2(src, backup / name)
        existing_flow = build.REST / "input/k200_futures_investor_net_daily.csv"
        expected = evidence["derivatives_evidence"]["history_before_sha256"]
        new_flow = pd.read_csv(a.evidence_dir / "all_expiry_flow_history.csv").rename(columns={"date": "trade_date"})
        if build.mtf.sha256_file(existing_flow) != expected:
            actual = pd.read_csv(existing_flow)
            pd.testing.assert_frame_equal(actual.reset_index(drop=True), new_flow.reset_index(drop=True), check_dtype=False)
        else:
            new_flow.to_csv(existing_flow, index=False, encoding="utf-8-sig")
        original_day = build.SOURCE / "output/futures_options_eod" / day
        # Recovery artifacts are additive. The failed collection manifest is untouched.
        for name in [f"eod_0787_parsed_{day}.csv", f"eod_ocr_bridge_corrected_{day}.json", "contract_oi_corrected.csv", "0441_F202609_user_verified.png"]:
            dst = original_day / name
            if dst.exists() and not (backup / name).exists():
                shutil.copy2(dst, backup / name)
            shutil.copy2(a.evidence_dir / name, dst)
        build.write_json(original_day / f"eod_recovery_validation_{day}.json", validation)
        shutil.copy2(files_dir / "latest.json", build.REST / "output/supply_zone_latest.json")
        for item in files_dir.iterdir():
            if item.is_file():
                shutil.copy2(item, root / "supply-zone" / item.name)
    print(json.dumps({"staged_locally": a.install, "date": day, "publication_folder": str(files_dir),
        "files": [f"supply-zone/{x.name}" for x in files_dir.iterdir() if x.is_file()], "remote_uploaded": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
