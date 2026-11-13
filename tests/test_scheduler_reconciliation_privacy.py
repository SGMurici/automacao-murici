"""Privacy regression tests for uncertain LinkedIn publication reconciliation."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import app as application


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_instance


class SchedulerReconciliationPrivacyTests(unittest.TestCase):
    def test_reconciliation_does_not_return_internal_error_message(self):
        sentinel = "PRIVATE_PROVIDER_RESPONSE_SENTINEL"
        rows = [(
            7,
            41,
            "Post em reconciliação",
            datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc),
            2,
            None,
            datetime(2026, 11, 13, 10, 15, tzinfo=timezone.utc),
        )]
        connection = FakeConnection(rows)

        with (
            patch.object(application, "require_publish_secret", return_value=None),
            patch.object(application, "ensure_scheduler_tables"),
            patch.object(application, "get_db_connection", return_value=connection),
        ):
            response = application.app.test_client().get("/scheduler/reconciliation")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["itens"][0]["queue_id"], 7)
        self.assertNotIn("error_message", payload["itens"][0])
        self.assertNotIn(sentinel, response.get_data(as_text=True))

    def test_reconciliation_rejects_unauthorized_request_before_database_access(self):
        auth_response = application.app.response_class('{"status":"erro"}', status=401, mimetype="application/json")
        auth_error = (auth_response, 401)
        with (
            patch.object(application, "require_publish_secret", return_value=auth_error),
            patch.object(application, "get_db_connection") as database,
            patch.object(application, "ensure_scheduler_tables") as ensure_tables,
        ):
            response = application.app.test_client().get("/scheduler/reconciliation")

        self.assertEqual(response.status_code, 401)
        database.assert_not_called()
        ensure_tables.assert_not_called()


if __name__ == "__main__":
    unittest.main()
