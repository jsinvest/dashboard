"""Install the manually reviewed Sept 8 analysis locally. Never pushes or collects."""
import copy
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import matplotlib.pyplot as plt
import build_cash_index_review as build
from prepare_futures_review_20260908 import ROOT, REST, TS, DAY, WORK, sha, read, rows, write

OUT = ROOT / 'supply-zone'
EVIDENCE = WORK / 'cash_index_review'
DATE = '2026-09-08'
DAYKEY = '20260908'


def level(label, low, high, side, strength, reason, rule, short):
    return dict(label=label, low=low, high=high, side=side, level_type='structural',
                range=f'{low:,.2f}'+(f'~{high:,.2f}' if high!=low else ''),
                structure_strength=strength, strength=strength, reason=reason,
                invalidation=rule, map_reason=short, map_rule=rule,
                color='#ef4444' if side=='resistance' else '#3b82f6')


def main():
    now=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    old=read(WORK/'dashboard_before.json')
    assert old['as_of']=='2026-09-07' and old['analysis_basis']=='FUTURES_OPTIONS_WITH_INDEX_CONTEXT'
    ev=read(EVIDENCE/'cash_index_evidence.json')
    val=read(EVIDENCE/'validation.json')
    assert ev['trade_date']==val['trade_date']==DAYKEY and val['ready_for_editorial_review']
    for item in val['artifacts']:
        assert sha(EVIDENCE/item['path'])==item['sha256']
    derivative=ev['derivatives_evidence']
    for key in ('flow_source','price_source','parsed_source'):
        assert sha(derivative[key]['path'])==derivative[key]['sha256']
    history={r['trade_date']:r for r in rows(REST/'input/futures_f202609_daily.csv')}
    for date,field,value in [('2026-08-18','high',1144.9),('2026-08-21','high',1105.25),
                             ('2026-08-27','high',1109.4),('2026-08-27','low',1078.2),
                             ('2026-09-04','high',1063.85),('2026-09-07','low',1084.25),
                             ('2026-09-08','low',1097.85),('2026-09-08','high',1138.7),
                             ('2026-08-19','low',1003.65),('2026-08-25','low',1007.1),('2026-09-03','low',1008.7)]:
        assert abs(float(history[date][field])-value)<.001
    levels=[
        level('큰 박스 상단 · 재차 매도 반응',1138.7,1144.9,'resistance','중',
              '9/8 장중 고가 1,138.70에서 급히 밀렸고 8/18 고가 1,144.90은 넘지 못했습니다. 가까운 이전 고점 저항보다 위에 있는 큰 스윙 경계입니다.',
              '1,144.90 위 정규장 종가 + 되돌림 재지지 때 큰 상방 전환 재평가','9/8 고점과 8/18 큰 스윙 고점'),
        level('돌파 실패 뒤 첫 회복 관문',1105.25,1109.75,'resistance','중',
              '8/21 고가 1,105.25, 8/27 고가 1,109.40, 9/7 고가·종가 1,109.75. 오늘 장중 통과했지만 1,098.40으로 마감해 지지 전환에 실패했습니다.',
              '1,109.75 위 10분봉 마감·재지지 전 단기 하방 조정 우선','이전 두 고점 + 9/7 종가 · 오늘 재이탈'),
        level('바로 아래 당일 저점',1097.85,1097.85,'support','약',
              '오늘 정규장 저점이며 종가보다 0.55포인트 아래입니다. 반복 방어가 확인된 누적 지지대가 아니라 현재 하락이 멈추는지 보는 첫 지점입니다.',
              '10분봉 종가 이탈 뒤 재회복 실패 → 1,084.25 시험','9/8 저점 · 1회 관측 / 종가 근접'),
        level('전일 갭 상승의 윗 경계',1084.25,1084.25,'support','약',
              '9/7 정규장 저점입니다. 오늘 저점은 이보다 높아 일봉 반등 전체가 무너진 것은 아니지만 이 선을 잃으면 전일 급등의 방어력이 약해집니다.',
              '이탈·재회복 실패 → 1,078.20을 거쳐 1,063.85 점검','9/7 저점 · 여러 날 반복 방어 아님'),
        level('중간 파동 반응점',1078.2,1078.2,'support','약',
              '8/27 정규장 저점입니다. 1,084.25 아래에서 확인할 중간 파동 흔적이며 이 한 선을 강한 지지대로 과대평가하지 않습니다.',
              '반등 실패 시 다음 주요 경계 1,063.85','8/27 저점 · 중간 관찰점'),
        level('갭 반등 구조의 핵심 경계',1063.85,1063.85,'support','중',
              '9/4 고가와 9/7 저점 사이의 정규장 갭 하단입니다. 가격 공백은 매물대가 아니며 이 경계가 저항으로 바뀌면 갭 반등 전제가 훼손됩니다.',
              '이탈·재회복 실패 → 1,052.50 / 1,042.30 차례로 점검','9/4 고가 · 갭 하단 / 반복 지지 아님'),
        level('반복 저점 · 먼 핵심 방어대',1003.65,1008.7,'support','강',
              '8/19 1,003.65, 8/25 1,007.10, 9/3 1,008.70의 세 저점이 모입니다. 최근 16거래일 안의 세 번의 일봉 하단 반응이며 현재가와 먼 구조 지지입니다.',
              '1,003.65 이탈 뒤 1,008.70 재시험이 저항이면 큰 반등 가설 중단','서로 다른 세 날짜의 반복 하단 반응')]
    # Keep the minor 1,078.20 swing inside scenario text, so the compact map
    # still shows the more material gap floor among its nearest 3 supports.
    levels=[x for x in levels if x['low']!=1078.2]
    assessment=dict(
        dashboard_conclusion='9월물 1,098.40: 1,109.75 회복·재지지 전 단기 하방 조정 우세 · 1,097.85 이탈 시 1,084.25 시험',
        dashboard_conclusion_detail='장중 1,138.70까지 올랐지만 이전 고점대 아래로 밀려 저가 부근 마감했습니다. 단기 상승 파동은 꺾였고, 일봉 반등 전체는 1,084.25·1,063.85가 남아 있어 별도로 봅니다. 지지 이탈 후 되돌림이 저항으로 바뀔 때 다음 구간으로 뷰를 이어갑니다.',
        headline='외국인 최근 3·5일 순매수와 상승에 유리한 누적 추정 곡선은 남아 있지만, 오늘 가격과 니케이 급락이 충돌합니다. 수급만으로 다음 날 상방을 유지하지 않습니다.',
        stance='단기 하방 조정 / 일봉은 박스·회복 구조 안', confidence='가격 구조 근거 · 확정 승률 아님', levels=levels,
        acceleration_title='이탈 강도와 상·하방 가속 조건 · 9월물 가격',acceleration_after_map=True,
        acceleration_triggers=[
            dict(label='첫 하방 연장',structure_strength='약',classification='작은 지지 이탈 · 강한 붕괴 아님',condition='1,097.85 아래 10분봉 마감 후 되돌림 회복 실패.',target='1,084.25에서 반응 확인. 되찾으면 이탈 실패로 분류'),
            dict(label='하방 속도가 붙을 조건',structure_strength='약 → 중',classification='전일 저점 이탈 + 갭 구간 진입',condition='1,084.25 이탈·재회복 실패, 이어 1,078.20도 지키지 못할 때.',target='1,063.85 갭 하단. 정규장 공백이지만 야간 거래는 있어 빈 매물 구간으로 단정하지 않음'),
            dict(label='일봉 반등 훼손',structure_strength='중',classification='갭 하단의 저항 전환',condition='1,063.85를 이탈하고 되돌림에서 회복하지 못할 때.',target='1,052.50·1,042.30부터 점검. 먼 1,003.65까지 직행한다고 가정하지 않음'),
            dict(label='단기 하방 뷰 해제',tone='cancel',classification='이전 고점의 지지 전환',condition='1,109.75 위 10분봉 마감 후 1,105.25~1,109.75 재지지.',target='1,138.70~1,144.90 재시험. 1,105.25 아래 복귀하면 돌파 실패'),
            dict(label='더 큰 상승 전환 후보',tone='cancel',classification='큰 스윙 상단 돌파',condition='1,144.90 위 정규장 종가와 이후 재지지. 만기별 거래량·OI 범위를 함께 확인.',target='큰 박스 상단 돌파로 재평가. 위쪽 목표는 추가 실제 파동 확인 후 설정'),
            dict(label='강한 하단 붕괴',structure_strength='강',classification='반복 저점 구조 무효화',condition='1,003.65 이탈 후 1,008.70까지 되돌림이 저항으로 전환.',target='반복 하단 반등 가설 중단. 현재 바로 앞의 진입 신호가 아닌 먼 구조 경계')],
        support_break_policy=dict(strong='반복 하단 반등 가설 중단',medium='갭 반등의 구조 훼손',weak='작은 파동의 하방 연장부터 확인',confirmation='한 번의 체결·꼬리보다 10분봉 마감과 재시험을 확인합니다. 큰 경계는 정규장 종가도 봅니다. 이 조건의 도달 승률을 새로 검증한 것은 아닙니다.'),
        scenarios=[dict(tone='down',condition='1,109.75 회복·재지지 전',target='단기 하방 조정 우선 / 1,097.85·1,084.25 반응'),dict(tone='up',condition='1,109.75 회복·재지지',target='1,138.70~1,144.90까지 상단 재시험'),dict(tone='neutral',condition='1,084.25 유지하나 회복 관문 미통과',target='일봉 반등 속 단기 조정·박스')],
        caution='강·중·약은 반복 가격 반응과 구조 중요도의 상대 평가입니다. 실제 가격별 잔존 계약수나 예측 성공률이 아닙니다. 가격지도에는 가까운 지지·저항 각각 최대 3개를 표시하며, 먼 핵심 방어대는 가속 조건과 전체 근거 펼치기에 있습니다. 약한 지지 이탈을 큰 추세 붕괴로 확대하지 않습니다.')
    inference=copy.deepcopy(old['hts_0791_position_inference'])
    inference.update(as_of=DATE,reference_range='0790 실제 표시 1,090.08~1,110.08 / 0791 상세 실제 1,100~1,150',
                     recent_flow_alignment='외국인 최근 1·3·5·15일 순매수와 추정 곡선 우상향은 정렬하지만, 오늘 종가 하락과 충돌합니다. 금융투자·투신의 곡선은 하락에 유리한 기울기이며 기관계 최근 순매도와 정렬합니다.',
                     limitation='0791은 실제 잔고가 아닌 추정 곡선입니다. 상세 화면의 입력 1,100~1,200과 실제 표시 1,100~1,150이 달라 실제 축만 읽었습니다. 현재가 주변은 0790으로 교차 확인했습니다. 정확한 계약수·평균단가·델타는 추정하지 않습니다.')
    inference['foreign']['curve_basis']='0790의 현재가 주변과 0791 상세에서 합성 만기손익곡선이 우상향합니다. 외국인은 가격 상승에 유리한 추정 구조이지만, 현재 손익값이 음수라는 사실과 방향 기울기는 서로 다른 정보입니다.'
    inference['institution']['curve_basis']='0790·0791의 금융투자와 투신은 우하향합니다. 은행·보험은 반대 기울기여서 기관 전체의 확정 순숏 잔고로 표현하지 않습니다.'
    flow_text='외국인 9/8 +1,288, 최근 3일 +20,048, 5일 +15,018, 연속 15거래일(8/19~9/8) +21,220계약입니다. 기관계는 같은 기간 -4,553 / -22,289 / -17,486 / -20,108계약입니다. 매수 누적은 남아 있지만 외국인 당일 순매수는 전일 +10,967보다 작고 가격은 하락했습니다. 매수 잔존과 단기 매수 압력 둔화를 구별합니다.'
    option_text='외국인 콜은 +4,472계약·+7억원으로 수량과 금액이 모두 순매수입니다. 풋은 +6,124계약인데 금액은 -15억원으로 엇갈립니다. 기관은 콜 -4,368계약·-25억원, 풋 -1,249계약·+65억원입니다. 행사가·만기·체결단가 구성이 달라질 수 있어 단순 콜-풋 계약수나 가정 델타 0.5로 전체 순롱·순숏을 계산하지 않습니다. 0471은 우측 풋 평균 IV가 콜보다 높은 모습만 보조로 확인했습니다.'
    oi_text='9월물은 1,109.75→1,098.40으로 -11.35포인트(-1.02%), OI는 134,903→100,612로 -34,291계약입니다. 거래량은 124,035→125,850으로 약 1.46% 증가해 거래 급증을 동반한 하락이라고 과장할 수 없습니다. 12월물은 1,111.00→1,100.20, OI 37,352→74,318입니다. 만기 이동·기존 포지션 청산이 섞일 가능성은 있지만 12월물 OI 화면 차이 +36,966이 거래량 18,158보다 커 정확한 롤오버 수량이나 신규 숏/롱 수량은 판정하지 않습니다. 원본 OCR의 -46,831은 9/4와 비교한 값이어서 전일 변화에 사용하지 않았습니다.'
    limitations=[
        '기준은 9/8 정규장 15:45 선물 화면입니다. 이후 야간 현재가는 수집하지 않았으며 실시간 가격이 아닙니다.',
        '가격 57행·수급 56행(6/12~9/8)의 검증된 저장자료를 사용했습니다. 과거 일부 거래일이 빠져 있어 전체 구간을 연속 57/56거래일이라고 하지 않습니다. 최근 15일은 국내 완료 일봉 달력과 일치합니다.',
        '0441 원본 판독과 사용자 12월물 화면을 사용했습니다. 거래소 공식 월물 가격·OI와 독립 대조한 자료는 아닙니다. 원본, SHA256, 정정 전후 기록을 보존했습니다.',
        '12월물 OI 차이와 거래량의 범위 충돌은 남아 있습니다. 두 만기를 합산한 실제 롤오버·보유계약수는 계산하지 않았습니다.',
        '0787은 전체 월물 활동이며 0791은 최근월물 전환 시점을 기준으로 한 HTS 추정 누적입니다. 만기별 실제 포지션과 평균단가는 별도로 확인해야 합니다.',
        '지지 강도는 가격 반응·파동·갭 경계를 종합한 상대 평가입니다. 5605의 거래량 프로파일은 선택 봉 수·야간 포함 설정에 영향을 받으며 보유물량을 의미하지 않습니다.',
        '기존 EOD는 화면 71건 수집 뒤 5단계에서 실패했습니다. 실패 로그는 보존했고 실패 후처리만 복구했습니다. 전체 배치·HTS 화면 자동조작을 재실행하지 않았습니다.',
        '원장 누락·숫자 오독·오래된 전일 비교를 막는 회귀검사는 통과했지만 새 설정의 다음 전체 실수집 성공까지 검증한 것은 아닙니다.',
        '코스피·니케이는 9/8, 미국 현물은 9/4 완료 세션입니다. 미국 휴장으로 같은 세션을 다시 사용하며 새 미국 관측일로 중복 누적하지 않습니다. 진행 월·주봉은 확정 판단에서 제외합니다.',
        '새 구간 도달 조건의 적중률은 이번에 산출하지 않았습니다. 해외 차트 추가 자체를 승률 향상으로 주장하지 않습니다.']
    charts=[]
    specs=[('5605_KOSPI200최근월_일봉_20260908.png','daily','price','5605 실제 선물 일봉 · 120봉 표시','큰 하락 뒤 하단이 높아진 회복 구간이지만 오늘 고점 돌파를 유지하지 못했습니다. 넓은 거래량 프로파일과 좁은 실행 관찰선을 구별합니다.'),
           ('5605_KOSPI200최근월_10분봉_20260908.png','10m','price','5605 실제 선물 10분봉 · 600봉','9/3 이후 상승 뒤 9/8 13:05 고점 1,138.70에서 밀려 단기 이평과 이전 상단 아래로 내려왔습니다. 장중 과매도는 반등 가능성이지만 지지 회복의 증거는 아닙니다.'),
           ('0790_누적_20260908.png','0790','source','0790 누적 · 현재가 주변의 주체별 곡선','외국인 우상향 / 금융투자·투신 우하향. 은행·보험은 우상향으로 기관 내 차이가 있습니다.'),
           ('0791_외국인_누적_1100_1200_20260908.png','0791_foreign','source','0791 외국인 추정 누적','입력 범위가 아니라 실제 보이는 1,100~1,150의 우상향 곡선을 읽었습니다. 현재가 1,098.40 주변은 0790으로 확인합니다.'),
           ('0791_금융투자_누적_1100_1200_20260908.png','0791_financial','source','0791 금융투자 추정 누적','실제 표시 구간의 합성곡선은 우하향으로 하락에 유리한 추정 구조입니다.'),
           ('0791_투신_누적_1100_1200_20260908.png','0791_trust','source','0791 투신 추정 누적','금융투자와 같은 우하향 기울기입니다. 기관 전체의 확정 잔고와 구별합니다.'),
           ('0471_KOSPI200_일별_60일_20260908.png','0471','source','0471 KOSPI200 변동성 · 60일','우측 풋 평균 IV가 콜보다 높은 곡선 관계를 보조 확인합니다. 정확한 최신 IV 숫자는 읽을 수 없어 사용하지 않습니다.'),
           ('0441_close_snapshot_20260908.png','0441_sep','source','0441 9월물 · 정규장 원본','종가 1,098.40 / 거래량 125,850 / 미결제약정 100,612. 구조 판독과 셀 판독을 교차 대조했습니다.'),
           ('0441_F202612_user_verified.png','0441_dec','source','0441 12월물 · 사용자 제공 10분 차트','종가 1,100.20 / 미결제약정 74,318. 전일 화면과의 차이가 당일 거래량보다 커 정확한 OI 이동 물량은 보류합니다.')]
    for source,key,kind,title,interpretation in specs:
        p=DAY/source
        assert p.is_file()
        dest=f'futures_{key}_{DAYKEY}.png'
        charts.append(dict(file=dest,title=title,kind=kind,interpretation=interpretation,
                           source_note='키움 저장 원본 · 2026-09-08 / 임의 파동·가상 가격을 덧그리지 않음',source_path=str(p),sha256=sha(p)))
    validation=dict(trade_date=DAYKEY,status='OK_WITH_DISCLOSED_LIMITATIONS',ready_for_editorial_review=True,
                    original_eod_status='FAILED_STAGE_5_PRESERVED',collection_rerun=False,
                    futures_price_history_latest=DATE,flow_calendar_verified=True,
                    expiry_holdings_verified=False,december_oi_volume_consistent=False,
                    regular_oi_change_check=True,source_manifests=ev['source_manifests'],
                    sources=[derivative[k] for k in ('flow_source','price_source','parsed_source')],
                    chart_sources=charts,limitations=limitations,review_script_sha256=sha(__file__))
    manifest_path=DAY/'eod_manifest_20260908.json'
    original_manifest=read(manifest_path)
    assert original_manifest['trade_date']==DAYKEY
    validation['original_manifest']=dict(path=str(manifest_path),sha256=sha(manifest_path),generated_at=original_manifest['generated_at'])
    validation['original_validation']=dict(path=str(DAY/'eod_validation_20260908.txt'),sha256=sha(DAY/'eod_validation_20260908.txt'))
    validation['recovery_tests']=dict(regressions_passed=9,full_eod_reexecuted=False,live_collection_after_fix_verified=False)
    payload=dict(schema_version='futures-options-review-v1',analysis_basis='FUTURES_OPTIONS_WITH_INDEX_CONTEXT',
                 as_of=DATE,generated_at=now,review_status='AI_REVIEWED_CONDITIONAL_SCENARIOS',execution_ready=False,
                 primary_market='KOSPI200_FUTURES',futures_contract='F202609',contract_code='A0169000',current_price=1098.4,
                 display_reference_basis='9/8 정규장 0441 원본 직접 대조',
                 session_references=dict(regular=dict(trade_date=DATE,close=1098.4,high=1138.7,low=1097.85,open=None),overnight=None),
                 overall_assessment=assessment,hts_0791_position_inference=inference,derivatives_evidence=derivative,
                 flow_interpretation=flow_text,options_interpretation=option_text,oi_interpretation=oi_text,
                 contract_observations=read(WORK/'contract_observations.json'),
                 futures_structure=dict(daily='선호 해석은 큰 하락 이후 반복 하단에서 반등한 박스 안의 조정입니다. 1,003.65→1,007.10→1,008.70의 하단 구조는 유지됐지만 1,144.90을 넘지 못했습니다. 1,084.25·1,063.85 이탈 여부가 최근 갭 반등 지속을 가릅니다.',
                    intraday='10분봉 상승 가지는 장중 고점 이후 저점·단기 이평을 빠르게 이탈했습니다. 지금의 하방 조정은 다음 날 방향을 자동 확정한 것이 아니라 1,109.75 회복·재지지까지 유지하는 구간 뷰입니다.',
                    profile='5605 일봉의 거래량 프로파일은 넓은 구간에 거래가 누적됐음을 보여 줍니다. 해당 구간 전체를 단일 지지선으로 쓰지 않고 반복 저점·갭 경계로 나눴습니다. 0791은 주체별 가격 민감도의 확인값이지 각 가격의 잔존 매수물량이 아닙니다.',
                    wave_limit='일봉은 회복 가지 안의 눌림을 선호하되 상단에서 끝난 B/X 반등이라는 대안을 둡니다. 1,109.75 회복 후 1,144.90 돌파·재지지가 상방 구조 개선, 1,063.85 이탈·회복 실패는 조정 확대 근거입니다. 누락 일봉·정규장/야간 범위 차이로 정확한 1~5·A~C 차수는 강제하지 않습니다. 코스피 월·주봉을 선물 차수로 그대로 옮기지 않습니다.'),
                 index_confirmation='코스피는 7,171.52까지 올랐다가 6,954.52로 마감해 6,996.12 돌파를 유지하지 못했고, 니케이는 65,600.42를 잃고 65,269.33으로 마감했습니다. 선물의 단기 하방 조정과 정렬합니다. 다만 미국은 새 세션이 없는 9/4 자료이며 나스닥·다우 월주봉 상승과 SOX 주일봉 조정이 엇갈려 큰 하락 확정 근거로 확대하지 않습니다.',
                 index_context_file=f'cash_context_{DAYKEY}.json',charts=charts,limitations=limitations,data_validation=validation,
                 recovery_note='9/8 원본 71건 수집 뒤 5단계 실패 기록은 보존했습니다. 전체 재수집 없이 0441 판독·전일 비교·수급 누적과 필요한 차트 후처리를 복구한 검토본입니다.',
                 downloads=[dict(label='선물 중심 분석 JSON',file='latest.json'),dict(label='분석 요약',file=f'futures_review_{DAYKEY}.md'),dict(label='검증 결과',file=f'futures_review_validation_{DAYKEY}.json'),dict(label='지수 보조 JSON',file=f'cash_context_{DAYKEY}.json')])
    cash_review=copy.deepcopy(read(OUT/'cash_context_20260907.json')['review'])
    cash_review.update(trade_date=DAYKEY,reviewed_at=DATE,
        headline='코스피 6,954.52: 6,996.12 회복·재지지 전 단기 조정 우세 · 6,867.91 이탈은 갭 반등 약화',
        summary='장중 7,171.52까지 올랐지만 종가는 6,954.52로 당일 저가 6,951.78에 가깝습니다. 8월 고점 6,996.12 돌파에 실패했고 120일선 6,984.32도 다시 잃었습니다. 월봉의 장기 상승 배경과 주봉 조정이 공존하며 당장 큰 상승 재개로 보지 않습니다.',
        cross_market='니케이의 전일 저점 65,600.42 이탈과 오후 급락은 국내 단기 조정의 확인 근거입니다. 미국은 9/7 휴장으로 9/4 완료 세션을 재사용했습니다. 나스닥·다우의 큰 상승 배경과 SOX 주·일봉 조정이 혼재하므로 해외 신호를 하나의 상방 점수로 더하지 않습니다.',
        flow_interpretation=flow_text,limitations=limitations)
    cash_review['elliott']=dict(preferred='7월 29일 5,262.77 이후 회복 과정에서 9월 3일 6,439.49부터 오른 가지가 9월 8일 고점 이후 눌리는 가설을 우선합니다. 월봉 장기 상승 배경은 있으나 주봉 20주선 아래 조정이 남아 있습니다.',
        alternative='7,171.52에서 회복 가지가 끝난 B/X 반등이며 다음 하락이 시작됐다는 대안입니다. 6,867.91 이탈은 단기 경고, 6,439.49 이탈은 9월 상승 가지 훼손, 6,400.81 아래 재회복 실패는 반복 저점대 붕괴입니다.',
        confirmation='6,996.12 회복·재지지 → 7,171.52 고점 재시험 → 7,192.39~7,216.62 돌파·재지지 때 회복 가설을 강화합니다. 이 순서를 상승 3파 확정으로 바꾸지 않습니다.',
        invalidation='5,262.77 이탈은 7월 저점부터의 큰 회복 가설 무효화입니다. 가까운 손절선과 구별합니다.',rule_check='월·주·일·10분봉을 함께 보되 차수는 조건부입니다. 일반 충격파의 1·4파 겹침 금지를 유지하고, 쐐기 모양만으로 예외를 적용하지 않습니다.')
    cash_review['levels']=[dict(low=x[0],high=x[1],side=x[2],label=x[3],strength=x[4],evidence=x[5],condition=x[6]) for x in [
        (7192.39,7216.62,'resistance','중기 회복 관문','중 · 60일선과 큰 고점','9/8 60일선 7,192.39와 8/18 고가 7,216.62.','7,171.52 회복 후 돌파·재지지 때 중기 회복 신뢰도 개선'),
        (6984.32,6996.12,'resistance','첫 회복 구간','중 · 120일선과 이전 고점','120일선 6,984.32, 8/27 고가 6,996.12. 오늘 통과 후 종가 재이탈.','6,996.12 위 마감·재지지 → 7,171.52 재시험'),
        (6951.78,6951.78,'support','당일 저점','약 · 반복 방어 아님','9/8 저점이며 종가보다 2.74포인트 아래.','10분봉 이탈·회복 실패 → 6,867.91'),
        (6867.91,6867.91,'support','전일 갭 반등 유지선','약 · 전일 저점','9/7 저점. 일봉 갭 위 방어 경계.','이탈·재회복 실패 → 6,746.14~6,760.33'),
        (6746.14,6760.33,'support','갭 하단과 20일선','중 · 구조·이평 중첩','9/4 고가 6,746.14, 오늘 20일선 6,760.33.','구간 하단을 잃으면 일봉 회복 약화 / 하위 파동 재점검'),
        (6400.81,6439.49,'support','반복 저점 핵심 방어','강 · 세 날짜 저점 반응','8/19·8/25·9/3 저점이 모입니다.','6,400.81 이탈 후 재회복 실패는 반복 하단 반등 가설 중단')]]
    kr=next(x for x in cash_review['indices'] if x['key']=='KOSPI')
    kr.update(view='단기 하방 조정 / 큰 틀은 박스·회복',monthly='완료 8월 월봉은 장기 12·24개월선 위지만 3개월선 아래입니다. 6월 급등 이후 조정이며 진행 중인 9월 봉으로 상승 재개를 확정하지 않습니다.',
              weekly='완료 9/4 주봉 종가 6,687.21은 10주선 6,929.67·20주선 7,371.70 아래입니다. 이번 주 고점을 높였어도 아직 진행 봉이므로 주봉 추세 전환을 확정하지 않습니다.',
              daily='고가 7,171.52에서 밀려 6,954.52 마감. 이전 고점 6,996.12와 120일선 6,984.32 위 안착 실패입니다. 20일선 6,760.33 위인 일봉 반등 구조는 아직 남아 있습니다.',
              intraday_10m='오후 고점 이후 작은 눌림 저점 7,115.82와 단기 이평을 잃고 급락했습니다. 이 저점은 이미 이탈한 과거 지점이지 지금의 아래 지지선이 아닙니다. 6,951.78 유지·6,996.12 회복을 나눠 봅니다.',
              hold='6,996.12 회복·재지지 전 단기 조정 우선. 회복하면 7,171.52, 이후 7,192.39~7,216.62 점검.',failure='6,951.78 이탈 → 6,867.91. 전일 저점도 잃으면 6,746.14~6,760.33 갭 하단·20일선 점검.',reference_levels=[6951.78,6996.12,6867.91,7171.52,7192.39,7216.62,6746.14,6760.33,6439.49,6400.81])
    nr=next(x for x in cash_review['indices'] if x['key']=='NIKKEI')
    nr.update(view='주봉 박스 / 단기 반등 실패',monthly='완료 8월 종가 66,311.93은 12·24개월선 위지만 3개월선 66,912.09 아래입니다. 장기 상승 배경과 6월 고점 이후 조정을 함께 봅니다.',
              weekly='완료 9/4 종가 65,020.94는 5·10주선과 20주선 65,470.97 아래입니다. 이번 주 봉은 진행 중이고 월봉 강세만으로 주봉 조정을 무시하지 않습니다.',
              daily='9/8 고가 66,791.84에서 저가·종가 65,269.33까지 밀렸습니다. 전일 저점 65,600.42와 20일선 66,336.44를 잃어 단기 반등 실패에 무게가 실립니다.',
              intraday_10m='오후 작은 파동 저점 66,424.53과 단기 이평 이탈 뒤 낙폭이 확대됐습니다. RSI 과매도만으로 바닥을 확정하지 않습니다. 점심 휴장은 분리하고 종가 단일 값은 마지막 봉에 반영했습니다.',
              hold='65,600.42 회복·재지지 전 단기 약세 우선. 회복 후 66,336.44, 66,791.84~66,954.69 순서로 확인.',failure='65,269.33 이탈 후 회복 실패 시 65,020.94와 63,772.80을 차례로 관찰. 국내 방향은 국내 지지 이탈로 최종 확인.',reference_levels=[65600.42,66336.44,66791.84,66954.69,65269.33,65020.94,63772.8])
    # US completed session is unchanged. Revalidate every preserved reference
    # against the newly source-hashed evidence, not by copying the old date.
    indices=[]
    for r in cash_review['indices']:
        i=next(x for x in ev['indices'] if x['key']==r['key'])
        candidates=[]
        for tf in ('monthly','weekly','daily','intraday_10m'):
            f=pd.read_csv(EVIDENCE/f'{i["key"]}_{tf}_{DAYKEY}.csv')
            cols=[c for c in f if c in build.OHLCV[:4] or c.startswith(('sma','ema'))]
            candidates.extend(f[cols].to_numpy().flatten())
        for p in r['reference_levels']:
            assert any(abs(float(x)-p)<.02 for x in candidates if pd.notna(x)), (i['key'],p)
        indices.append({**i,'review':r})
    cash_chart=f'cash_KOSPI_structure_{DAYKEY}.png'
    f=build.read_frame(EVIDENCE/f'KOSPI_daily_{DAYKEY}.csv').tail(35)
    f=build.mtf.add_indicators(build.read_frame(EVIDENCE/f'KOSPI_daily_{DAYKEY}.csv'),'sma',(5,10,20)).tail(35)
    fig,ax=plt.subplots(figsize=(15,9))
    build.mtf.plot_candles(ax,f,dict(build.mtf.TIMEFRAME_CONFIG['daily'],chart_bars=35,chart_periods=(5,10,20)),f'코스피 현물 · 일봉 구조 · {DATE}')
    ax.set_ylim(6270,7360); ax.set_xlim(-1,len(f)+.5)
    for l,y in zip(cash_review['levels'],[7280,7130,7000,6860,6690,6410]):
        c='#bd1f32' if l['side']=='resistance' else '#145cbc'
        ax.axhspan(l['low'],l['high'],color=c,alpha=.10); ax.axhline(l['high'],color=c,ls='--',lw=1)
        label=l['label']+'\n'+f"{l['low']:,.2f}"+(f"~{l['high']:,.2f}" if l['low']!=l['high'] else '')+'\n'+l['strength']
        ax.annotate(label,xy=(len(f)-1,(l['low']+l['high'])/2),xytext=(len(f)+2,y),fontsize=9,color=c,va='center',annotation_clip=False,arrowprops=dict(arrowstyle='->',color=c),bbox=dict(boxstyle='round,pad=.4',fc='white',ec=c))
    fig.text(.06,.96,'6,996.12 회복·재지지 전 단기 조정 우세 / 선물 가격이 아닌 코스피 지수',fontsize=11)
    fig.text(.06,.025,'최근 35일 구조 확대 · 세로축 밖 고저가 생략 · 전체 차트는 아래 4개 시간대 원본 참고\n강도는 반복 가격 반응·구조·이평의 상대 평가이며 체결 잔량·승률이 아닙니다.',fontsize=10)
    fig.subplots_adjust(left=.07,right=.72,top=.90,bottom=.14); fig.savefig(OUT/cash_chart,dpi=140);plt.close(fig)
    cash=dict(schema_version='cash-index-review-v1',analysis_basis='CASH_INDEX_MTF',as_of=DATE,generated_at=now,
              review_status='AI_REVIEWED_CONDITIONAL_SCENARIOS',execution_ready=False,primary_market='KOSPI',
              review=cash_review,indices=indices,primary_chart=cash_chart,derivatives_evidence=derivative,
              source_manifests=ev['source_manifests'],data_validation=val,
              oi_note='월물별 OI와 범위 충돌은 위 선물옵션 본문에서 구분했습니다. 현물 지수 판단으로 대체하지 않습니다.',
              downloads=[dict(label='지수 분석 JSON',file=f'cash_context_{DAYKEY}.json'),dict(label='5개 지수 차트·20개 시간대 CSV·검증 ZIP',file=f'cash_context_{DAYKEY}.zip')])
    for i in indices: shutil.copy2(EVIDENCE/i['chart'],OUT/i['chart'])
    with zipfile.ZipFile(OUT/f'cash_context_{DAYKEY}.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in EVIDENCE.iterdir():
            if p.is_file(): z.write(p,p.name)
    for i in charts:
        shutil.copy2(i['source_path'],OUT/i['file']); assert sha(OUT/i['file'])==i['sha256']
    write(OUT/payload['index_context_file'],cash)
    validation['index_context_sha256']=sha(OUT/payload['index_context_file'])
    write(OUT/f'futures_review_validation_{DAYKEY}.json',validation)
    md=['# 선물옵션 분석 · '+DATE,'',assessment['dashboard_conclusion'],'',assessment['dashboard_conclusion_detail'],'','## 지지·저항']
    md.extend('\n- '+l['label']+' '+l['range']+' · '+l['strength']+': '+l['reason']+' / '+l['invalidation'] for l in levels)
    md.extend(['','## 누적 수급과 월물 분리','',flow_text,'',option_text,'',oi_text,'','## 지수 보조','',payload['index_confirmation'],'','## 검증 범위','',*['- '+x for x in limitations]])
    (OUT/f'futures_review_{DAYKEY}.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    write(OUT/'latest.json',payload)
    shutil.copy2(OUT/'latest.json',REST/'output/supply_zone_latest.json')
    # Keep the source publication bundle self-contained for the next explicit
    # upload; a JSON that references dashboard-only images is not sufficient.
    bundled={x['file'] for x in charts} | {x['chart'] for x in indices} | {
        cash_chart,payload['index_context_file'],f'cash_context_{DAYKEY}.zip',
        f'futures_review_{DAYKEY}.md',f'futures_review_validation_{DAYKEY}.json'}
    for name in bundled:
        shutil.copy2(OUT/name,REST/'output'/name)
        assert sha(OUT/name)==sha(REST/'output'/name)
    print(json.dumps(dict(status='LOCAL_ONLY',date=DATE,price=1098.4,levels=len(levels),charts=len(charts),indices=len(indices)),ensure_ascii=False))


if __name__=='__main__': main()
