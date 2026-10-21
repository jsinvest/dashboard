"""Publish only hash-verified WiseReport observations; never send messages."""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'telegram-archive'))
from wise_watch import parse, key

def build(run):
    validation = json.loads((run / 'validation.json').read_text('utf-8'))
    if validation['status'] not in ('PASS', 'READY_FOR_PUBLICATION'):
        raise ValueError('Source validation failed')
    rows = json.loads((run / 'rows.json').read_text('utf-8'))
    parsed = []
    for source in validation['sources']:
        raw = Path(source['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source['sha256']:
            raise ValueError('Source hash mismatch')
        _, date, items = parse(raw)
        if date != source['date'] or len(items) != source['count']:
            raise ValueError('Source date/count mismatch')
        parsed.extend(items)
    if parsed != rows or len(rows) != validation['source_rows']:
        raise ValueError('Parsed rows mismatch')
    days = {}
    for date in sorted({r['date'] for r in rows}, reverse=True):
        selected = [r for r in rows if r['date'] == date]
        reports, seen = [], set()
        duplicates = 0
        for row in selected:
            if row['status'] not in ('목표주가 상향', '목표주가 하향'):
                continue
            if (not re.fullmatch(r'\d{6}', row['code']) or row['code'] == '000000'
                    or not isinstance(row['price'], int) or row['price'] <= 0
                    or not all(row[x].strip() for x in ('name', 'broker', 'title', 'summary'))):
                raise ValueError('Incomplete directional report')
            ident = key(row)
            if ident in seen:
                duplicates += 1
                continue
            seen.add(ident)
            reports.append(dict(row))
        counts = Counter(r['status'] for r in reports)
        days[date] = dict(source_count=len(selected), duplicate_count=duplicates,
                          up=counts['목표주가 상향'], down=counts['목표주가 하향'], reports=reports)
    out = ROOT / 'daily-reports'
    out.mkdir(exist_ok=True)
    # Keep historical days while replacing a reobserved day with its verified snapshot.
    path = out / 'latest.json'
    previous = json.loads(path.read_text('utf-8')) if path.exists() else {'days': {}}
    if previous.get('collected_at', '') > validation['collected_at']:
        raise ValueError('Refusing an older observation')
    days = {**previous['days'], **days}
    data = dict(collected_at=validation['collected_at'], latest_date=max(days),
                source=validation['source'], classification='WiseReport 원문 목표주가 방향 표시 기준',
                days=dict(sorted(days.items(), reverse=True)))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    result = dict(status='PASS', source_run=str(run.resolve()), source_rows=len(rows),
                  latest_date=data['latest_date'], up=days[data['latest_date']]['up'],
                  down=days[data['latest_date']]['down'], output_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (run / 'daily_reports_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    build(p.parse_args().run)
