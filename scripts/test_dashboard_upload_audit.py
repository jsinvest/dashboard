"""Publication decisions: schedules, provisional editions, and public-only ZIPs."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import dashboard_upload_audit as a


class PublicationDecisions(unittest.TestCase):
    def test_daily_deadline_and_holiday(self):
        holidays = {a.date(2026, 10, 9)}
        self.assertEqual(a.expected_day("trade", 21, a.datetime(2026, 10, 12, 20, tzinfo=a.KST), holidays), a.date(2026, 10, 8))
        self.assertEqual(a.expected_day("trade", 21, a.datetime(2026, 10, 12, 21, tzinfo=a.KST), holidays), a.date(2026, 10, 12))
        self.assertEqual(a.expected_day("trade", 17, a.datetime(2026, 10, 11, 21, tzinfo=a.KST), holidays), a.date(2026, 10, 8))

    def test_weekly_schedule_does_not_expect_daily_etf(self):
        for now, expected in [("2026-11-10T21:00:00+09:00", "2026-11-06"), ("2026-11-14T08:59:00+09:00", "2026-11-06"), ("2026-11-14T09:00:00+09:00", "2026-11-13")]:
            self.assertEqual(a.expected_day("weekly", 9, a.datetime.fromisoformat(now), set()).isoformat(), expected)
        self.assertIsNone(a.expected_day("source", 20, a.datetime.now(a.KST), set()))

    def test_today_does_not_mean_final(self):
        d = {name: [] for name in ["executive_summary", "market_views", "risk_flags", "next_session_checks", "candidate_stocks", "final_picks"]}
        d.update(elliott_wave_view={}, data_validation={"phase": "PROVISIONAL"})
        self.assertEqual(a.json_issues("market-ai", d, a.datetime(2026, 11, 10, 20, tzinfo=a.KST)), ["FINAL_PENDING"])
        self.assertEqual(a.json_issues("market-ai", d, a.datetime(2026, 11, 10, 21, tzinfo=a.KST)), ["FINAL_NOT_PUBLISHED"])

    def test_both_news_editions_required(self):
        d = {"reports": [{"edition": "morning", "cutoff": "2026-11-10T07:00:00+09:00"}]}
        self.assertEqual(a.json_issues("news", d, a.datetime(2026, 11, 10, 9, tzinfo=a.KST)), [])
        self.assertEqual(a.json_issues("news", d, a.datetime(2026, 11, 10, 21, tzinfo=a.KST)), ["NEWS_EDITION_MISSING"])

    def test_bundle_repair_uses_committed_public_files_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Audit Test"], cwd=root, check=True)
            folder = root / "supply-zone"
            folder.mkdir()
            image = b"committed public chart"
            d = {"as_of": "2026-11-10", "futures_contract": "F202612", "data_validation": {"trade_date": "20261110", "ready_for_editorial_review": True},
                 "charts": [{"file": "chart.png", "sha256": a.sha(image)}], "downloads": []}
            (folder / "latest.json").write_text(json.dumps(d), encoding="utf8")
            (folder / "chart.png").write_bytes(image)
            subprocess.run(["git", "add", "--", "supply-zone/latest.json", "supply-zone/chart.png"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "public source"], cwd=root, check=True)
            (folder / "chart.png").write_bytes(b"uncommitted unrelated dirty chart")
            (folder / "private_account.csv").write_text("private", encoding="utf8")
            result = a.repair_bundle(root, "HEAD", a.datetime(2026, 11, 10, 21, tzinfo=a.KST))
            archive = (folder / result["file"]).read_bytes()
            a.verify_bundle(result, archive, d, lambda n: a.read_object(root, "HEAD", "supply-zone/" + n))
            self.assertEqual(result["file_count"], 2)
            self.assertEqual((folder / "chart.png").read_bytes(), b"uncommitted unrelated dirty chart")
            subprocess.run(["git", "add", "--", "supply-zone/data_bundle_latest.json", "supply-zone/futures_options_data_bundle_latest.zip"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "bundle"], cwd=root, check=True)
            self.assertEqual(a.repair_bundle(root, "HEAD", a.datetime.now(a.KST))["status"], "UNCHANGED")
            altered = dict(result, as_of="20261109")
            with self.assertRaisesRegex(ValueError, "기준일 불일치"):
                a.verify_bundle(altered, archive, d, lambda n: a.read_object(root, "HEAD", "supply-zone/" + n))

    def test_zip_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            a.public_files({"downloads": [{"file": "../private.csv"}]})


if __name__ == "__main__":
    unittest.main()
