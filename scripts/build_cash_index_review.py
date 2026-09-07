"""Offline, source-pinned cash-index charts and EOD recovery. Never collects HTS data.

The numerical evidence is not a forecast. A separately reviewed editorial JSON is
required by publish_cash_index_review.py before publication.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SOURCE = Path(r"C:\Users\skylo\Desktop\trading_strength")
REST = Path(r"C:\Users\skylo\Desktop\restapi")
sys.path.insert(0, str(SOURCE))
import kospi_nikkei_mtf_daily as mtf

OHLCV = ["open", "high", "low", "close", "volume"]
AGG = dict(open="first", high="max", low="min", close="last", volume="sum")
mtf.TIMEFRAME_CONFIG["intraday_10m"] = dict(mtf.TIMEFRAME_CONFIG["intraday_15m"], label="10분봉", chart_bars=117)
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def write_json(p, obj):
    mtf.write_json(Path(p), obj)


def hash_manifest(path, root, key):
    obj = read_json(path)
    rows = obj[key]
    for r in rows:
        p = Path(r["path"])
        p = p if p.is_absolute() else root / p
        if not p.is_file() or mtf.sha256_file(p).lower() != r["sha256"].lower():
            raise ValueError(f"Source hash mismatch: {p}")
    return {"path": str(path), "sha256": mtf.sha256_file(path), "verified_files": len(rows)}


def read_frame(path, timezone=None):
    raw = pd.read_csv(path)
    column = "timestamp" if "timestamp" in raw else "date"
    index = pd.to_datetime(raw.pop(column), utc=True) if timezone else pd.to_datetime(raw.pop(column))
    if timezone:
        index = index.dt.tz_convert(timezone)
    f = raw[OHLCV].copy()
    f.index = pd.DatetimeIndex(index)
    if f.index.duplicated().any() or not f.index.is_monotonic_increasing:
        raise ValueError(f"Duplicate/unordered source: {path}")
    if f[OHLCV[:4]].isna().any().any():
        raise ValueError(f"Missing OHLC: {path}")
    if ((f.high < f[["open", "close", "low"]].max(axis=1) - .0001) |
            (f.low > f[["open", "close", "high"]].min(axis=1) + .0001)).any():
        raise ValueError(f"Invalid OHLC: {path}")
    return f


def ten_minute(f, key):
    """Preserve session OHLC; no fabricated bars across auctions or lunch."""
    pieces, excluded, folded = [], [], []
    for day, g in f.groupby(f.index.date):
        tz = f.index.tz
        def at(t):
            return pd.Timestamp(f"{day} {t}", tz=tz)
        if key == "KOSPI":
            sessions = [("09:00", "15:30")]
            expected = pd.date_range(at("09:00"), at("15:20"), freq="5min").union(pd.DatetimeIndex([at("15:30")]))
        elif key == "NIKKEI":
            sessions = [("09:00", "11:30"), ("12:30", "15:30")]
            expected = pd.date_range(at("09:00"), at("11:25"), freq="5min").union(pd.date_range(at("12:30"), at("15:25"), freq="5min"))
        else:
            # These pinned August/September sources contain no US early-close dates.
            sessions = [("09:30", "16:00")]
            expected = pd.date_range(at("09:30"), at("15:55"), freq="5min")
        missing = expected.difference(g.index)
        if len(missing):
            excluded.append({"date": str(day), "missing_5m": [str(x) for x in missing]})
            continue
        for start, end in sessions:
            h = g[(g.index >= at(start)) & (g.index <= at(end))].copy()
            terminal = at(end)
            if terminal in h.index:
                folded.append({"date": str(day), "terminal": str(terminal), "into": str(terminal-pd.Timedelta(minutes=10))})
                h.index = pd.DatetimeIndex([x-pd.Timedelta(microseconds=1) if x == terminal else x for x in h.index])
            out = h.resample("10min").agg(AGG).dropna(subset=["open", "high", "low", "close"])
            if not out.empty:
                pieces.append(out)
    result = pd.concat(pieces).sort_index()
    if result.index[-1].date() != f.index[-1].date():
        raise ValueError(f"Latest 10m session incomplete: {key}")
    if result.index.duplicated().any():
        raise ValueError("10m duplicate")
    last = result[result.index.date == result.index[-1].date()]
    original_last = f[f.index.date == f.index[-1].date()]
    for col, fun in AGG.items():
        a = original_last[col].iloc[0] if fun == "first" else original_last[col].iloc[-1] if fun == "last" else getattr(original_last[col], fun)()
        b = last[col].iloc[0] if fun == "first" else last[col].iloc[-1] if fun == "last" else getattr(last[col], fun)()
        if abs(a-b) > max(.0001, abs(a)*1e-10):
            raise ValueError(f"Resampling does not preserve {key} {col}: {a} vs {b}")
    return result, {"excluded_incomplete_dates": excluded, "terminal_prints_folded": folded,
                    "latest_10m_bars": len(last), "latest_session_ohlcv_preserved": True,
                    "auction_note": "KOSPI 15:20/15:30 종가 단일가 자료는 마지막 15:20 봉에 합침; 15:25 가상 봉 생성 안 함" if key == "KOSPI" else "세션 종료 인덱스 값은 직전 마지막 10분봉에 합침; 니케이 점심 분리"}


def swings(f, width=2):
    highs, lows = [], []
    for i in range(width, len(f)-width):
        row = f.iloc[i]
        chunk = f.iloc[i-width:i+width+1]
        if row.high == chunk.high.max() and row.high > f.high.iloc[i-width:i].max():
            highs.append({"date": str(f.index[i]), "price": float(row.high)})
        if row.low == chunk.low.min() and row.low < f.low.iloc[i-width:i].min():
            lows.append({"date": str(f.index[i]), "price": float(row.low)})
    return {"highs": highs[-8:], "lows": lows[-8:], "right_bars_for_confirmation": width}


def recover_eod(recovery, output, day):
    stage = recovery / day
    bridge_path = stage / f"eod_ocr_bridge_{day}.json"
    bridge = read_json(bridge_path)
    manual = Path(r"C:\Users\skylo\AppData\Local\Temp\codex-clipboard-0b82403e-93ac-4bdd-a330-e2fea6a2e47c.png")
    assert mtf.sha256_file(manual).lower() == "c9114faa169b493ce94044dc87e528837e126bd621ec698b006faeb4e9db928c"
    shutil.copy2(manual, output / "0441_F202609_user_verified.png")
    corrected = copy.deepcopy(bridge)
    corrected["open_interest"]["close_open_interest"] = 134903
    corrected["open_interest"]["volume"] = 124035
    corrected["open_interest"]["change"] = -12540
    corrected["open_interest"]["source"] = "사용자 제공 0441 원본 화면을 직접 판독한 정정값; 독립 거래소 검증 아님"
    corrected["manual_correction"] = {"raw_ocr_path": str(bridge_path), "raw_ocr_sha256": mtf.sha256_file(bridge_path),
        "original_values": bridge["open_interest"], "source": str(manual), "source_sha256": mtf.sha256_file(manual),
        "reason": "OCR 열 밀림: 6000 OI / 134903 volume -> 134903 OI / 124035 volume",
        "reference_contract_does_not_identify_0787_flow_expiry": True}
    corrected["warnings"] = ["RAW_OCR_OI_COLUMN_SHIFT_MANUALLY_CORRECTED", "0787_EXPIRY_DECOMPOSITION_UNAVAILABLE", "OPTION_DELTA_0_5_IS_NOT_OBSERVED_DELTA"]
    corrected["open_interest_history_csv"] = str(output / "contract_oi_corrected.csv")
    pd.DataFrame([{"trade_date": pd.Timestamp(day).strftime("%Y-%m-%d"), "contract": "F202609", "open_interest": 134903,
        "oi_change": -12540, "volume": 124035, "source_type": "USER_SCREEN_MANUALLY_REVIEWED", "source_sha256": mtf.sha256_file(manual)}]).to_csv(output / "contract_oi_corrected.csv", index=False, encoding="utf-8-sig")
    write_json(output / f"eod_ocr_bridge_corrected_{day}.json", corrected)
    parsed_path = stage / f"eod_0787_parsed_{day}.csv"
    p = pd.read_csv(parsed_path)
    assert not p.duplicated(["asof_date", "market", "unit", "investor"]).any()
    assert set(p.asof_date.astype(str)) == {day} and not p.net.isna().any()
    def net(market, unit, investor):
        r = p[(p.market == market) & (p.unit == unit) & (p.investor == investor)]
        assert len(r) == 1
        return int(r.net.iloc[0])
    foreign, institution = net("선물", "수량", "외국인"), net("선물", "수량", "기관계")
    assert (foreign, institution) == (10967, -10430)
    flow_path = REST / "input/k200_futures_investor_net_daily.csv"
    hist = pd.read_csv(flow_path).rename(columns={"trade_date": "date"})
    assert not hist.date.duplicated().any()
    date = pd.Timestamp(day).strftime("%Y-%m-%d")
    row = {"date": date, "foreign_net": foreign, "institution_net": institution,
        "scope": "Kiwoom 0787 KOSPI200 futures selection; expiry decomposition unavailable",
        "source": "Kiwoom 0787 saved screenshot; offline parse and manual review",
        "validation_status": "REVIEWED_0787_MANUAL_0441_DATE_GATE"}
    same = hist[hist.date == date]
    if len(same) and (float(same.foreign_net.iloc[0]) != foreign or float(same.institution_net.iloc[0]) != institution):
        raise ValueError("Conflicting flow history needs explicit correction")
    hist = pd.concat([hist[hist.date != date], pd.DataFrame([row])], ignore_index=True).sort_values("date")
    hist.to_csv(output / "all_expiry_flow_history.csv", index=False, encoding="utf-8-sig")
    shutil.copy2(parsed_path, output / parsed_path.name)
    windows = {}
    for n in [1, 3, 5, 15]:
        tail = hist.tail(n)
        windows[str(n)] = {"start": tail.date.iloc[0], "end": tail.date.iloc[-1], "observations": len(tail),
            "foreign": int(tail.foreign_net.sum()), "institution": int(tail.institution_net.sum())}
    return {"all_expiry_flow": windows, "contract_oi": [{"contract": "F202609", "oi": 134903, "change": -12540, "volume": 124035,
        "source_type": "사용자 제공 화면 직접 판독"}], "raw_ocr_sha256": mtf.sha256_file(bridge_path),
        "parsed_sha256": mtf.sha256_file(parsed_path), "history_before_sha256": mtf.sha256_file(flow_path),
        "daily_options": [{"investor": inv, "market": market, "quantity": net(market, "수량", inv), "amount_100m_krw": net(market, "금액", inv)}
            for inv in ["외국인", "기관계"] for market in ["콜옵션", "풋옵션"]],
        "scope_note": "0787 전월물 순매매 활동의 누적. 만기별 보유 잔고·평균단가·진짜 옵션 델타가 아니며 계약별 포지션 합산에 사용하지 않음."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--us-dir", type=Path, required=True)
    ap.add_argument("--recovery", type=Path, required=True)
    args = ap.parse_args()
    day = args.day
    output = args.recovery / "cash_index_review"
    output.mkdir(exist_ok=True)
    domestic = SOURCE / "output/index_multitimeframe" / day
    dv = read_json(domestic / f"validation_{day}.json")
    uv = read_json(args.us_dir / "validation.json")
    assert dv["trade_date"] == day and dv["can_use_for_decision"]
    assert uv["trade_date"] == day and uv["can_use_for_context"]
    audits = [hash_manifest(domestic / f"manifest_{day}.json", domestic, "files"), hash_manifest(args.us_dir / "validation.json", args.us_dir, "artifacts")]
    specs = [("KOSPI", "코스피 현물", "001", "Asia/Seoul", domestic / f"data/kospi_daily_{day}.csv", domestic / f"data/kospi_5m_{day}.csv"),
        ("NIKKEI", "니케이225", "^N225", "Asia/Tokyo", domestic / f"data/nikkei225_daily_{day}.csv", domestic / f"data/nikkei225_5m_{day}.csv")]
    for k, name, symbol in [("NASDAQ", "나스닥종합", "^IXIC"), ("SOX", "필라델피아 반도체", "^SOX"), ("DOW", "다우 산업평균", "^DJI")]:
        specs.append((k, name, symbol, "America/New_York", args.us_dir / f"{k}_daily.csv", args.us_dir / f"{k}_5m.csv"))
    result = {"trade_date": day, "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(), "analysis_basis": "CASH_INDEX_MTF",
        "source_manifests": audits, "indices": [], "script_sha256": mtf.sha256_file(Path(__file__)),
        "numerical_module_sha256": mtf.sha256_file(Path(mtf.__file__))}
    for key, name, symbol, timezone, daily_path, five_path in specs:
        daily = read_frame(daily_path)
        five = read_frame(five_path, timezone)
        ten, audit = ten_minute(five, key)
        expected_day = pd.Timestamp(day).date() if key in ("KOSPI", "NIKKEI") else pd.Timestamp(uv["source_session_date"]).date()
        assert daily.index[-1].date() == five.index[-1].date() == expected_day
        assert abs(float(daily.close.iloc[-1])-float(ten.close.iloc[-1])) < max(.05, float(daily.close.iloc[-1])*.00001)
        raw_frames = {"monthly": mtf.resample_ohlcv(daily, "ME"), "weekly": mtf.resample_ohlcv(daily, "W-FRI"), "daily": daily, "intraday_10m": ten}
        frames, analyses = {}, {}
        for tf, raw in raw_frames.items():
            cfg = mtf.TIMEFRAME_CONFIG[tf]
            frame = mtf.add_indicators(raw, cfg["ma_kind"], cfg["ma_periods"])
            partial = (tf == "monthly" and expected_day.month == frame.index[-1].month and expected_day < frame.index[-1].date()) or (tf == "weekly" and expected_day.weekday() < 4)
            scored = frame.iloc[:-1] if partial else frame
            frames[tf] = frame
            a = mtf.timeframe_analysis(scored, tf, "complete")
            if len(scored) > 3:
                a["returns_pct"]["3"] = round((float(scored.close.iloc[-1]) / float(scored.close.iloc[-4]) - 1) * 100, 3)
            a["current_incomplete_bar"] = ({"period_end": str(frame.index[-1]), "ohlc": frame.iloc[-1][OHLCV[:4]].to_dict()} if partial else None)
            a["confirmed_swings"] = swings(scored)
            analyses[tf] = a
            frame.to_csv(output / f"{key}_{tf}_{day}.csv", encoding="utf-8-sig", index_label="timestamp")
        # Short-term observed price contacts; not a trade-volume-at-price profile.
        chart_name = f"cash_{key}_mtf_{day}.png"
        fig, axes = plt.subplots(2, 2, figsize=(18, 11))
        for ax, tf in zip(axes.flat, raw_frames):
            cfg = dict(mtf.TIMEFRAME_CONFIG[tf])
            cfg["chart_bars"] = {"monthly": 72, "weekly": 78, "daily": 65, "intraday_10m": 117}[tf]
            status = "마지막 봉 진행 중 · 확정 판정에서 제외" if analyses[tf]["current_incomplete_bar"] else "완료 봉"
            mtf.plot_candles(ax, frames[tf], cfg, f"{cfg['label']} | {status}")
            if tf in ("daily", "intraday_10m"):
                recent = analyses[tf]["confirmed_swings"]
                for side, color in [("highs", "#c02030"), ("lows", "#1265c7")]:
                    if recent[side]:
                        p = recent[side][-1]["price"]
                        ax.axhline(p, color=color, linestyle="--", linewidth=1.1)
                        ax.text(.99, p, f" {'최근 확정 고점' if side=='highs' else '최근 확정 저점'} {p:,.2f} ", transform=ax.get_yaxis_transform(),
                            color=color, ha="right", va="bottom" if side=="highs" else "top", fontsize=8,
                            bbox=dict(facecolor="white", edgecolor=color, alpha=.88, pad=2))
        fig.suptitle(f"{name} ({symbol}) | 실제 현물 OHLC | 기준 세션 {expected_day}", fontsize=18, fontweight="bold")
        fig.text(.5, .012, "점선은 관측된 가격 고저점: 매물대·보유 원가 아님 | 10분봉은 보존된 5분봉 재표본화 | 시간축은 해당 거래소 현지 시각", ha="center", fontsize=10)
        fig.tight_layout(rect=(0, .035, 1, .95))
        fig.savefig(output / chart_name, dpi=150)
        plt.close(fig)
        result["indices"].append({"key": key, "name": name, "symbol": symbol, "source_session_date": str(expected_day), "timezone": timezone,
            "daily_source": {"path": str(daily_path), "sha256": mtf.sha256_file(daily_path), "rows": len(daily), "start": str(daily.index[0].date()), "end": str(daily.index[-1].date())},
            "intraday_source": {"path": str(five_path), "sha256": mtf.sha256_file(five_path), "rows": len(five), "start": str(five.index[0]), "end": str(five.index[-1])},
            "latest_daily_ohlc": daily.iloc[-1][OHLCV[:4]].to_dict(), "timeframes": analyses, "ten_minute_validation": audit, "chart": chart_name,
            "daily_last_20": [{"date": str(t.date()), **r[OHLCV[:4]].to_dict()} for t, r in daily.tail(20).iterrows()]})
    result["derivatives_evidence"] = recover_eod(args.recovery, output, day)
    kdaily = read_frame(specs[0][4])
    flow = pd.read_csv(output / "all_expiry_flow_history.csv")
    last15 = pd.to_datetime(flow.tail(15).date).dt.date.tolist()
    assert last15 == kdaily.index[kdaily.index.date >= last15[0]].date.tolist(), "15-day flow calendar gaps"
    result["derivatives_evidence"]["latest_15_trading_days_calendar_verified"] = True
    write_json(output / "cash_index_evidence.json", result)
    manifest = {"trade_date": day, "status": "OK_WITH_DISCLOSED_LIMITATIONS", "ready_for_editorial_review": True,
        "original_eod_status": "FAILED_STAGE_1_PRESERVED", "recovered_stages": ["OFFLINE_0787_PARSE_EXIT_0", "MANUAL_OI_CORRECTION", "ALL_EXPIRY_FLOW", "FIVE_CASH_INDICES_FOUR_TIMEFRAMES"],
        "skipped_stages": ["HTS_UI_RECOLLECTION", "LEGACY_FUTURES_PRICE_STRUCTURE_BY_USER_REQUEST", "AUTOMATIC_EXPIRY_HOLDING_INFERENCE"],
        "limitations": ["미국 지수 시세는 Yahoo 지연 보조 원천이며 독립 공식 가격 교차검증 없음", "진행 중 주봉·월봉은 확정 봉 판정에서 제외",
            "0787 전월물 순매매를 만기별 실제 보유 포지션으로 해석하지 않음", "이 지수 OHLCV로 실제 체결 매물대/강도/검증 승률을 산출하지 않음"],
        "artifacts": [{"path": p.name, "sha256": mtf.sha256_file(p), "bytes": p.stat().st_size} for p in sorted(output.iterdir()) if p.is_file() and p.name != "validation.json"]}
    write_json(output / "validation.json", manifest)
    print(json.dumps({"output": str(output), "indices": [{"key": i["key"], "close": i["latest_daily_ohlc"]["close"], "10m_bars_latest": i["ten_minute_validation"]["latest_10m_bars"], "excluded_dates": len(i["ten_minute_validation"]["excluded_incomplete_dates"])} for i in result["indices"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
