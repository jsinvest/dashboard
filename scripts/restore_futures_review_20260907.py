"""Stage a human-reviewed futures-first report from preserved Sep 7 evidence.

No collectors, EOD stages, network requests, positions inferred by algorithm,
orders, or remote publication. Original failed EOD and raw inputs stay intact.
"""
from __future__ import annotations
import csv
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
REST = Path(r"C:\Users\skylo\Desktop\restapi")
SOURCE = Path(r"C:\Users\skylo\Desktop\trading_strength")
DAY = SOURCE / "output/futures_options_eod/20260907"
RECOVERY = SOURCE / "output/eod_recovery_20260907_210454"
OUT = ROOT / "supply-zone"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    context_path = OUT / "cash_context_20260907.json"
    context = read(context_path)
    assert context["as_of"] == "2026-09-07"
    assert context["data_validation"]["ready_for_editorial_review"]
    assert len(context["indices"]) == 5
    manifest_path = DAY / "eod_manifest_20260907.json"
    assert read(manifest_path)["trade_date"] == "20260907"
    preserved_manifest = RECOVERY / "original_collection/eod_manifest_20260907.json"
    assert preserved_manifest.is_file() and sha(preserved_manifest) == sha(manifest_path)
    bridge_path = DAY / "eod_ocr_bridge_corrected_20260907.json"
    assert read(bridge_path)["trade_date"] == "20260907"
    assert float(read(bridge_path)["futures_price"]) == 1109.75
    history_path = REST / "input/futures_f202609_daily.csv"
    history = rows(history_path)
    assert len({(x["trade_date"], x["contract_code"], x["session"]) for x in history}) == len(history)
    assert all(x["contract_code"] == "A0169000" and x["session"] == "regular" for x in history)
    hist = {x["trade_date"]: x for x in history}
    assert max(hist) == "2026-09-04", "Review date changed: re-read sources, do not reuse Sep 7 narrative"
    expected_anchors = {
        "2026-08-18": {"high":1144.90}, "2026-08-19": {"low":1003.65},
        "2026-08-21": {"high":1105.25}, "2026-08-25": {"low":1007.10},
        "2026-08-27": {"high":1109.40}, "2026-08-31": {"low":1026.25},
        "2026-09-03": {"low":1008.70},
        "2026-09-04": {"high":1063.85,"low":1042.30,"close":1052.50,"open_interest":147443,"volume":103413},
    }
    anchors = []
    for date, fields in expected_anchors.items():
        r = hist[date]
        raw = Path(r["source_png"])
        assert raw.is_file() and sha(raw) == r["source_sha256"].lower(), date
        for key, value in fields.items():
            assert float(r[key]) == value, (date, key)
        anchors.append({"date":date,"values":fields,"source":str(raw),"sha256":sha(raw)})

    flow_path = REST / "input/k200_futures_investor_net_daily.csv"
    flow_rows = rows(flow_path)
    assert len({x["trade_date"] for x in flow_rows}) == len(flow_rows)
    flow_rows.sort(key=lambda x:x["trade_date"])
    calendar = rows(RECOVERY / "cash_index_review/KOSPI_daily_20260907.csv")
    dates = [x["timestamp"][:10] for x in calendar if "2026-08-18" <= x["timestamp"][:10] <= "2026-09-07"]
    assert dates == [x["trade_date"] for x in flow_rows[-15:]] and len(dates) == 15
    flow = {}
    for n in (1,3,5,15):
        tail = flow_rows[-n:]
        flow[str(n)] = {"start":tail[0]["trade_date"],"end":tail[-1]["trade_date"],"observations":n,
            "foreign":int(sum(float(x["foreign_net"]) for x in tail)),
            "institution":int(sum(float(x["institution_net"]) for x in tail))}
    assert flow == context["derivatives_evidence"]["all_expiry_flow"]
    assert sha(DAY / "0441_F202609_user_verified.png") == "c9114faa169b493ce94044dc87e528837e126bd621ec698b006faeb4e9db928c"

    charts = []
    def source_image(file, target, title, kind="source", interpretation="", note="2026-09-07 저장 원본 직접 검토 · HTS 추정치는 실제 보유 잔고와 구분"):
        assert file.is_file() and file.stat().st_size > 1000
        charts.append({"file":target,"title":title,"kind":kind,"interpretation":interpretation,
            "source_note":note,"source_path":str(file),"sha256":sha(file)})

    source_image(DAY / "5605_KOSPI200최근월_일봉_20260907.png", "futures_daily_20260907.png", "KOSPI200 9월물 · 실제 키움 5605 일봉", "price",
        "큰 하락 뒤 하단을 높여 반등했지만, 과거 주요 고점을 모두 회복한 추세 전환과는 구분합니다.",
        "F202609 · 야간 포함 HTS 원본 그대로 · 차트 우측 1,110.65는 정규장 확정 종가 1,109.75와 다름 · 원본 확대는 이미지 클릭")
    source_image(DAY / "5605_KOSPI200최근월_10분봉_20260907.png", "futures_10m_20260907.png", "KOSPI200 9월물 · 실제 키움 5605 10분봉", "price",
        "9/3 저점 이후 고점·저점이 높아지는 단기 상승 구조입니다. 보관 화면의 야간 고가 1,110.95를 넘는 것과 정규장 주요 저항 재지지는 별개의 확인이에요.",
        "2026-09-07 19:30 보관 화면 · 야간 포함 · 표시 가격 1,110.65 / 화면 고가 1,110.95(19:10) · 9/8 실시간 아님")
    for original, target, title in [
        ("0790_누적_20260907.png","futures_0790_cumulative_20260907.png","0790 누적 · 전체 주체의 곡선 기울기"),
        ("0791_외국인_누적_1100_1200_20260907.png","futures_0791_foreign_20260907.png","0791 외국인 누적 · 위로 기울어진 합성 손익곡선"),
        ("0791_금융투자_누적_1100_1200_20260907.png","futures_0791_financial_20260907.png","0791 금융투자 누적 · 아래로 기울어진 합성 손익곡선"),
        ("0791_투신_누적_1100_1200_20260907.png","futures_0791_trust_20260907.png","0791 투신 누적 · 아래로 기울어진 합성 손익곡선"),
        ("0471_KOSPI200_일별_60일_20260907.png","futures_0471_20260907.png","0471 · 풋·콜 변동성 원본"),
        ("0441_F202609_user_verified.png","futures_0441_sep_20260907.png","0441 9월물 · 사용자 제공 정정 원본"),
    ]:
        source_image(DAY / original, target, title)
    source_image(Path(r"C:\Users\skylo\AppData\Local\Temp\codex-clipboard-76dd4be2-b789-4dfc-bfcd-f308f87478ec.png"),
        "futures_0441_dec_20260907.png", "0441 12월물 · 사용자 제공값 / 거래량과 OI 증감의 범위 차이 주의")

    def level(label, low, high, side, strength, reason, invalidation):
        return {"label":label,"low":low,"high":high,"range":f"{low:,.2f}"+(f"~{high:,.2f}" if high!=low else ""),
            "side":side,"level_type":"structural","structure_strength":strength,"strength":strength,
            "reason":reason,"invalidation":invalidation,"color":"#ef4444" if side in ("current","resistance") else "#3b82f6"}
    levels = [
        level("이전 고점·현재 돌파 시험",1105.25,1109.75,"current","중",
            "8/21 고가 1,105.25 · 8/27 고가 1,109.40 · 9/7 고가·종가 1,109.75. 과거 두 고점의 매도 압력을 다시 시험 중이며, 새 지지 전환은 별도 확인합니다.",
            "1,109.75 위 10분봉 마감 후 되돌림에서 유지; 다시 1,105.25 아래면 단기 돌파 실패 경계"),
        level("큰 반등 상단·상승 전환 경계",1144.90,1144.90,"resistance","중",
            "8/18 정규장 고가. 가장 가까운 저항 위의 큰 스윙 경계이며 반복 접촉 횟수가 많은 강한 매물대라고 단정하지 않습니다.",
            "1,144.90 위 정규장 종가와 이후 재지지 확인 시 큰 박스 상단 돌파 가설"),
        level("가까운 반등 유지선",1084.25,1084.25,"support","약",
            "9/7 정규장 저점. 당일 갭 상승의 상단 경계일 뿐, 여러 날 반복 지지로 확인된 자리는 아닙니다.",
            "10분봉 종가 이탈 후 되돌림에서 회복 실패 시 단기 반등 약화"),
        level("갭 하단 방어 기준",1063.85,1063.85,"support","중",
            "9/4 정규장 고가. 9/7 저점 1,084.25와 사이에 정규장 가격 공백이 생겼습니다. 아직 반복 재지지하지 않은 갭 하단 기준입니다.",
            "이탈·재회복 실패하면 갭 상승 전제 훼손; 1,042.30·1,026.25에서 다시 반응 확인"),
        level("반복 저점 핵심 방어대",1003.65,1008.70,"support","강",
            "8/19 저점 1,003.65 · 8/25 저점 1,007.10 · 9/3 저점 1,008.70. 세 날짜의 하단 반등 흔적이 겹칩니다. 현재가와 먼 구조 경계입니다.",
            "1,003.65 아래 마감 후 1,008.70 부근 되돌림이 저항으로 바뀌면 반복 하단 매수 전제 중단"),
    ]
    for item, reason, rule in zip(levels, [
        "8/21·8/27 이전 고점과 9/7 종가", "8/18 고가 · 단일 큰 스윙 경계",
        "9/7 당일 저점 · 반복 지지 아님", "9/4 고가 · 정규장 갭 하단",
        "8/19·8/25·9/3 세 저점 중첩"], [
        "1,109.75 위 마감·재지지", "1,144.90 위 종가·재지지",
        "1,084.25 종가 이탈·회복 실패", "1,063.85 이탈·재회복 실패",
        "1,003.65 이탈·되돌림 저항 전환"]):
        item.update(map_reason=reason, map_rule=rule)
    assessment = {
        "dashboard_conclusion":"9월물: 1,084.25 유지 시 단기 반등 우세 · 1,109.75 재지지부터 상방 연장 · 1,144.90 돌파는 큰 전환",
        "dashboard_conclusion_detail":"1,109.75 부근은 이전 고점 시험 구간입니다. 야간 보관 화면 1,110.65만으로 돌파 안착을 확정하지 않아요. 내일의 등락을 단정하기보다 유지선·돌파 실패·다음 구조 경계를 기준으로 뷰를 이어갑니다.",
        "headline":"외국인 누적 곡선과 최근 순매수는 상승 방향에 정렬. 금융투자·투신은 반대 기울기. 가격 상승과 9월물 OI 감소가 함께 나타나 신규 롱만으로 설명할 수 없습니다.",
        "stance":"단기 반등 / 큰 박스 상단 미돌파", "confidence":"중 · 검증 승률 아님", "levels":levels,
        "acceleration_title":"상승·하락 가속 조건 · 선물 9월물 기준", "acceleration_after_map":True,
        "acceleration_triggers":[
            {"label":"가까운 상방 연장","tone":"cancel","classification":"이전 고점의 지지 전환","condition":"1,109.75 위에서 10분봉 마감 후 되돌림을 견디는지 확인. 야간 1,110.95는 단기 고점 참고만 사용.","target":"다음 큰 구조 경계 1,144.90 관찰 · 바로 도달한다는 뜻 아님"},
            {"label":"더 큰 상승 가속 후보","tone":"cancel","classification":"큰 스윙 상단 돌파","condition":"1,144.90 위 정규장 종가 + 다음 되돌림 재지지. 거래량과 월물별 OI를 추가 확인.","target":"박스 상단 돌파·상방 우선으로 전환 · 상위 목표는 추가 가격 반응 확인 뒤 설정"},
            {"label":"약한 지지 이탈","structure_strength":"약","classification":"반등 약화 / 강한 하락 확정 아님","condition":"1,084.25 아래 10분봉 종가와 되돌림 회복 실패.","target":"1,063.85 갭 하단 시험 가능성"},
            {"label":"갭 상승 전제 훼손","structure_strength":"중","classification":"하방 우선 재평가","condition":"1,063.85 이탈 뒤 재회복 실패.","target":"1,042.30 · 1,026.25를 중간 반응 지점으로 재점검; 핵심 방어대까지 직행 가정 금지"},
            {"label":"강한 지지 이탈","structure_strength":"강","classification":"큰 하락 가속 위험","condition":"1,003.65 이탈 후 1,008.70 주변 되돌림까지 저항 전환.","target":"반복 저점 기반 반등 가설 중단 · 먼 구조 경계이며 현재 숏 진입선 아님"}
        ],
        "support_break_policy":{"strong":"반복 하단 매수 전제 중단","medium":"갭 상승 구조 약화","weak":"단기 반등 약화부터 확인", "confirmation":"한 번의 터치·꼬리만으로 돌파 판정하지 않음. 10분봉 마감 + 재시험이 단기 확인 기준이며 큰 경계는 정규장 종가도 확인. 이 규칙의 승률은 별도 검증 전입니다."},
        "scenarios":[
            {"tone":"neutral","condition":"1,084.25 위지만 1,109.75 재지지 전","target":"박스 상단 시험 · 추격보다 저항 반응 확인"},
            {"tone":"up","condition":"1,109.75 돌파·재지지","target":"단기 상방 유지, 1,144.90에서 다음 판단"},
            {"tone":"down","condition":"1,084.25 이탈·회복 실패","target":"단기 하방 우선, 1,063.85에서 다음 판단"}],
        "caution":"강·중·약은 확인된 가격 반응과 구조상 중요도의 상대 평가입니다. 승률이나 해당 가격의 체결 잔량이 아닙니다. 지수와 전체 월물 순매매는 확인 근거이며 개별 선물 지지선의 매수 주체를 입증하지 않습니다."
    }
    inference = {
        "as_of":"2026-09-07","mode":"누적 · HTS 추정","scope":"최근월물 기준 HTS 누적 손익곡선 직접 판독",
        "reference_range":"0791 화면에 실제 보이는 1,100~1,150", "institution_label":"금융투자·투신 · 기관 전체 합산 아님",
        "foreign":{"direction":"LONG","contracts":None,"average_price":None,"curve_basis":"표시 범위에서 합성 만기손익곡선이 우상향합니다. 가격 상승에 유리한 추정 구조이며 실제 보유 롱 계약수 확인과는 다릅니다."},
        "institution":{"direction":"SHORT","contracts":None,"average_price":None,"curve_basis":"금융투자와 투신의 합성곡선은 우하향합니다. 0790의 은행·보험은 반대 방향이어서 기관 전체를 동일한 숏 포지션으로 단정하지 않습니다.","components":[{"investor":"금융투자","direction":"SHORT"},{"investor":"투신","direction":"SHORT"},{"investor":"은행(0790)","direction":"LONG"},{"investor":"보험(0790)","direction":"LONG"}]},
        "recent_flow_alignment":"외국인 1·3·5·15거래일 선물 순매수와 곡선의 상승 기울기가 일치합니다. 기관계 순매도는 금융투자·투신의 하락 기울기와 정렬하지만 전체 기관 잔고를 뜻하지 않습니다.",
        "flow_proxy_comparison":"0787의 전월물 거래 활동과 0791의 최근월물 전환 시점 기준 추정 누적은 기간·범위가 다릅니다. 서로 합산하거나 평균단가를 역산하지 않습니다.",
        "limitation":"0791은 키움이 거래 수량·대금으로 추정한 포지션입니다. 실제 잔존 계약수·평균단가·옵션 델타는 확인 불가이며, 화면에 없는 누적 시작일을 임의로 만들지 않았습니다."
    }
    limitations = [
        "9/7 자료를 재검토한 게시본이며 9/8 실시간 분석이 아닙니다. 정규장 0441과 야간 포함 5605를 구분합니다.",
        "정규장 가격 CSV는 9/4까지이고 과거 일부 거래일·시가가 빠져 있습니다. 9/7은 사용자 0441 화면의 고가·저가·종가를 추가 대조했으며 없는 시가를 채우거나 새 선물 주봉·월봉을 만들지 않았습니다.",
        "레벨 근거는 8/18~9/7의 선택된 실제 고저점과 원본 차트입니다. 강도는 가격 구조 상대 평가이며 가격별 체결대금·실제 잔존 포지션이 입증된 강도가 아닙니다.",
        "0787 최근 15거래일(8/18~9/7)은 거래일 누락·중복 없이 대조했습니다. 전월물 순매매이므로 현재 9월물 실제 잔고·정확한 월물별 누적 포지션은 판단 불가입니다.",
        "12월물 사용자 화면의 OI 증가 24,715가 표시 거래량 6,549보다 큽니다. 두 수치의 집계 범위 차이가 해소되지 않아 롤오버 확정 수량이나 신규 롱 증거로 사용하지 않습니다.",
        "옵션 수량·금액의 부호 차이는 구성 변화로 달라질 수 있습니다. 가정 델타 0.5를 실제 델타로 사용하지 않습니다. 0471은 곡선 비교만 가능해 정확한 IV 숫자는 쓰지 않았습니다.",
        "지수 보조 분석은 국내·니케이 9/7, 미국 현물 9/4 완료 세션 기준입니다. 미국 Yahoo 시세는 지연 보조 원천이고, 미완료 주봉·월봉은 확정 판단에서 제외합니다.",
        "새 조건의 목표 도달 승률은 계산하지 않았습니다. execution_ready=false는 자동 실행 신호가 아니라 사람이 확인할 조건부 분석이라는 뜻입니다."
    ]
    payload = {
        "schema_version":"futures-options-review-v1","analysis_basis":"FUTURES_OPTIONS_WITH_INDEX_CONTEXT",
        "as_of":"2026-09-07","generated_at":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "review_status":"AI_REVIEWED_CONDITIONAL_SCENARIOS","execution_ready":False,
        "primary_market":"KOSPI200_FUTURES","futures_contract":"F202609","contract_code":"A0169000","current_price":1109.75,
        "display_reference_basis":"9/7 정규장 확정 화면 0441 · 사용자 제공값 직접 대조",
        "session_references":{"regular":{"trade_date":"2026-09-07","close":1109.75,"high":1109.75,"low":1084.25,"open":None},"overnight":{"snapshot_price":1110.65,"snapshot_high":1110.95,"snapshot_time":"2026-09-07 19:30 KST","source":"5605 보관 화면 / 야간 포함"}},
        "overall_assessment":assessment,"hts_0791_position_inference":inference,
        "derivatives_evidence":{**context["derivatives_evidence"],"all_expiry_flow":flow},
        "flow_interpretation":"외국인은 9/1~9/2 합계 11,344계약 순매도 뒤 9/3~9/7 세 거래일 21,837계약 순매수로 돌아섰습니다. 5일·15일 합계도 순매수여서 반등에 정렬하지만, 다음 날 상승을 자동 예측하는 규칙으로 쓰지 않습니다.",
        "options_interpretation":"외국인 콜 순매수·기관 콜 순매도는 반등 해석과 정렬합니다. 외국인 풋은 계약수 순매수지만 금액은 순매도여서 단순 풋 매도=강한 상방으로 단정하지 않습니다. 0471 우측의 풋 평균 IV가 콜보다 높은 모습은 하방 경계의 보조 단서로만 반영합니다.",
        "contract_observations":[
            {"contract":"F202609","code":"A0169000","close":1109.75,"volume":124035,"oi":134903,"oi_change":-12540,"status":"사용자 0441 직접 대조 · 전일 OI 차이 일치"},
            {"contract":"F202612","code":"A016C000","close":1111.00,"volume":6549,"oi":37352,"oi_change":24715,"status":"사용자 제공값 · OI 증가와 거래량 범위 충돌"}],
        "oi_interpretation":"9월물은 종가 +57.25포인트(+5.44%)인데 OI는 147,443→134,903으로 12,540계약 감소했습니다. 숏 환매와 만기 이동 가능성을 함께 열어 두며 신규 롱 유입으로 확정하지 않습니다. 12월물 수치 충돌 때문에 양 월물 증감을 합산해 롤오버 물량을 계산하지 않습니다.",
        "futures_structure":{
            "daily":"일봉 선호 해석은 큰 하락 뒤 하단이 높아지는 회복·박스 상단 시험입니다. 1,003.65→1,007.10→1,008.70의 반복 저점과 1,105.25~1,109.75의 이전 고점을 함께 봅니다. 1,144.90 돌파 전에는 큰 상승추세 복귀로 확대하지 않아요.",
            "intraday":"10분봉은 9/3 저점 뒤 고점과 저점을 높이며 단기 이평 위로 올라선 모습입니다. 가까운 상단 돌파 실패만으로 일봉 전체를 하방 확정하지 않고 1,084.25·1,063.85를 차례로 확인합니다.",
            "profile":"5605 일봉의 장기간 거래량 프로파일에는 넓은 누적 거래 구간이 보입니다. 넓은 막대 전체를 한 개의 강한 진입 지지대로 쓰지 않고, 반복 고저점과 갭 경계로 실행 관찰 지점을 좁혔습니다. 0791 곡선은 주체별 방향 확인용이며 각 선물 가격대의 보유물량 지도는 아닙니다.",
            "wave_limit":"엘리어트 세부 1~5·A~C 차수는 미확정입니다. 정규장 CSV의 누락 봉 때문에 임의 카운트를 덧그리지 않았으며 지수 월·주봉의 프랙탈 구조를 보조로 확인합니다. 지수 파동을 선물 파동으로 그대로 이식하지 않습니다."},
        "index_confirmation":"코스피와 니케이의 9/7 단기 반등은 선물 상승과 정렬하지만 주봉의 회복 확인은 덜 끝났습니다. 미국은 9/4 완료 자료에서 나스닥·다우와 반도체의 시간대별 강도가 엇갈려요. 따라서 지수는 선물의 단기 반등을 확인하되 1,144.90 돌파 전 큰 상승 전환을 확정하는 근거로 쓰지 않습니다.",
        "index_context_file":context_path.name,"charts":charts,"limitations":limitations,
        "downloads":[{"label":"선물 중심 분석 JSON","file":"latest.json"},{"label":"분석 요약","file":"futures_review_20260907.md"},{"label":"이번 검증 결과","file":"futures_review_validation_20260907.json"},{"label":"지수 보조 분석 JSON","file":context_path.name}],
    }
    validation = {"trade_date":"20260907","status":"OK_WITH_DISCLOSED_LIMITATIONS","ready_for_editorial_review":True,
        "original_eod_status":"FAILED_STAGE_1_PRESERVED","collection_rerun":False,
        "futures_price_history_latest":"2026-09-04","regular_latest_supplement":"2026-09-07 USER_0441",
        "flow_calendar_verified":dates,"expiry_holdings_verified":False,"december_oi_volume_consistent":False,
        "regular_oi_change_check":134903-int(float(hist["2026-09-04"]["open_interest"])) == -12540,
        "price_anchors":anchors,"flow_source":{"path":str(flow_path),"sha256":sha(flow_path)},
        "price_source":{"path":str(history_path),"sha256":sha(history_path)},
        "index_context_sha256":sha(context_path),"review_script_sha256":sha(Path(__file__)),
        "original_manifest":{"path":str(manifest_path),"sha256":sha(manifest_path),"unchanged_from_collection_backup":True},
        "corrected_bridge":{"path":str(bridge_path),"sha256":sha(bridge_path)},
        "chart_sources":[{"file":x["file"],"path":x["source_path"],"sha256":x["sha256"]} for x in charts],
        "limitations":limitations}
    assert validation["regular_oi_change_check"]
    payload["data_validation"] = validation
    # Back up this date-specific replacement before installing generated files.
    backup = RECOVERY / "before_futures_restore_20260908"
    assert (backup / "dashboard_supply_zone_latest.json").exists()
    for item in charts:
        shutil.copy2(item["source_path"], OUT / item["file"])
        assert sha(OUT / item["file"]) == item["sha256"]
    md = ["# 선물옵션 중심 분석 · 2026-09-07", "", assessment["dashboard_conclusion"], "", assessment["dashboard_conclusion_detail"], "", "## 지지·저항"]
    for x in levels:
        md.extend(["",f"- {x['label']} {x['range']} · 구조 {x['structure_strength']}: {x['reason']} / {x['invalidation']}"])
    md.extend(["", "## 누적 포지션", "", inference["foreign"]["curve_basis"], "", inference["institution"]["curve_basis"], "", payload["flow_interpretation"], "", payload["oi_interpretation"], "", "## 지수 보조", "", payload["index_confirmation"], "", "## 제한사항", "", *["- "+x for x in limitations]])
    (OUT / "futures_review_20260907.md").write_text("\n".join(md)+"\n", encoding="utf-8")
    write(OUT / "futures_review_validation_20260907.json", validation)
    write(OUT / "latest.json", payload)
    shutil.copy2(OUT / "latest.json", REST / "output/supply_zone_latest.json")
    assert read(OUT / "latest.json") == read(REST / "output/supply_zone_latest.json")
    print(json.dumps({"status":"LOCALLY_STAGED","as_of":payload["as_of"],"charts":len(charts),"flow":flow,
        "levels":len(levels),"index_context_retained":True,"remote_uploaded":False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
