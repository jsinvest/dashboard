import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from reconcile_stock_price_sessions import main, reconcile
from test_stock_price_session import fixtures


class BatchSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def case(self, code, *, broken=False):
        chart, minute = fixtures(code=code)
        if broken:
            minute['response']['stk_min_pole_chart_qry'][0]['cur_prc'] = '24700'
            minute['response']['stk_min_pole_chart_qry'][0]['high_pric'] = '24700'
        a, b = self.root / (code + '-chart.json'), self.root / (code + '-minute.json')
        a.write_text(json.dumps(chart), encoding='utf-8')
        b.write_text(json.dumps(minute), encoding='utf-8')
        return {'code': code, 'chart_raw': str(a), 'intraday_raw': str(b),
                'trade_date': '20261119', 'previous_date': '20261118', 'regular_close': '153000'}

    def test_one_unresolved_stock_does_not_discard_valid_independent_stock(self):
        result = reconcile([self.case('086450'), self.case('035760', broken=True)],
                           checked_at='2026-11-20T22:00:00+09:00')
        self.assertEqual(result['summary']['eligible_for_remaining_selection_checks'], 1)
        self.assertEqual(result['summary']['unresolved'], 1)
        self.assertFalse(result['market_publication_blocked_by_this_check'])
        self.assertFalse(result['recommendation_selection_complete'])
        self.assertEqual(result['unresolved_stocks'][0]['code'], '035760')

    def test_all_failed_is_not_selection_success(self):
        result = reconcile([self.case('086450', broken=True)], checked_at='2026-11-20T22:00:00+09:00')
        self.assertEqual(result['status'], 'NO_VALIDATED_PRICE_BOUNDARIES')
        self.assertFalse(result['recommendation_selection_complete'])

    def test_duplicate_cases_cannot_double_count_stock(self):
        case = self.case('086450')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            reconcile([case, copy.deepcopy(case)], checked_at='2026-11-20T22:00:00+09:00')

    def test_manifest_code_cannot_approve_different_stock(self):
        case = self.case('086450')
        case['code'] = '035760'
        result = reconcile([case], checked_at='2026-11-20T22:00:00+09:00')
        self.assertEqual(result['summary']['unresolved'], 1)
        self.assertEqual(result['records'][0]['issues'][-1]['code'], 'CASE_CODE_MISMATCH')

    def test_cli_corrupt_stock_evidence_keeps_valid_stock_results(self):
        valid, corrupt = self.case('086450'), self.case('035760')
        Path(corrupt['chart_raw']).write_text('{', encoding='utf-8')
        manifest, output = self.root / 'cases.json', self.root / 'result.json'
        manifest.write_text(json.dumps([valid, corrupt]), encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(['--cases', str(manifest), '--output', str(output)])
        result = json.loads(output.read_text(encoding='utf-8'))
        self.assertEqual(code, 2)
        self.assertEqual(result['summary']['eligible_for_remaining_selection_checks'], 1)
        self.assertEqual(result['summary']['unresolved'], 1)

    def test_output_cannot_overwrite_manifest_or_raw_quote(self):
        case = self.case('086450')
        manifest = self.root / 'cases.json'
        manifest.write_text(json.dumps([case]), encoding='utf-8')
        for target in (manifest, Path(case['chart_raw']), Path(case['intraday_raw'])):
            prior = target.read_bytes()
            with self.assertRaises(SystemExit) as caught:
                main(['--cases', str(manifest), '--output', str(target)])
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(target.read_bytes(), prior)


if __name__ == '__main__':
    unittest.main()
