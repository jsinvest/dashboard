"""Validated, additive merge of explicit DAJU target-price list posts."""
import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from update_report_dashboard import dedupe_key, rebuild_summary

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=None if compact else 2, separators=(',', ':') if compact else None), encoding='utf-8')
    tmp.replace(path)

def parse_post(post):
    text = post['text'].strip()
    match = re.match(r'^📣 목표주가 상향 목록\((\d{4}-\d{2}-\d{2})\)(?:\s*-\s*\(\d+\))?', text)
    if not match:
        raise ValueError(f'Unrecognized target list heading: {post["url"]}')
    date = match[1]
    datetime.strptime(date, '%Y-%m-%d')
    if date != post['date_kst'][:10]:
        raise ValueError('List date and KST publication date disagree')
    if post['url'] != f'https://t.me/daju_dart/{post["id"]}':
        raise ValueError('Source identity mismatch')
    blocks = text.split('📌')[1:]
    if not blocks:
        raise ValueError('Empty target list')
    rows = []
    for block in blocks:
        pattern = (r'^\s*(?P<name>[^\n]+?)\((?P<code>\d{6})\)\s*\n'
                   r'\[(?P<up>\d+)/(?P<total>\d+) \(상향/종목 리포트\)\]\s*\n'
                   r'\s*- 목표주가\s*:\s*(?P<price>[\d,]+)원(?:\(🔺\s*(?P<pct>[\d.]+)%\))?\s*\n'
                   r'\s*- 제목\s*:\s*(?P<title>.*?)\n'
                   r'\s*- 내용\s*:\s*(?P<body>.*?)\n'
                   r'\s*- 기관\s*:\s*(?P<broker>[^\n]+)\s*$')
        m = re.fullmatch(pattern, block, re.S)
        if not m:
            raise ValueError(f'Incomplete/unrecognized report block in {post["url"]}: {block[:100]}')
        values = m.groupdict()
        if not all(values[k].strip() for k in ['name','title','body','broker']):
            raise ValueError('Required field missing')
        price = int(values['price'].replace(',', ''))
        up, total = int(values['up']), int(values['total'])
        if price <= 0 or not 0 < up <= total:
            raise ValueError('Invalid price or report counts')
        rows.append({'날짜': date, '종목명': values['name'].strip(), '종목코드': values['code'],
                     '목표주가': price, '상향건수': up, '전체건수': total,
                     '제목': values['title'].strip(), '내용': values['body'].strip(),
                     '기관': values['broker'].strip(), '텔레그램URL': post['url'],
                     '목표주가변동률_pct': float(values['pct']) if values['pct'] else None})
    return rows

