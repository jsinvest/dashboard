from pathlib import Path
import json,re,hashlib,math
from datetime import datetime

import argparse, sys
from zoneinfo import ZoneInfo
import leader_mapping_data as data
parser=argparse.ArgumentParser(description='Publish validated intraday leader maps; evening stages are optional context.')
parser.add_argument('--trade-date',required=True)
parser.add_argument('--source-root',type=Path,required=True)
parser.add_argument('--integration-dir',type=Path,required=True)
parser.add_argument('--calendar',type=Path,required=True)
parser.add_argument('--input',type=Path,default=Path('index.html'))
parser.add_argument('--output',type=Path,default=Path('index.html'))
args=parser.parse_args()
DATE=args.trade_date
assert re.fullmatch(r'\d{8}',DATE)
assert DATE==datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y%m%d'), 'Current-day sources required'
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
calendar=json.loads(args.calendar.read_text(encoding='utf-8-sig'))
assert calendar['trade_date']==DATE and calendar['status']=='VERIFIED' and calendar['is_regular_trading_day']
assert digest(calendar['raw_path'])==calendar['raw_sha256']
integrated=json.loads((args.integration_dir/'latest.json').read_text(encoding='utf-8'))
validation=json.loads((args.integration_dir/'validation_latest.json').read_text(encoding='utf-8'))
assert integrated['trade_date']==DATE and validation['status']=='OK'
assert digest(args.integration_dir/'latest.json')==validation['latest_sha256']
assert all(digest(p)==h for p,h in integrated['input_hashes'].items())
assert integrated['leader_validation']['content_status']=='OK', 'Leader content validation failed'
assert not integrated['leader_validation']['unaccounted'], 'Unaccounted source symbols need review'
data.DATE=DATE; data.BASE=str(args.source_root/'한국/55개섹터_주도주')
scans=sorted(args.source_root.glob(f'scan_result_{DATE}_*.csv'))
data.SCAN=str(scans[-1]) if scans else ''
ns=vars(data)
path,sector,stock,excluded=data.read_xlsx(DATE)
assert len(stock)>0 and len(sector)>0
assert not stock[[f'c{i}' for i in range(16)]].isna().any().any()
assert not stock.duplicated(['c5','c6']).any()
assert set(stock.c6)=={'KOSPI','KOSDAQ'}
assert digest(path)==integrated['leader_validation']['sha256']
source_time=datetime.fromtimestamp(Path(path).stat().st_mtime,ZoneInfo('Asia/Seoul'))
assert source_time.strftime('%Y%m%d')==DATE
clock=source_time.strftime('%H:%M'); iso=datetime.strptime(DATE,'%Y%m%d').strftime('%Y-%m-%d'); short=f'{int(DATE[4:6])}/{int(DATE[6:8])}'
scan,ss=data.scan_map(); scan_clock=datetime.fromtimestamp(scans[-1].stat().st_mtime,ZoneInfo('Asia/Seoul')).strftime('%H:%M') if scans else '자료 없음'
stats=data.sector_stats(stock)
dates=data.available_dates(); all_stats={}; history_hashes={}
for date in dates:
 hp,hs,st,ex=data.read_xlsx(date)
 assert not st[[f'c{i}' for i in range(16)]].isna().any().any(), f'History null: {date}'
 assert not st.duplicated(['c5','c6']).any(), f'History duplicate: {date}'
 all_stats[date]=data.sector_stats(st); history_hashes[date]=digest(hp)
