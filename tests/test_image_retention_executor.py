import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

from image_retention_executor import RetentionExecutionError, execute_one_image_deletion


class ImageRetentionExecutorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
        self.asset = {"drive_file_id": "fake-drive-image-001"}
        self.current = {
            "drive_file_id": "fake-drive-image-001", "mime_type": "image/png",
            "editorial_post_id": 42, "publication_status": "publicado",
            "published_at": "2026-10-29T12:00:00Z", "asset_status": "stored",
        }
        self.metadata = {
            "id": "fake-drive-image-001", "mimeType": "image/png",
            "parents": ["fake-test-folder"], "trashed": False,
        }
        self.deleted, self.marked, self.audits = [], [], []
        self.locked = []

    @contextmanager
    def lock(self, file_id):
        self.locked.append(file_id)
        yield

    def run_workflow(self, **overrides):
        options = {
            "now": self.now, "test_folder_id": "fake-test-folder",
            "asset_lock": self.lock,
            "load_current_asset": lambda file_id: self.current,
            "load_drive_metadata": lambda file_id: self.metadata,
            "permanent_delete": lambda file_id: self.deleted.append(file_id) or True,
            "mark_deleted": lambda file_id, at: self.marked.append((file_id, at)) or True,
            "record_audit": lambda event: self.audits.append(event),
        }
        options.update(overrides)
        return execute_one_image_deletion(self.asset, **options)

    def test_eligible_image_deleted_and_audited_under_lock(self):
        result = self.run_workflow()
        self.assertEqual(result["status"], "deleted")
        self.assertEqual(self.deleted, ["fake-drive-image-001"])
        self.assertEqual(len(self.marked), 1)
        self.assertEqual(self.locked, ["fake-drive-image-001"])
        self.assertEqual(self.audits[0]["event"], "image_permanently_deleted")

    def test_under_seven_days_fails_before_drive_delete(self):
        self.current["published_at"] = "2026-10-29T12:00:01Z"
        with self.assertRaises(RetentionExecutionError):
            self.run_workflow()
        self.assertEqual(self.deleted, [])

    def test_wrong_folder_fails_closed(self):
        self.metadata["parents"] = ["other-folder"]
        with self.assertRaises(RetentionExecutionError):
            self.run_workflow()
        self.assertEqual(self.deleted, [])

    def test_wrong_identity_or_missing_trashed_metadata_fails_closed(self):
        self.metadata["id"] = "different-file"
        with self.assertRaises(RetentionExecutionError):
            self.run_workflow()
        self.metadata["id"] = "fake-drive-image-001"
        self.metadata.pop("trashed")
        with self.assertRaises(RetentionExecutionError):
            self.run_workflow()
        self.assertEqual(self.deleted, [])

    def test_non_stored_asset_fails_closed(self):
        self.current["asset_status"] = "deleted"
        with self.assertRaises(RetentionExecutionError):
            self.run_workflow()
        self.assertEqual(self.deleted, [])

    def test_drive_failure_never_marks_database(self):
        with self.assertRaises(RetentionExecutionError):
            self.run_workflow(permanent_delete=lambda file_id: False)
        self.assertEqual(self.marked, [])

    def test_database_mark_failure_records_reconciliation(self):
        with self.assertRaisesRegex(RetentionExecutionError, "reconciliation"):
            self.run_workflow(mark_deleted=lambda file_id, at: False)
        self.assertEqual(self.deleted, ["fake-drive-image-001"])
        self.assertEqual(self.audits[0]["event"], "drive_deleted_database_reconciliation_required")

    def test_confirmed_missing_file_is_explicitly_idempotent(self):
        result = self.run_workflow(permanent_delete=lambda file_id: "already_deleted")
        self.assertEqual(result["drive_delete_result"], "already_deleted")
        self.assertEqual(len(self.marked), 1)

    def test_missing_test_folder_fails_closed(self):
        with self.assertRaises(RetentionExecutionError):
            self.run_workflow(test_folder_id="")
        self.assertEqual(self.deleted, [])


if __name__ == "__main__":
    unittest.main()
