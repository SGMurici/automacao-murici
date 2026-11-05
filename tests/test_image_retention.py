import unittest
from datetime import datetime, timezone

from image_retention import plan_image_retention


class ImageRetentionPlannerTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)

    def asset(self, **overrides):
        row = {
            "drive_file_id": "drive-image-001",
            "mime_type": "image/png",
            "editorial_post_id": 42,
            "publication_status": "publicado",
            "published_at": "2026-10-29T12:00:00Z",
        }
        row.update(overrides)
        return row

    def test_exactly_seven_full_days_is_eligible(self):
        result = plan_image_retention([self.asset()], now=self.now)
        self.assertEqual(result["eligible_count"], 1)
        self.assertEqual(result["mode"], "dry_run")
        self.assertFalse(result["destructive"])

    def test_less_than_seven_full_days_is_excluded(self):
        row = self.asset(published_at="2026-10-29T12:00:01Z")
        result = plan_image_retention([row], now=self.now)
        self.assertEqual(result["eligible_count"], 0)
        self.assertEqual(result["excluded"][0]["reason"], "retention_period_not_completed")

    def test_unpublished_or_unlinked_assets_are_excluded(self):
        rows = [
            self.asset(drive_file_id="a", publication_status="agendado"),
            self.asset(drive_file_id="b", editorial_post_id=None),
        ]
        result = plan_image_retention(rows, now=self.now)
        self.assertEqual(result["eligible_count"], 0)

    def test_naive_timestamp_fails_closed(self):
        result = plan_image_retention(
            [self.asset(published_at="2026-10-01T12:00:00")], now=self.now
        )
        self.assertEqual(result["excluded"][0]["reason"],
                         "missing_or_timezone_naive_published_at")

    def test_non_image_and_duplicate_drive_ids_are_excluded(self):
        rows = [
            self.asset(mime_type="application/pdf"),
            self.asset(drive_file_id="duplicate"),
            self.asset(drive_file_id="duplicate"),
        ]
        result = plan_image_retention(rows, now=self.now)
        self.assertEqual(result["eligible_count"], 0)
        reasons = {item["reason"] for item in result["excluded"]}
        self.assertIn("not_an_image", reasons)
        self.assertIn("duplicate_drive_file_reference", reasons)

    def test_retention_period_cannot_be_overridden(self):
        with self.assertRaises(ValueError):
            plan_image_retention([], now=self.now, retention_days=30)


if __name__ == "__main__":
    unittest.main()