cum=data.cumulative(all_stats,dates)
configs={m:[(prefix+'Center' if i==0 else prefix+str(i),v['sector'],'' if i==0 else '강도 비교') for i,v in enumerate(stats[m][:5])] for m,prefix in [('KOSPI','ks'),('KOSDAQ','kq')]}
daily={};links={};cards=[];mobile=[];summary={}
def j(o):return json.dumps(o,ensure_ascii=False)
for market,items in configs.items():
 center=items[0][0];nodes=[];edges=[];buttons=[]
 for i,(key,name,relation) in enumerate(items):
  stat=ns['find_sector'](stats,market,name)
  rows=ns['stock_rows'](stock,market,name,5,scan)
  for row in rows:row['v2']=row['v2'].replace('9/8',short)+f' · {scan_clock} 스캐너'
  daily[key]={'name':name,'score':f"시장별 비교순위 {stat['rank']}위 · {stat['sample']}종목 · {short} {clock} 장중",'stocks':rows}
  links[key]=[x[0] for x in items[1:]] if not i else [center]
  x,y,r=(300,180,78) if not i else [(115,65,52),(485,65,52),(115,300,52),(485,300,52)][i-1]
  label={'정유·석유제품·LPG':'정유·석유','가스·LNG·도시가스':'가스·LNG','기계·산업장비':'기계·장비','소프트웨어·IT서비스':'SW·IT','통신장비·광네트워크':'통신·네트워크','시험·인증·리서치':'시험·인증','은행·금융지주':'은행·금융','ESS·에너지저장':'ESS·저장','의료기기·진단':'의료·진단','전자부품·디스플레이':'전자·디스플레이','전력기기·전선·전력망':'전력기기·전선','자동차·일반부품':'자동차·부품'}.get(name,name)
  names=rows[0]['name'] if rows else '자료 없음'
  kicker=('단일 종목 집중' if stat['sample']==1 else '시장별 상대강도 후보') if not i else ('단일 종목 집중' if stat['sample']==1 else f"비교 {stat['rank']}위 · {stat['sample']}종목")
  nodes.append(f'<g class="eco-node {"leader-center" if not i else ""}" data-eco-sector="{key}" data-node-market="{market}" role="button" tabindex="0"><circle cx="{x}" cy="{y}" r="{r}"/><text class="eco-kicker" x="{x}" y="{y-24}">{kicker}</text><text class="eco-name" x="{x}" y="{y}">{label}</text><text class="eco-score" textLength="{min(len(names)*12,100)}" lengthAdjust="spacingAndGlyphs" x="{x}" y="{y+23}">{names}</text></g>')
  if i:
   dist=math.hypot(x-300,y-180); ux=(x-300)/dist; uy=(y-180)/dist
   edges.append(f'<line class="eco-leader-link eco-link-weak" data-eco-link="{center},{key}" x1="{300+ux*81}" y1="{180+uy*81}" x2="{x-ux*55}" y2="{y-uy*55}"/><text class="eco-link-label" x="{(300+x)/2}" y="{(180+y)/2-8}">{relation}</text>')
  buttons.append(f'<button type="button" data-eco-sector="{key}" data-node-market="{market}">{label} · {names}</button>')
 s=ns['find_sector'](stats,market,items[0][1])
 windows=' / '.join(f"{w}일 {sum(any(x['sector']==s['sector'] for x in all_stats[d][market][:5]) for d in dates[-w:])}/{min(w,len(dates))}회" for w in [3,5,20])
 note=f"{s['sector']}: {s['sample']}종목 중 {round(s['sample']*s['upPct']/100)}상승 · RS 중앙값 {s['medianRs']:+.2f}%p · 합산 {s['tradingValue']:,.1f}억원. 원자료 내 시장별 상대 비교이며 시장 전체 확정 주도 판단은 보류합니다. 종목 우선순위는 원본 주도점수 기준이며 거래대금 순위와 다릅니다. 운영 표본 내 상대순위이며 시장 전체 순위가 아닙니다. 최근 3/5/20일 TOP5 등장: {windows}. 확정 종가 지속성이 아닙니다."
 cards.append(f'<div class="eco-market-card" data-eco-market="{market}"><div class="eco-market-label"><b>{market}</b><span>{short} {clock} · 동반 강세와 단일 급등 구분</span></div><svg viewBox="0 0 600 365" role="img" aria-label="{market} 주도 후보 업종"><g class="eco-links">{"".join(edges)}</g>{"".join(nodes)}</svg><div class="eco-cross-note">{note}</div></div>')
 mobile.append(f'<div data-eco-market="{market}"><b>{market} · {items[0][1]}</b>{"".join(buttons)}</div>')
 passes=list(dict.fromkeys(x[1] for x in ss['pass'] if x[2]==market))
 summary[market]=[items[0][1],note,f'V2 품질통과 {len(passes)}종목','·'.join(passes),f'{len(dates)}거래일 누적',f'업종 생성 {clock} / V2 {scan_clock} · 시점 차이 있음']
summary['all']=[' · '.join(configs[m][0][1] for m in configs),'시장별 상대강도 순위 · 원본 사업분류 유지',f"V2 품질통과 {len(set(x[0] for x in ss['pass']))}종목",'코스피·코스닥 별도 교차 확인',f'{len(dates)}거래일 누적',f'{dates[0]}~{DATE} · 날짜별 1회 반영']
import os
html=args.input.read_text(encoding='utf-8')
def sub(pattern,repl):
 global html
 html,n=re.subn(pattern,lambda _:repl,html,count=1,flags=re.S)
 assert n==1,pattern
