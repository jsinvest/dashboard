"""Pinned offline evidence preparation. No HTS input, API login or publication."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REST = Path(r'C:\Users\skylo\Desktop\restapi')
TS = Path(r'C:\Users\skylo\Desktop\trading_strength')
DAY = TS / 'output/futures_options_eod/20260908'
WORK = REST / 'output/eod_repair_20260908_2019'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def rows(p):
    with Path(p).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    price_path = REST / 'input/futures_f202609_daily.csv'
    flow_path = REST / 'input/k200_futures_investor_net_daily.csv'
    prices, flow = rows(price_path), rows(flow_path)
    assert prices[-1]['trade_date'] == flow[-1]['trade_date'] == '2026-09-08'
    assert len({(x['trade_date'], x['contract_code']) for x in prices}) == len(prices)
    assert len({x['trade_date'] for x in flow}) == len(flow)
    for x in prices:
        assert float(x['low']) <= float(x['close']) <= float(x['high'])
        if x.get('source_png'):
            assert sha(x['source_png']).lower() == x['source_sha256'].lower()
    assert float(prices[-1]['close']) == 1098.4 and float(prices[-1]['oi_change']) == -34291
    assert sha(DAY/'0441_F202612_user_verified.png') == '27c0d75752208e940540cfde5250b75e4a7ceb29b2009939f8990fc43717de78'
    sums={str(n):dict(start=flow[-n]['trade_date'], end=flow[-1]['trade_date'],
                     foreign=int(sum(float(x['foreign_net']) for x in flow[-n:])),
                     institution=int(sum(float(x['institution_net']) for x in flow[-n:])))
          for n in (1,3,5,15)}
    parsed_path=DAY/'eod_0787_parsed_20260908.csv'
    parsed=rows(parsed_path)
    assert len({(x['asof_date'],x['market'],x['unit'],x['investor']) for x in parsed})==len(parsed)
    assert {x['asof_date'] for x in parsed}=={'20260908'}
    def net(m,u,i):
        selected=[x for x in parsed if (x['market'],x['unit'],x['investor'])==(m,u,i)]
        assert len(selected)==1
        return int(selected[0]['net'])
    options=[dict(investor=i,market=m,quantity=net(m,'수량',i),amount_100m_krw=net(m,'금액',i))
             for i in ('외국인','기관계') for m in ('콜옵션','풋옵션')]
    assert [(x['quantity'],x['amount_100m_krw']) for x in options]==[(4472,7),(6124,-15),(-4368,-25),(-1249,65)]
    evidence=dict(trade_date='20260908',original_eod_status='FAILED_STAGE_5_PRESERVED',
                  all_expiry_flow=sums,daily_options=options,
                  scope_note='0787 전체 월물 순매매 활동 누적입니다. 실제 9월물 잔존 포지션·평균단가가 아니며 0791 추정 손익곡선과 합산하지 않습니다.',
                  flow_source=dict(path=str(flow_path),sha256=sha(flow_path),rows=len(flow),start=flow[0]['trade_date']),
                  price_source=dict(path=str(price_path),sha256=sha(price_path),rows=len(prices),start=prices[0]['trade_date']),
                  parsed_source=dict(path=str(parsed_path),sha256=sha(parsed_path)),
                  raw_bridge_sha256=sha(DAY/'eod_ocr_bridge_20260908.json'))
    write(WORK/'derivatives_evidence.json',evidence)
    write(WORK/'contract_observations.json',[
        dict(contract='F202609',code='A0169000',close=1098.4,high=1138.7,low=1097.85,volume=125850,oi=100612,oi_change=-34291,
             status='0441 직접 대조 · 9/7 OI 134,903과 비교',source_png=str(DAY/'0441_close_snapshot_20260908.png')),
        dict(contract='F202612',code='A016C000',close=1100.2,high=1140.6,low=1099.75,volume=18158,oi=74318,oi_change=36966,
             status='사용자 제공값 · 두 화면 차이 +36,966이 당일 거래량보다 커 집계 범위 확인 필요',source_png=str(DAY/'0441_F202612_user_verified.png'))])
    print(json.dumps(evidence,ensure_ascii=False))


if __name__=='__main__':
    main()
