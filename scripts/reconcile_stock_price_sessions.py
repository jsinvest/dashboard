"""Check stored per-stock session evidence without collecting or publishing.

Input is a JSON array of code, chart_raw, intraday_raw, trade_date,
previous_date and regular_close. Exit 2 signals unresolved stocks; it does
not prohibit independent, already-validated market publication.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from stock_price_session import load_and_evaluate


def reconcile(cases, *, checked_at=None):
    if not isinstance(cases, list) or not cases:
        raise ValueError('A nonempty array of stock evidence cases is required')
    seen, records = set(), []
    checked_at = checked_at or datetime.now(timezone.utc).isoformat()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError('Each case must be an object')
        code, date = case.get('code'), case.get('trade_date')
        if not isinstance(code, str) or not re.fullmatch(r'\d{6}', code):
            raise ValueError('An explicit six-digit KRX code is required')
        key = (date, code)
        if key in seen:
            raise ValueError('Duplicate stock/date evidence case')
        seen.add(key)
        result = load_and_evaluate(
            case['chart_raw'], case['intraday_raw'], trade_date=date,
            previous_date=case['previous_date'], regular_close=case['regular_close'],
            checked_at=checked_at,
        )
        if result.get('code') not in (None, code):
            result.update(status='UNRESOLVED', can_use_completed_history=False)
            result.setdefault('issues', []).append({'code': 'CASE_CODE_MISMATCH',
                                                   'detail': 'Manifest code differs from source response'})
        result['manifest_code'] = code
        records.append(result)
    counts = dict(Counter(r['status'] for r in records))
    unresolved = [r for r in records if r['status'] == 'UNRESOLVED']
    eligible = [r for r in records if r.get('can_use_completed_history')]
    return {
        'checked_at': checked_at,
        'status': ('PRICE_BOUNDARIES_RESOLVED' if not unresolved else
                   'PARTIAL_PRICE_BOUNDARIES' if eligible else 'NO_VALIDATED_PRICE_BOUNDARIES'),
        'summary': {'cases': len(records), 'status_counts': counts,
                    'eligible_for_remaining_selection_checks': len(eligible),
                    'unresolved': len(unresolved)},
        'all_price_checks_resolved': not unresolved,
        'market_publication_blocked_by_this_check': False,
        'recommendation_selection_complete': False,
        'scope': 'Previous-day price boundaries only. Normal stock selection, full source QA and deployment gates remain required.',
        'unresolved_stocks': [{'trade_date': r['trade_date'], 'code': r['manifest_code'],
                               'issues': r.get('issues', [])} for r in unresolved],
        'records': records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    cases = json.loads(args.cases.read_text(encoding='utf-8-sig'))
    protected = {args.cases.resolve()}
    for case in cases if isinstance(cases, list) else []:
        if not isinstance(case, dict):
            parser.error('Each case must be an object')
        for key in ('chart_raw', 'intraday_raw'):
            if key in case:
                source = Path(case[key])
                protected.add(source.resolve())
                if key == 'chart_raw' and source.is_file():
                    try:
                        chart = json.loads(source.read_text(encoding='utf-8-sig'))
                    except (OSError, ValueError, TypeError):
                        continue  # Per-stock load_and_evaluate reports the invalid input.
                    if not isinstance(chart, dict):
                        continue
                    for ref in ('source_raw', 'request_evidence'):
                        if isinstance(chart.get(ref), dict) and isinstance(chart[ref].get('path'), str):
                            protected.add(Path(chart[ref]['path']).resolve())
    if args.output.resolve() in protected or (args.output.exists() and any(
            source.exists() and args.output.samefile(source) for source in protected)):
        parser.error('Output must not overwrite an input, source or evidence file')
    result = reconcile(cases)
    result['manifest_sha256'] = hashlib.sha256(args.cases.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], **result['summary'], 'output': str(args.output)}, ensure_ascii=True))
    return 2 if result['summary']['unresolved'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
