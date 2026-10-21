"""Index public, date-stamped report pages without copying private report files."""
import datetime as dt
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_index():
    reports = []
    target = ROOT / 'news' / 'index.json'
    existing = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'reports': []}
    previous = {r['id']: r for r in existing['reports']}
    for folder in sorted((ROOT / 'news').iterdir(), reverse=True):
        if not folder.is_dir() or not re.fullmatch(r'\d{4}-\d{2}-\d{2}-\d{4}', folder.name):
            continue
        stamp = dt.datetime.strptime(folder.name, '%Y-%m-%d-%H%M')
        page = folder / 'index.html'
        if not page.is_file():
            raise ValueError(f'Missing public report: {folder.name}')
        source = page.read_text(encoding='utf-8')
        title = re.search(r'<title>(.*?)</title>', source, re.S)
        if not title:
            raise ValueError(f'Missing title: {page}')
        edition = {'0700': 'morning', '1900': 'evening', '1930': 'evening'}.get(stamp.strftime('%H%M'), 'special')
        metadata = {k: previous.get(folder.name, {}).get(k) for k in ('published_at', 'publication_time_basis')}
        validation = ROOT / 'reports/news' / (stamp.strftime('%Y%m%d_%H%M') + '_validation.json')
        if validation.is_file():
            evidence = json.loads(validation.read_text(encoding='utf-8-sig'))
            if evidence.get('pages_conclusion') == 'success':
                value = evidence.get('pages_completed_at') or evidence.get('public_verified_at')
                if value:
                    moment = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
                    if moment.tzinfo is None:
                        raise ValueError('Publication timestamp needs timezone')
                    metadata = {'published_at': moment.astimezone(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec='seconds'),
                                'publication_time_basis': 'deployment_completed' if evidence.get('pages_completed_at') else 'public_verified'}
        reports.append({
            **metadata,
            'id': folder.name,
            'cutoff': stamp.isoformat(timespec='minutes') + '+09:00',
            'edition': edition,
            'title': html.unescape(title.group(1)).strip(),
            'url': f'news/{folder.name}/',
        })
    if not reports:
        raise ValueError('No public reports found')
    target = ROOT / 'news' / 'index.json'
    existing = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'reports': []}
    removed = {r['id'] for r in existing['reports']} - {r['id'] for r in reports}
    if removed:
        raise ValueError(f'Refusing to drop previous reports: {sorted(removed)}')
    reports.sort(key=lambda r: (r.get('published_at') or '', r['cutoff']), reverse=True)
    target.write_text(json.dumps({'schema_version': 1, 'timezone': 'Asia/Seoul', 'reports': reports}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Indexed {len(reports)} public reports; latest={reports[0]["id"]}')


if __name__ == '__main__':
    build_index()
