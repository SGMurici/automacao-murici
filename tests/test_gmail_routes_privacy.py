import unittest
from unittest.mock import patch

import app as application


class _FakeCursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return (True,)


class _FakeConnection:
    def __init__(self):
        self.cursor_instance = _FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


class GmailRoutePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()

    def test_unauthorized_request_does_not_open_database_or_read_gmail(self):
        with (
            patch.object(application, "GMAIL_MONITOR_SECRET", "test-gmail-secret"),
            patch.object(application, "get_db_connection") as get_db,
            patch.object(application, "_gmail_triage_one_account") as triage,
        ):
            response = self.client.post("/internal/gmail/triage/run")
        self.assertEqual(response.status_code, 401)
        get_db.assert_not_called()
        triage.assert_not_called()

    def test_unconfigured_monitor_fails_closed(self):
        with (
            patch.object(application, "GMAIL_MONITOR_SECRET", None),
            patch.object(application, "get_db_connection") as get_db,
        ):
            response = self.client.post("/internal/gmail/triage/run")
        self.assertEqual(response.status_code, 503)
        get_db.assert_not_called()

    def test_endpoint_never_returns_message_details_even_when_opt_out_is_requested(self):
        connection = _FakeConnection()

        def fake_triage(account_name, query, max_results):
            return {
                "status": "ok",
                "count": 1,
                "summary": {
                    "total": 1,
                    "categories": {"entrevista": 1},
                    "priorities": {"alta": 1},
                },
                "messages": [{
                    "from": "private-sender@example.test",
                    "subject": "PRIVATE_SUBJECT_SENTINEL",
                    "body_text": "PRIVATE_BODY_SENTINEL",
                    "snippet": "PRIVATE_SNIPPET_SENTINEL",
                }],
            }

        with (
            patch.object(application, "GMAIL_MONITOR_SECRET", "test-gmail-secret"),
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application, "_gmail_triage_one_account", side_effect=fake_triage) as triage,
        ):
            response = self.client.post(
                "/internal/gmail/triage/run?summary_only=false",
                headers={"X-Gmail-Monitor-Secret": "test-gmail-secret"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["summary"]["total"], 4)
        self.assertEqual(triage.call_count, 4)
        self.assertTrue(connection.closed)
        for account in payload["accounts"].values():
            self.assertNotIn("messages", account)
        serialized = response.get_data(as_text=True)
        for private_value in (
            "private-sender@example.test",
            "PRIVATE_SUBJECT_SENTINEL",
            "PRIVATE_BODY_SENTINEL",
            "PRIVATE_SNIPPET_SENTINEL",
        ):
            self.assertNotIn(private_value, serialized)


if __name__ == "__main__":
    unittest.main()
