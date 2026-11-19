import sqlite3
import tempfile
import unittest
from pathlib import Path
from crm_workflow import connect, initialize, ingest, decide, metrics, normalize_utc

BASE = dict(source="sample", external_id="evt-1", record_id="OPP-1", event_time="2026-11-10T10:00:00-08:00",
            owner="test@example.test", stage="Discovery", next_step="Follow up")

class CRMWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = connect(Path(self.tmp.name) / "db.sqlite3")
        initialize(self.con)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_timezone_normalization(self):
        self.assertEqual(normalize_utc("2026-11-10T10:00:00-08:00"), "2026-11-10T18:00:00+00:00")

    def test_timezone_required(self):
        with self.assertRaises(ValueError):
            normalize_utc("2026-11-10T10:00:00")

    def test_identical_repeat_is_idempotent(self):
        self.assertEqual(ingest(self.con, BASE), "created")
        self.assertEqual(ingest(self.con, BASE), "duplicate")
        self.assertEqual(metrics(self.con)["ingested_events"], 1)

    def test_conflicting_repeat_rejected_without_mutation(self):
        ingest(self.con, BASE)
        with self.assertRaisesRegex(ValueError, "CONFLICT"):
            ingest(self.con, {**BASE, "stage": "Proposal"})
        self.assertEqual(metrics(self.con)["ingested_events"], 1)

    def test_proposal_requires_manual_approval_and_audits(self):
        ingest(self.con, BASE)
        ingest(self.con, {**BASE, "external_id": "evt-2", "stage": "Proposal"})
        self.assertEqual(self.con.execute("SELECT stage FROM crm_records").fetchone()[0], "Discovery")
        self.assertEqual(metrics(self.con)["pending_changes"], 1)
        self.assertEqual(decide(self.con, 1, "approved"), "approved")
        self.assertEqual(self.con.execute("SELECT stage FROM crm_records").fetchone()[0], "Proposal")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 3)

    def test_rejection_does_not_change_record(self):
        ingest(self.con, BASE)
        ingest(self.con, {**BASE, "external_id": "evt-2", "next_step": "Call client"})
        decide(self.con, 1, "rejected")
        self.assertEqual(self.con.execute("SELECT next_step FROM crm_records").fetchone()[0], "Follow up")

    def test_invalid_event_no_partial_rows(self):
        with self.assertRaises(ValueError):
            ingest(self.con, {**BASE, "owner": ""})
        self.assertEqual(metrics(self.con)["crm_records"], 0)
        self.assertEqual(metrics(self.con)["ingested_events"], 0)

    def test_report_missing_next_steps(self):
        ingest(self.con, {**BASE, "next_step": ""})
        self.assertEqual(metrics(self.con)["missing_next_steps"], 1)

if __name__ == "__main__":
    unittest.main()
