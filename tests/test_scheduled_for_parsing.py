import unittest
from datetime import datetime, timezone

import app as application


class ScheduledForParsingTests(unittest.TestCase):
    def test_converts_explicit_offset_to_utc(self):
        parsed = application.parse_scheduled_for("2026-11-10T14:30:00-03:00")
        self.assertEqual(parsed, datetime(2026, 11, 10, 17, 30, tzinfo=timezone.utc))

    def test_accepts_utc_z_suffix(self):
        parsed = application.parse_scheduled_for("2026-11-10T17:30:00Z")
        self.assertEqual(parsed, datetime(2026, 11, 10, 17, 30, tzinfo=timezone.utc))

    def test_rejects_datetime_without_timezone(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            application.parse_scheduled_for("2026-11-10T14:30:00")

    def test_rejects_invalid_datetime(self):
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            application.parse_scheduled_for("not-a-date")

    def test_rejects_empty_or_non_string_value(self):
        for value in ("", "   ", None, 123):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    application.parse_scheduled_for(value)


if __name__ == "__main__":
    unittest.main()
