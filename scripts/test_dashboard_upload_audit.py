"""Publication decisions: schedules, provisional editions, and public-only ZIPs."""
import json
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

import dashboard_upload_audit as a


class PublicationDecisions(unittest.TestCase):
    def review_publication(self, manifest_date="20261111", tamper=False):
        name = "futures_public_review_20261111.zip"
        futures = {"as_of": "20261111", "futures_contract": "F202612",
                   "charts": [{"file": "chart.png"}], "downloads": [{"file": name}]}
        public = {"latest.json": json.dumps(futures, indent=2).encode(), "chart.png": b"reviewed chart"}
        records = [{"file": n, "sha256": a.sha(b)} for n, b in public.items()]
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as z:
            for n, b in public.items():
                z.writestr(n, b"tampered" if tamper and n == "chart.png" else b)
            z.writestr("review_manifest_20261111.json", json.dumps({
                "as_of": manifest_date, "contract": "F202612", "files": records}))
        return {**{"supply-zone/" + n: b for n, b in public.items()},
                "supply-zone/" + name: output.getvalue(),
                "legacy.json": b'{"as_of":"20261110"}'}

    def test_explicit_current_review_zip_wins_over_hidden_legacy_descriptor(self):
        files = self.review_publication()
        path, member, body, metadata = a.publication_evidence(files.__getitem__, "futures-zip", "legacy.json")
        self.assertEqual(path, "supply-zone/futures_public_review_20261111.zip")
        self.assertEqual(a.observed_day("futures-zip", a.evidence_json(body, member)), a.date(2026, 11, 11))
        self.assertEqual(metadata["bundle_format"], "dated_public_review")

    def test_invalid_current_review_zip_never_falls_back_to_legacy(self):
        for files in [self.review_publication(manifest_date="20261110"), self.review_publication(tamper=True)]:
            with self.assertRaises(ValueError):
                a.publication_evidence(files.__getitem__, "futures-zip", "legacy.json")

    def test_unlinked_review_zip_does_not_override_legacy(self):
        files = self.review_publication()
        d = json.loads(files["supply-zone/latest.json"])
        d["downloads"] = []
        files["supply-zone/latest.json"] = json.dumps(d).encode()
        self.assertEqual(a.publication_evidence(files.__getitem__, "futures-zip", "legacy.json")[:2], ("legacy.json", None))

    def test_git_eol_conversion_is_reported_without_changing_archive_hash_checks(self):
        files = self.review_publication()
        files["supply-zone/latest.json"] = files["supply-zone/latest.json"].replace(b"\n", b"\r\n")
        path, member, body, metadata = a.publication_evidence(files.__getitem__, "futures-zip", "legacy.json")
        self.assertEqual(metadata["eol_normalized_members"], ["latest.json"])
        # Semantic JSON equivalence alone is insufficient: changed whitespace
        # other than line endings, values, or binary image bytes still fail.
        for name, replacement in [("latest.json", b"{}"), ("chart.png", b"reviewed chart\r\n")]:
            changed = dict(files, **{"supply-zone/" + name: replacement})
            with self.assertRaises((ValueError, KeyError)):
                a.verify_review_bundle(body, files["supply-zone/latest.json"], path.split("/")[-1], lambda n: changed["supply-zone/" + n])

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

    def market_publication(self, research_date="20261110"):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("index_multitimeframe_validation_latest.json", json.dumps({"status": "OK", "trade_date": "20261110", "can_use_for_decision": True}))
            archive.writestr("validation/mandatory_audit.json", json.dumps({
                "status": "OK", "trade_date": "20261110",
                "sources": [{"path": "C:/source/index_direction_research_latest.json", "sha256": "a" * 64}],
                "research_handoff": {"status": "RESEARCH_ONLY", "trade_date": research_date,
                                     "automatic_effect": {"final_market_view": "NONE"}}}))
        bundle = output.getvalue()
        return {
            "market-analysis/latest.json": json.dumps({"as_of": "20261110", "data_bundle": {
                "file": "market_data_bundle_latest.zip", "as_of": "20261110", "sha256": a.sha(bundle)}}).encode(),
            "market-analysis/market_data_bundle_latest.zip": bundle,
            "legacy.json": json.dumps({"trade_date": "20261109"}).encode()}

    def test_current_linked_bundle_wins_over_retained_legacy_file(self):
        files = self.market_publication()
        for key in ("index-mtf", "research"):
            path, member, body, metadata = a.publication_evidence(files.__getitem__, key, "legacy.json")
            self.assertEqual(path, "market-analysis/market_data_bundle_latest.zip")
            self.assertEqual(a.observed_day(key, a.evidence_json(body, member)), a.date(2026, 11, 10))
            self.assertEqual(metadata["legacy_path"], "legacy.json")
        self.assertEqual(metadata["research_status"], "RESEARCH_ONLY")
        self.assertEqual(metadata["source_research_sha256"], "a" * 64)

    def test_bad_bundle_hash_cannot_fall_back_to_a_good_looking_date(self):
        files = self.market_publication()
        files["market-analysis/market_data_bundle_latest.zip"] += b"tampered"
        with self.assertRaisesRegex(ValueError, "해시 불일치"):
            a.publication_evidence(files.__getitem__, "research", "legacy.json")

    def test_same_day_bundle_does_not_make_old_research_current(self):
        files = self.market_publication(research_date="20261109")
        with self.assertRaisesRegex(ValueError, "연구 인계자료 기준일/상태 불일치"):
            a.publication_evidence(files.__getitem__, "research", "legacy.json")

    def test_legacy_publication_remains_supported(self):
        files = self.market_publication()
        files["market-analysis/latest.json"] = b'{"as_of":"20261109"}'
        path, member, body, metadata = a.publication_evidence(files.__getitem__, "index-mtf", "legacy.json")
        self.assertEqual((path, member, metadata), ("legacy.json", None, {}))
        self.assertEqual(a.evidence_json(body)["trade_date"], "20261109")


if __name__ == "__main__":
    unittest.main()
