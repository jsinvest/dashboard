import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sync_live_monitor_connection as sync_module
from sync_live_monitor_connection import SyncError, main, public_url, synchronize


URL = "https://new-verified-viewer.trycloudflare.com"


class ConnectionSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = self.root / "live-monitors/connection.json"
        self.manifest.parent.mkdir()
        self.connection = {"url": "https://old-viewer.trycloudflare.com", "mode": "readonly",
                           "authentication": "server_password", "published_at": "OLD_TIMESTAMP",
                           "sources": {"program": "existing"}, "temporary_connection": True}
        self.manifest.write_text(json.dumps(self.connection), encoding="utf-8")
        self.source = self.root / "public.json"
        self.source.write_text(json.dumps({"url": URL, "ignored_private_field": "MUST_NOT_COPY"}), encoding="utf-8")
        self.before = self.manifest.read_bytes()
        self.requests = []

    def good_fetch(self, url):
        self.requests.append(url)
        if url.endswith("/health"):
            return 200, b'{"app":"readonly-trading-viewer"}'
        if url.endswith("/api/state"):
            return 401, b""
        return 200, b'<input id="viewerPassword" type="password">'

    def run_sync(self, **kwargs):
        return synchronize(self.root, self.source, fetcher=self.good_fetch, **kwargs)

    def test_check_only_validates_all_seven_routes_without_edit(self):
        result = self.run_sync()
        self.assertEqual(result["status"], "VALIDATED")
        self.assertEqual(len(self.requests), 7)
        self.assertEqual(len(result["checks"]), 7)
        self.assertFalse(result["applied"])
        self.assertEqual(self.manifest.read_bytes(), self.before)

    def test_apply_changes_only_url_and_timestamp(self):
        result = self.run_sync(apply=True)
        updated = json.loads(self.manifest.read_text())
        self.assertTrue(result["applied"])
        self.assertEqual(updated["url"], URL)
        self.assertNotEqual(updated["published_at"], "OLD_TIMESTAMP")
        expected = copy.deepcopy(self.connection)
        expected.update(url=URL, published_at=updated["published_at"])
        self.assertEqual(updated, expected)
        self.assertNotIn("ignored_private_field", updated)

    def test_same_url_does_not_rewrite_timestamp_or_bytes(self):
        self.source.write_text(json.dumps({"url": self.connection["url"]}), encoding="utf-8")
        result = self.run_sync(apply=True)
        self.assertFalse(result["change_required"])
        self.assertFalse(result["applied"])
        self.assertEqual(self.manifest.read_bytes(), self.before)

    def test_unauthenticated_200_is_rejected_and_manifest_preserved(self):
        def unsafe(url):
            return (200, b'{"sensitive":"not printed"}') if url.endswith("/api/state") else self.good_fetch(url)
        with self.assertRaisesRegex(SyncError, "UNAUTHENTICATED_STATE_NOT_BLOCKED"):
            synchronize(self.root, self.source, apply=True, fetcher=unsafe)
        self.assertEqual(self.manifest.read_bytes(), self.before)

    def test_invalid_urls_are_rejected_before_http(self):
        invalid = ["http://a.trycloudflare.com", "https://a.trycloudflare.com:443", "https://a.trycloudflare.com/x",
                   "https://a.b.trycloudflare.com", "https://user:password@a.trycloudflare.com",
                   "https://a.trycloudflare.com?x=1", "https://a.trycloudflare.com#fragment",
                   "https://a.trycloudflare.com.evil.test", "https://-a.trycloudflare.com", None]
        for url in invalid:
            with self.subTest(url=url), self.assertRaisesRegex(SyncError, "INVALID_PUBLIC_URL"):
                public_url(url)
        self.assertEqual(self.requests, [])

    def test_403_or_missing_password_marker_preserves_manifest(self):
        for response in [(403, b"Forbidden"), (200, b"no login page")]:
            def broken(url):
                return response if url.endswith("/investor/") else self.good_fetch(url)
            with self.subTest(response=response), self.assertRaises(SyncError):
                synchronize(self.root, self.source, apply=True, fetcher=broken)
            self.assertEqual(self.manifest.read_bytes(), self.before)

    def test_wrong_health_app_and_unsafe_manifest_are_rejected(self):
        with self.assertRaisesRegex(SyncError, "UNEXPECTED_BRIDGE_APP"):
            synchronize(self.root, self.source, apply=True, fetcher=lambda url: (200, b'{"app":"other"}'))
        self.assertEqual(self.manifest.read_bytes(), self.before)
        unsafe = dict(self.connection, authentication="none")
        self.manifest.write_text(json.dumps(unsafe))
        with self.assertRaisesRegex(SyncError, "UNSAFE_MANIFEST_MODE"):
            self.run_sync(apply=True)
        self.assertEqual(json.loads(self.manifest.read_text()), unsafe)

    def test_cli_failure_exit_two_preserves_manifest_and_safe_report(self):
        report = self.root / "report.json"
        with patch("sync_live_monitor_connection.validate_bridge", side_effect=SyncError("HEALTH_HTTP_STATUS")):
            code = main(["--root", str(self.root), "--bridge-public", str(self.source), "--apply", "--report", str(report)])
        self.assertEqual(code, 2)
        self.assertEqual(self.manifest.read_bytes(), self.before)
        data = json.loads(report.read_text())
        self.assertEqual(data["error"], "HEALTH_HTTP_STATUS")
        self.assertNotIn(str(self.root), json.dumps(data))

    def test_report_cannot_overwrite_source(self):
        with self.assertRaisesRegex(SyncError, "REPORT_OVERLAPS_SOURCE"):
            self.run_sync(apply=True, report=self.manifest)
        self.assertEqual(self.manifest.read_bytes(), self.before)

    def test_report_failure_after_apply_restores_our_manifest_bytes(self):
        report = self.root / "report.json"
        original_writer = sync_module.atomic_bytes
        failed = False

        def fail_once(path, data):
            nonlocal failed
            if Path(path) == report and json.loads(data).get("applied") and not failed:
                failed = True
                raise OSError("private path must not be disclosed")
            return original_writer(path, data)

        with patch.object(sync_module, "validate_bridge", return_value=[]), patch.object(sync_module, "atomic_bytes", side_effect=fail_once):
            code = main(["--root", str(self.root), "--bridge-public", str(self.source), "--apply", "--report", str(report)])
        self.assertEqual(code, 2)
        self.assertEqual(self.manifest.read_bytes(), self.before)
        self.assertEqual(json.loads(report.read_text())["error"], "FILE_WRITE_FAILED")


if __name__ == "__main__":
    unittest.main()