def merge(source, after, through, audit, apply=False):
    audit.mkdir(parents=True, exist_ok=True)
    posts = json.loads(source.read_text(encoding='utf-8'))
    if not posts or len(posts) != len({p['id'] for p in posts}):
        raise ValueError('Empty or duplicate source messages')
    selected = [p for p in posts if after < p['date_kst'][:10] <= through]
    targets = [p for p in selected if '목표주가 상향 목록' in p['text']]
    rows = [r for p in targets for r in parse_post(p)]
    candidates = [p for p in selected if re.search('목표주가|목표가|리포트',p['text'])]
    unparsed = [p['url'] for p in candidates if p not in targets]
    if unparsed:
        raise ValueError(f'Target/report candidate needs manual inspection: {unparsed}')
    db_path, sig_path = ROOT/'report_data.json', ROOT/'report_signal_data.json'
    original = json.loads(db_path.read_text(encoding='utf-8'))
    original_signals = json.loads(sig_path.read_text(encoding='utf-8'))
    data, signals = copy.deepcopy(original), copy.deepcopy(original_signals)
    before_details = Counter(canonical(r) for r in data['details'])
    before_up = Counter(canonical(r) for r in signals['up'])
    seen = {dedupe_key(r) for r in data['details']}
    if len(seen) != len(data['details']):
        raise ValueError('Existing report duplicates require separate review')
    signal_seen = {dedupe_key(r) for r in signals['up'] if r.get('구분')=='목표주가 상향'}
    added, added_signals, duplicates = [], [], 0
    for r in rows:
        key = dedupe_key(r)
        if key not in seen:
            clean = {k:r[k] for k in ['날짜','종목명','목표주가','상향건수','전체건수','종목코드','제목','내용','기관']}
            clean['텔레그램URL'] = r['텔레그램URL']
            data['details'].append(clean)
            added.append(clean)
            seen.add(key)
        else:
            duplicates += 1
        if key not in signal_seen:
            signal = {k:r[k] for k in ['날짜','종목명','종목코드','목표주가','제목','내용','기관','텔레그램URL','목표주가변동률_pct']}
            signal.update({'방향':'UP','구분':'목표주가 상향','영업이익_컨센대비_pct':None,
                           '영업이익':None,'영업_QoQ':None,'영업_YoY':None,'근거키워드':'목표주가 상향 목록',
                           '연계_목표주가':None,'연계_리포트날짜':None,'연계_기관':''})
            signals['up'].append(signal)
            added_signals.append(signal)
            signal_seen.add(key)
    now = datetime.now(KST).isoformat(timespec='seconds')
    if added:
        data['details'].sort(key=lambda r:(r['날짜'],r['종목명'],r['목표주가']))
        data['summary'] = rebuild_summary(data['details'])
        data['meta'].update({'created_at':now,'generated_at':now,'summary_count':len(data['summary']),
                             'detail_count':len(data['details']),'last_merge_source':'https://t.me/daju_dart',
                             'last_merge_added':len(added),'last_merge_through':max(r['날짜'] for r in rows),
                             'last_source_checked_through':through})
    cross_date = Counter(tuple(str(r[k]) for k in ['종목코드','종목명','목표주가','제목','기관']) for r in rows)
    repeat_count = sum(n-1 for n in cross_date.values() if n>1)
    if added_signals:
        signals['meta'].update({'generated_at':now,'up_signal_count':len(signals['up']),
                               'down_signal_count':len(signals['down']),
                               'up_category_counts':dict(Counter(r['구분'] for r in signals['up'])),
                               'down_category_counts':dict(Counter(r['구분'] for r in signals['down'])),
                               'target_price_source_checked_through':through,
                               'target_price_latest_list_date':max(r['날짜'] for r in rows),
                               'target_price_last_merge_added':len(added_signals),
                               'target_price_source_note':'공개 채널 목록의 날짜 기준이며 증권사 발간일을 독립 검증한 값이 아닙니다. 날짜가 다른 동일 내용은 지정된 날짜 포함 중복키에 따라 보존합니다. 공개 미리보기에 없는 글은 확인 불가입니다.',
                               'target_price_last_sources':[p['url'] for p in targets]})
    assert not (before_details - Counter(canonical(r) for r in data['details'])), 'Old details changed'
    assert not (before_up - Counter(canonical(r) for r in signals['up'])), 'Old up signals changed'
    assert signals['down'] == original_signals['down'], 'Old down signals changed'
    assert data['summary'] == rebuild_summary(data['details']), 'Summary mismatch'
    assert len(data['details']) == len({dedupe_key(r) for r in data['details']}), 'Duplicates'
    assert all(re.fullmatch(r'\d{6}',r['종목코드']) for r in data['details']), 'Invalid code'
    target_rows = [r for r in signals['up'] if r['구분']=='목표주가 상향']
    assert len(target_rows) == len({dedupe_key(r) for r in target_rows})
    result = {'status':'PASS','applied':apply,'verified_at':now,'source_file':str(source.resolve()),
              'source_sha256':sha(source),'source_message_count':len(posts),'selected_message_count':len(selected),
              'source_latest_kst':max(p['date_kst'] for p in posts),'requested_after':after,'checked_through':through,
              'target_posts':len(targets),'target_source_urls':[p['url'] for p in targets],
              'source_report_count':len(rows),'source_report_dates':dict(Counter(r['날짜'] for r in rows)),
              'missing_required_fields':0,'invalid_codes':0,'duplicate_source_message_ids':0,
              'existing_reports':len(original['details']),'added_reports':len(added),'duplicate_reports_skipped':duplicates,
              'total_reports':len(data['details']),'summary_count':len(data['summary']),
              'target_up_count':len(target_rows),'target_up_stocks':len({r['종목코드'] for r in target_rows}),
              'up_count':len(signals['up']),'up_stocks':len({r['종목코드'] for r in signals['up']}),
              'down_count':len(signals['down']),'added_signals':len(added_signals),
              'cross_date_same_content_repeats':repeat_count,'existing_rows_preserved':True,
              'latest_report_date':max(r['날짜'] for r in data['details']),
              'limitations':['PUBLIC_WEB_PREVIEW_ONLY','Source list date, not independently verified broker issue date',
                             'No missing dates are filled; absence of public matches is not proof of no reports'],
              'before_hashes':{p.name:sha(p) for p in [db_path,sig_path,ROOT/'index.html']}}
    for name, value in [('report_data.before.json',original),('report_signal_data.before.json',original_signals),
                        ('parsed_reports.json',rows),('report_data.proposed.json',data),('report_signal_data.proposed.json',signals)]:
        write(audit/name,value)
    if apply:
        for path, value, changed in [(db_path,data,bool(added)),(sig_path,signals,bool(added_signals))]:
            if changed:
                write(path,value,compact=True)
        assert json.loads(db_path.read_text(encoding='utf-8')) == data
        assert json.loads(sig_path.read_text(encoding='utf-8')) == signals
    result['after_hashes']={p.name:sha(p) for p in [db_path,sig_path,ROOT/'index.html']}
    write(audit/'validation.json',result)
    print(json.dumps(result,ensure_ascii=True))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--after',required=True)
    p.add_argument('--through',required=True)
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--apply',action='store_true')
    a=p.parse_args()
    for date in [a.after,a.through]: datetime.strptime(date,'%Y-%m-%d')
    if a.after>=a.through: p.error('--after must precede --through')
    merge(a.source,a.after,a.through,a.audit,a.apply)