sub(r'<span class="daily-leader-date">.*?</span>',f'<span class="daily-leader-date">시장 기준일 {iso} · {clock} 생성본 · 종가 확정 미검증 · V2 {scan_clock} · 누적 {len(dates)}거래일</span>')
audit_text=f'원본 내용·해시 검증 통과 · {len(sector)}개 섹터 / {len(stock)}행 / 제외 {len(excluded)}행 · 누락·중복 0 · 운영 표본 {len(stock)+len(excluded)}종목 · V2 {ss["rows"]}행 중 당일 {ss["sameDate"]}행 · 장중 자료: 종가 확정·생성기 종료코드 미검증 · 원본 업종분류 유지 · 수급 0은 미조회/중립 구분 불가 · 신고가 합의·충돌 및 저녁 2단계·14단계 연구자료 제외 · 보완분류 후보 미혼합 · 스팩 사업섹터 제외'
sub(r'<div class="daily-v2-audit"><b>검증 상태</b>.*?</div>',f'<div class="daily-v2-audit"><b>검증 상태</b> · {audit_text}</div>')
sub(r'<div class="daily-leader-summary">.*?<div class="daily-relation-strip">.*?</div>',f'''<div class="daily-leader-summary"><div class="daily-leader-stat"><small>시장별 상대강도 후보</small><strong id="dailyLeaderConfirmed">{summary['all'][0]}</strong><span id="dailyLeaderConfirmedNote"></span></div><div class="daily-leader-stat"><small>당일 V2</small><strong id="dailyLeaderEmerging"></strong><span id="dailyLeaderEmergingNote"></span></div><div class="daily-leader-stat"><small>누적</small><strong id="dailyLeaderWatch"></strong><span id="dailyLeaderWatchNote"></span></div></div><div class="daily-ecosystem"><div class="daily-ecosystem-title"><b>시장별 주도 후보 · 업종을 눌러 우선 종목 보기</b><span>점선: 시장 내 업종 강도 비교 · 산업 연관이나 자금 이동을 뜻하지 않음</span></div><div class="daily-ecosystem-board">{''.join(cards)}</div><div class="daily-ecosystem-mobile">{''.join(mobile)}</div><div class="daily-sector-detail" id="dailySectorDetail"></div></div><div class="daily-relation-strip"><span>판정 기준</span><b>시장별 RS·상승비율·거래대금·거래 확산으로 비교</b><b>작은 표본의 급등과 다종목 동반 강세 구분</b></div>''')
sub(r'const DAILY_LEADER_SUMMARY = \{.*?\n\};',f'const DAILY_LEADER_SUMMARY = {json.dumps(summary,ensure_ascii=False,indent=2)};')
sub(r'const LEADER_CUMULATIVE_\d{8}=.*?;\s*for\(const market',f'const LEADER_CUMULATIVE_{DATE}={j(cum)};\nfor(const market')
html=re.sub(r'LEADER_CUMULATIVE_\d{8}',f'LEADER_CUMULATIVE_{DATE}',html)
sub(r'const DAILY_SECTOR_STOCKS_\d{8} = \{.*?\n\};\s*const DAILY_SECTOR_LINKS_\d{8}=.*?;',f'const DAILY_SECTOR_STOCKS_{DATE} = {json.dumps(daily,ensure_ascii=False,indent=2)};\nconst DAILY_SECTOR_LINKS_{DATE}={j(links)};')
html=re.sub(r'DAILY_SECTOR_STOCKS_\d{8}',f'DAILY_SECTOR_STOCKS_{DATE}',html)
html=re.sub(r'DAILY_SECTOR_LINKS_\d{8}',f'DAILY_SECTOR_LINKS_{DATE}',html)
html=html.replace("selectDailySector('ksNuclear','KOSPI')","selectDailySector('ksCenter','KOSPI')").replace("selectDailySector('kqNuclear','KOSDAQ')","selectDailySector('kqCenter','KOSDAQ')")
tops=[]
for m in configs:
 spans=''.join(f'<span>{s} <strong>{count}회</strong><small>'+ ' · '.join(f'{name} {n}회' for name,n in cum[m]['history'][s]['l'][:3])+'</small></span>' for s,count,t,r in cum[m]['frequency'][:5])
 tops.append(f'<div class="leader-cumulative-market"><b>{m} · 누적 TOP5</b><div class="leader-cumulative-items">{spans}</div></div>')
sub(r'<div class="daily-v2-audit"><b>누적 기준: .*?<div class="leader-cumulative-controls">',f'<div class="daily-v2-audit"><b>누적 기준: {short}까지 {len(dates)}거래일</b> · 확보한 날짜별 TOP15 등장횟수, TOP5·1위 횟수 별도 · 장중 생성본 포함 · 실제 확보 기간만 집계</div><div class="leader-cumulative-top">{"".join(tops)}</div><div class="leader-cumulative-controls">')
assert html.count('id="dailySectorDetail"')==1
assert all(digest(p)==h for p,h in integrated['input_hashes'].items()), 'Sources changed during build'
assert all(digest(Path(data.BASE)/f'sector_stock_leaders_{date}.xlsx')==h for date,h in history_hashes.items())
audit={'status':'INTRADAY_CONTENT_VALIDATED','trade_date':DATE,'source_time_kst':source_time.isoformat(),'source_sha256':digest(path),'rows':len(stock),'excluded':len(excluded),'history_start':dates[0],'history_end':DATE,'history_days':len(dates),'history_hashes':history_hashes,'calendar_sha256':calendar['raw_sha256'],'integration_data_status':validation['data_status'],'integration_sha256':validation['latest_sha256'],'new_high_used':False,'evening_stages_required':False,'producer_validation':integrated['leader_validation']['producer_validation'],'scan_rows':ss['rows'],'scan_same_day':ss['sameDate'],'scan_sha256':digest(scans[-1]) if scans else None,'centers':{m:{'sector':stats[m][0]['sector'],'name':stats[m][0]['leader']} for m in configs}}
args.output.write_text(html,encoding='utf-8')
out=args.output.parent/'leader-mapping';out.mkdir(exist_ok=True)
(out/'validation_latest.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(audit,ensure_ascii=False))
