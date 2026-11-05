"""Collect source-labelled target changes. Never send messages or publish Git."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

BASE = 'https://consensus.hankyung.com/analysis/list'
KST = timezone(timedelta(hours=9))

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')

def parse(raw, day, direction, url):
    soup = BeautifulSoup(raw, 'html.parser')
    for name in ('sdate', 'edate'):
        field = soup.select_one(f'input[name="{name}"]')
        if field is None or field.get('value') != day:
            raise ValueError('Source date mismatch')
    table = soup.select_one('table')
    if table is None or not all(x in table.get_text() for x in ('현재목표', '이전목표', '적정주가')):
        raise ValueError('Source schema mismatch')
    pages = [int(parse_qs(urlparse(a['href']).query).get('now_page', ['1'])[0])
             for a in soup.select('.paging a[href]') if not a['href'].startswith('javascript:')]
    records = []
    for tr in table.select('tbody tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) == 1 and '없' in cells[0].get_text():
            continue
        if len(cells) != 6:
            raise ValueError('Unexpected source row')
        values = [c.get_text(' ', strip=True) for c in cells]
        title_link = cells[1].find('a')
        match = re.fullmatch(r'(.+?)\(([0-9]{6})\)\s*(.+)', title_link.get_text(' ', strip=True) if title_link else '')
        if not match or values[0] != day or not values[3]:
            raise ValueError('Incomplete report identity')
        prices = [int(v.replace(',', '')) if re.fullmatch(r'[0-9,]+', v) else 0 for v in values[4:6]]
        issue = '목표가 결측·0원 또는 방향 불일치: 확인 보류' if min(prices) <= 0 or (prices[0] > prices[1]) != (direction == 'up') or prices[0] == prices[1] else ''
        records.append(dict(date=day, name=match[1], code=match[2], title=match[3],
                            broker=values[3], author=values[2], price=prices[0], previous_price=prices[1],
                            status='목표주가 상향' if direction == 'up' else '목표주가 하향', source=url,
                            summary='한경 목록 표시값입니다. 증권사 원문·SEIBro 대조 미완료로 이전 목표가와 상향률은 확정하지 않습니다.',
                            comparison_verified=False, validation_issue=issue))
    return records, max(pages, default=1)

def collect(root, start, end, archive):
    now = datetime.now(KST)
    run = archive / now.strftime('%Y%m%d_%H%M%S_%f')
    run.mkdir(parents=True)
    sources, days = [], {}
    target = root / 'daily-reports/latest.json'
    before = target.read_bytes()
    data = json.loads(before)
    if data.get('latest_date', '') > end.isoformat():
        raise ValueError('Refusing to replace newer published observations')
    try:
        day = start
        while day <= end:
            rows, seen, duplicates = [], set(), 0
            for direction, skin in [('up', 'stock_good'), ('down', 'stock_bad')]:
                page, last = 1, 1
                while page <= last:
                    if page > 100:
                        raise ValueError('Page limit')
                    url = BASE + '?' + urlencode(dict(skinType=skin, sdate=day.isoformat(), edate=day.isoformat(), pagenum=80, now_page=page))
                    with urlopen(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=30) as response:
                        raw = response.read()
                    path = run / f'{day}_{direction}_{page}.html'
                    path.write_bytes(raw)
                    items, last = parse(raw, day.isoformat(), direction, url)
                    assert parse(path.read_bytes(), day.isoformat(), direction, url)[0] == items
                    sources.append(dict(url=url, path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(), count=len(items)))
                    for row in items:
                        key = tuple(row[k] for k in ('date','code','name','price','title','broker'))
                        if key in seen:
                            duplicates += 1
                        else:
                            seen.add(key); rows.append(row)
                    page += 1
            valid=[r for r in rows if not r['validation_issue']]
            days[day.isoformat()] = dict(source_count=len(rows)+duplicates, duplicate_count=duplicates,
                up=sum(r['status']=='목표주가 상향' for r in valid), down=sum(r['status']=='목표주가 하향' for r in valid),
                reports=valid, held_reports=[r for r in rows if r['validation_issue']], source_name='한경 컨센서스', source_scope='한경 상향·하향 목록 수집분', seibro_status='조회 검증 미완료')
            day += timedelta(days=1)
        if not any(d['reports'] for d in days.values()):
            raise ValueError('No reports in requested range; preserve published data pending review')
        write(run/'before.json', data)
        old_days = data['days'].copy()
        data['days'].update(days)
        assert all(data['days'][k] == v for k,v in old_days.items() if k not in days)
        data.update(collected_at=now.isoformat(), latest_date=max(data['days']), source=BASE,
                    classification='한경 컨센서스 상향·하향 목록 기준 · 전체 증권사 전수 아님 · SEIBro 대조 미완료')
        write(run/'proposed.json', data)
        if target.read_bytes() != before:
            raise ValueError('Concurrent daily data change; rebuild against latest data')
        pending = target.with_suffix('.pending.json')
        write(pending, data)
        pending.replace(target)
        result = dict(status='PASS', collected_at=now.isoformat(), sources=sources,
                      days={k:{a:v[a] for a in ('up','down','source_count')} for k,v in days.items()},
                      preserved_other_dates=True, output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                      source_run=str(run.resolve()), cross_source_validation='NOT_VERIFIED', messages_sent=0)
        write(run/'validation.json', result)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        write(run/'validation.json', dict(status='FAILED', error=str(exc), sources=sources))
        raise

if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument('--archive', type=Path, required=True)
    ap.add_argument('--start', type=date.fromisoformat)
    ap.add_argument('--end', type=date.fromisoformat)
    args=ap.parse_args(); today=datetime.now(KST).date()
    end=args.end or today; start=args.start or max(date(2026,11,4), end-timedelta(days=4))
    if not start <= end <= today: ap.error('Invalid/future date range')
    collect(args.root.resolve(), start, end, args.archive.resolve())
