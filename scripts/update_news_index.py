"""Index public, date-stamped report pages without copying private report files."""
import datetime as dt
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_index():
    reports = []
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
        edition = {'0700': 'morning', '1930': 'evening'}.get(stamp.strftime('%H%M'), 'special')
        reports.append({
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
    target.write_text(json.dumps({'schema_version': 1, 'timezone': 'Asia/Seoul', 'reports': reports}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Indexed {len(reports)} public reports; latest={reports[0]["id"]}')


if __name__ == '__main__':
    build_index()
