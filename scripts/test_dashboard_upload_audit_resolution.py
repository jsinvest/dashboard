import io
import json
import unittest
import zipfile
from datetime import datetime

import dashboard_upload_audit as audit


class PublicationResolutionTests(unittest.TestCase):
    def fixture(self, validation=None, linked=None):
        validation = validation or {"trade_date": "20261119", "status": "OK", "can_use_for_decision": True}
        raw = json.dumps(validation).encode()
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            z.writestr('09_지수다중시간대/validation_20261119.json', raw)
        body = out.getvalue()
        manifest = {"as_of": "20261119", "data_bundle": {"as_of": "20261119", "file": "bundle.zip", "sha256": audit.sha(body)},
                    "index_multitimeframe": {"validation_file": "kospi_kosdaq_nikkei_mtf_validation.json"}}
        return {"market-analysis/latest.json": json.dumps(manifest).encode(),
                "market-analysis/bundle.zip": body,
                "market-analysis/kospi_kosdaq_nikkei_mtf_validation.json": linked or raw}

    def test_follows_current_hashed_zip_and_link_without_legacy(self):
        files = self.fixture()
        path, member, body, metadata = audit.publication_evidence(files.__getitem__, 'index-mtf', 'unused.json')
        self.assertEqual(path, 'market-analysis/bundle.zip')
        self.assertEqual(member, '09_지수다중시간대/validation_20261119.json')
        self.assertEqual(audit.evidence_json(body, member)['trade_date'], '20261119')

    def test_rejects_inconsistent_explicit_validation(self):
        files = self.fixture(linked=b'{"trade_date":"20261118","status":"OK"}')
        with self.assertRaisesRegex(ValueError, '불일치'):
            audit.publication_evidence(files.__getitem__, 'index-mtf', 'unused.json')

    def test_rejects_damaged_declared_bundle(self):
        files = self.fixture()
        files['market-analysis/bundle.zip'] += b'damage'
        with self.assertRaisesRegex(ValueError, '해시'):
            audit.publication_evidence(files.__getitem__, 'index-mtf', 'unused.json')

    def test_rejects_current_date_with_failed_validation(self):
        files = self.fixture(validation={"trade_date":"20261119", "status":"FAIL", "can_use_for_decision":False})
        with self.assertRaisesRegex(ValueError, '상태'):
            audit.publication_evidence(files.__getitem__, 'index-mtf', 'unused.json')

    def test_partial_selection_remains_action_required(self):
        payload = {name: [] for name in ['executive_summary','market_views','risk_flags','next_session_checks','candidate_stocks','final_picks']}
        payload.update(elliott_wave_view={},data_validation={'recommendation_selection_complete':False})
        issues = audit.json_issues('market-ai', payload, datetime(2026,11,19,22,tzinfo=audit.KST))
        self.assertIn('RECOMMENDATION_SELECTION_INCOMPLETE', issues)
        state = audit.completion_state([{'id':'market-ai','issues':issues}])
        self.assertEqual(audit.completion_exit_code(state), 2)
        self.assertFalse(state['all_required_updates_complete'])
        payload['data_validation']['recommendation_selection_complete'] = True
        self.assertEqual(audit.json_issues('market-ai', payload, datetime(2026,11,19,22,tzinfo=audit.KST)), [])


if __name__ == '__main__':
    unittest.main()
