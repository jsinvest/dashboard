"""Preserve reports, import validated Hankyung lists and build sourced earnings periods."""
import argparse, copy, hashlib, json, re
from pathlib import Path
from collections import Counter
from datetime import datetime
from collect_hankyung_daily import parse
from update_report_dashboard import dedupe_key, rebuild_summary

ROOT=Path(__file__).resolve().parents[1]
def read(p): return json.loads(p.read_text('utf-8'))
def write(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2) if p.name=='latest.json' else json.dumps(d,ensure_ascii=False,separators=(',',':')), 'utf-8')
def canon(r): return json.dumps(r,ensure_ascii=False,sort_keys=True)
def main(run,messages,apply=False):
    v=read(run/'validation.json'); assert v['status']=='PASS'
    original={n:read(ROOT/n) for n in ['report_data.json','report_signal_data.json']}
    db=copy.deepcopy(original['report_data.json']); sig=copy.deepcopy(original['report_signal_data.json'])
    seen={dedupe_key(r) for r in db['details']}
    signals={k:{dedupe_key(r) for r in sig[k]} for k in ['up','down']}
    added=Counter(); held=[]; parsed=[]
    from urllib.parse import urlparse,parse_qs
    for source in v['sources']:
        raw=Path(source['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==source['sha256']
        q=parse_qs(urlparse(source['url']).query); day=q['sdate'][0]
        direction='up' if q['skinType'][0]=='stock_good' else 'down'
        rows,_=parse(raw,day,direction,source['url']); assert len(rows)==source['count']
        for r in rows:
            if r['validation_issue']: held.append(r); continue
            parsed.append(r)
            row={'날짜':r['date'],'종목코드':r['code'],'종목명':r['name'],'목표주가':r['price'],
                 '제목':r['title'],'내용':'한경 컨센서스 목록 기준 · 증권사 원문 대조 미완료',
                 '기관':r['broker'],'상향건수':None,'전체건수':None,'출처':'한경 컨센서스','원문URL':r['source']}
            key=dedupe_key(row)
            if key not in seen: db['details'].append(row);seen.add(key);added['reports']+=1
            else: added['duplicates']+=1
            if key not in signals[direction]:
                sig[direction].append({**row,'구분':r['status'],'방향':direction.upper(),'목표주가변동률_pct':None})
                signals[direction].add(key);added[direction]+=1
    db['summary']=rebuild_summary(db['details'])
    db['meta'].update(detail_count=len(db['details']),summary_count=len(db['summary']),generated_at=v['collected_at'],
                      last_merge_source='한경 컨센서스',last_source_checked_through=max(v['days']))
    if added['reports']: db['meta']['last_merge_added']=added['reports']
    sig['meta'].update(generated_at=v['collected_at'],up_signal_count=len(sig['up']),down_signal_count=len(sig['down']))
    for direction in ['up','down']: sig['meta'][direction+'_category_counts']=dict(Counter(r['구분'] for r in sig[direction]))
    for n,key in [('report_data.json','details'),('report_signal_data.json','up'),('report_signal_data.json','down')]:
        current=db if key=='details' else sig
        assert not (Counter(map(canon,original[n][key]))-Counter(map(canon,current[key])))
        assert len(current[key])==len({dedupe_key(r)+(r.get('구분',''),) for r in current[key]})
    assert all(re.fullmatch(r'\d{6}',r['종목코드']) for r in db['details'])
    # A period is anchored only by an explicit earnings quarter and timestamp, never calendar month.
    prior_periods=read(ROOT/'report-periods/data.json') if (ROOT/'report-periods/data.json').exists() else {}
    events={(e['code'],e['period']):e for e in prior_periods.get('events',[])}
    for p in read(messages):
        t=p['text']; code=re.search(r'\((\d{6})\)',t.split('\n')[0])
        quarter=re.search(r'📌 최근 실적\s*\n(\d{2})\.([1-4])Q\s*\|',t)
        stamp=re.search(r'※ (\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}',t)
        links=[x for x in p.get('links',[]) if 'dart.fss.or.kr/' in x or 'kind.krx.co.kr/' in x]
        if not (code and quarter and stamp and links and re.search(r'잠정실적|분기보고서|반기보고서|사업보고서',t)): continue
        if stamp[1]!=p['date_kst'][:10]: continue
        period=f'20{quarter[1]}-Q{quarter[2]}'
        key=(code[1],period); e=dict(code=code[1],period=period,date=stamp[1],source=p['url'],disclosure=links[0],basis='DAJU 공시 요약 기준 · 공시 원문 독립 대조 미완료')
        if key not in events or e['date']<events[key]['date']: events[key]=e
    periods={'events':sorted(events.values(),key=lambda e:(e['code'],e['date'])),
             'overrides':{'https://t.me/daju_dart/77660':{'period':'2026-Q2','date':None,'report_date':'2026-08-19',
              'source':'https://www.newspim.com/news/view/20260819000114','basis':'동일 제목·기관·목표가의 리포트 소개에서 2Q26 확인 · 발표일 미확인'}},
             'collected_at':v['collected_at'],'messages_sha256':hashlib.sha256(messages.read_bytes()).hexdigest(),'note':'실적 대상 분기와 발표 이후 구간을 구분합니다. 동일 날짜는 발표 전후 확인 불가입니다. 미확인 자료는 별도 보존합니다.'}
    periods['overrides']={**prior_periods.get('overrides',{}),**periods['overrides']}
    # Preserve previously published daily rows even when another provider covers the same day.
    daily=read(run/'before.json')
    daily_original=copy.deepcopy(daily)
    current_daily=read(ROOT/'daily-reports/latest.json')
    for day,d in current_daily['days'].items():
        dest=daily['days'].setdefault(day,copy.deepcopy(d))
        for field in ['reports','held_reports']:
            seen_rows={canon(r) for r in dest.get(field,[])}
            for r in d.get(field,[]):
                if canon(r) not in seen_rows:
                    dest.setdefault(field,[]).append(r);seen_rows.add(canon(r))
    for day in v['days']:
        d=daily['days'].setdefault(day,{'reports':[],'held_reports':[]})
        d.setdefault('held_reports',[])
        known={tuple(r.get(k) for k in ('date','code','name','price','title','broker')) for r in d['reports']}
        for r in [x for x in parsed if x['date']==day]:
            key=tuple(r[k] for k in ('date','code','name','price','title','broker'))
            if key not in known: d['reports'].append(r);known.add(key)
        held_known={canon(r) for r in d.get('held_reports',[])}
        for r in [r for r in held if r['date']==day]:
            if canon(r) not in held_known:
                d.setdefault('held_reports',[]).append(r);held_known.add(canon(r))
        d.update(up=sum(r['status']=='목표주가 상향' for r in d['reports']),down=sum(r['status']=='목표주가 하향' for r in d['reports']),
                 source_count=len(d['reports'])+len(d['held_reports']),source_scope='확보 원문 합산 · 한경 및 기존 자료',duplicate_count=0)
    daily.update(latest_date=max(k for k,d in daily['days'].items() if d['reports']),collected_at=v['collected_at'])
    for old in [daily_original,current_daily]:
        for day,d in old['days'].items():
            for field in ['reports','held_reports']:
                assert not (Counter(map(canon,d.get(field,[])))-Counter(map(canon,daily['days'][day].get(field,[]))))
    outputs={'report_data.json':db,'report_signal_data.json':sig,'report-periods/data.json':periods,'daily-reports/latest.json':daily}
    audit=run/'report_merge'/datetime.now().strftime('%Y%m%d_%H%M%S_%f');audit.mkdir(parents=True,exist_ok=True)
    for n,d in original.items():write(audit/(n+'.before.json'),d)
    for n,d in outputs.items():
        write(audit/(n.replace('/','_')+'.proposed.json'),d)
        if apply:write(ROOT/n,d)
    result=dict(status='PASS',applied=apply,added=dict(added),held=len(held),existing=len(original['report_data.json']['details']),total=len(db['details']),latest=max(r['날짜'] for r in db['details']),events=len(events),preserved=True)
    write(audit/'validation.json',result);print(json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--messages',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args();main(a.run,a.messages,a.apply)
