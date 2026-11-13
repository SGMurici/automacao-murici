import unittest
from unittest.mock import ANY, patch
from urllib.parse import parse_qs, urlparse

import app as application


class FakeCursor:
    def __init__(self):
        self.query = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.query = query

    def fetchone(self):
        return (True,)


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


class GmailPrivacyRouteTests(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True)
        self.client = application.app.test_client()

    def test_unconfigured_monitor_fails_closed_without_database_or_gmail_access(self):
        with (
            patch.object(application, "GMAIL_MONITOR_SECRET", ""),
            patch.object(application, "get_db_connection") as database,
            patch.object(application, "_gmail_triage_one_account") as triage,
        ):
            response = self.client.post("/internal/gmail/triage/run")
        self.assertEqual(response.status_code, 503)
        database.assert_not_called()
        triage.assert_not_called()

    def test_unauthorized_monitor_fails_before_database_or_gmail_access(self):
        with (
            patch.object(application, "GMAIL_MONITOR_SECRET", "expected-secret"),
            patch.object(application, "get_db_connection") as database,
            patch.object(application, "_gmail_triage_one_account") as triage,
        ):
            response = self.client.post(
                "/internal/gmail/triage/run",
                headers={"X-Gmail-Monitor-Secret": "wrong-secret"},
            )
        self.assertEqual(response.status_code, 401)
        database.assert_not_called()
        triage.assert_not_called()

    def test_response_is_aggregate_only_and_limited_to_sg_and_drive1(self):
        connection = FakeConnection()
        private_message = {
            "id": "PRIVATE_MESSAGE_ID",
            "subject": "PRIVATE_SUBJECT_SENTINEL",
            "body_text": "PRIVATE_BODY_SENTINEL",
            "snippet": "PRIVATE_SNIPPET_SENTINEL",
        }
        summary = {
            "total": 1,
            "categories": {"entrevista": 1},
            "priorities": {"alta": 1},
            "unclassified_signals": {},
        }

        def triage(account, query, max_results):
            self.assertIn(account, {"SG", "Drive1"})
            self.assertEqual(query, "newer_than:7d -in:sent")
            self.assertEqual(max_results, 2)
            return {
                "status": "ok",
                "count": 1,
                "summary": summary,
                "messages": [private_message],
            }

        with (
            patch.object(application, "GMAIL_MONITOR_SECRET", "expected-secret"),
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application, "_gmail_triage_one_account", side_effect=triage) as run_triage,
        ):
            response = self.client.post(
                "/internal/gmail/triage/run?summary_only=false",
                headers={"X-Gmail-Monitor-Secret": "expected-secret"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(set(payload["accounts"]), {"SG", "Drive1"})
        self.assertEqual(payload["summary"]["total"], 2)
        self.assertEqual(run_triage.call_count, 2)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        for sentinel in (
            "PRIVATE_MESSAGE_ID",
            "PRIVATE_SUBJECT_SENTINEL",
            "PRIVATE_BODY_SENTINEL",
            "PRIVATE_SNIPPET_SENTINEL",
        ):
            self.assertNotIn(sentinel, response.get_data(as_text=True))
        for account in payload["accounts"].values():
            self.assertNotIn("messages", account)
        self.assertTrue(connection.closed)

    def test_google_oauth_initiation_requires_publish_secret_before_state_creation(self):
        with (
            patch.object(application, "PUBLISH_SECRET", "expected-secret"),
            patch.object(application, "create_server_oauth_state") as create_state,
        ):
            response = self.client.post("/google/login", json={"account": "SG"})
        self.assertEqual(response.status_code, 401)
        create_state.assert_not_called()

    def test_gmail_account_allowlist_excludes_drive2_and_drive5(self):
        self.assertEqual(application.normalize_gmail_account_name("SG"), "SG")
        self.assertEqual(application.normalize_gmail_account_name("drive1"), "Drive1")
        for account in ("Drive2", "Drive5", "unknown"):
            with self.subTest(account=account):
                with self.assertRaises(ValueError):
                    application.normalize_gmail_account_name(account)

    def test_google_oauth_requests_gmail_readonly_only_for_sg_and_drive1(self):
        for account in ("SG", "Drive1"):
            with self.subTest(account=account):
                with (
                    patch.object(application, "PUBLISH_SECRET", "expected-secret"),
                    patch.object(application, "require_session_secret", return_value=None),
                    patch.object(application, "GOOGLE_CLIENT_ID", "client-id"),
                    patch.object(application, "GOOGLE_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth"),
                    patch.object(application, "GOOGLE_REDIRECT_URI", "https://example.test/google/callback"),
                    patch.object(application, "get_oauth_browser_id", return_value="browser-id"),
                    patch.object(application, "create_server_oauth_state") as create_state,
                ):
                    response = self.client.post(
                        "/google/login",
                        json={"account": account},
                        headers={"X-Publish-Secret": "expected-secret"},
                    )
                self.assertEqual(response.status_code, 302)
                query = parse_qs(urlparse(response.location).query)
                self.assertEqual(query["scope"], [application.GOOGLE_GMAIL_READONLY_SCOPE])
                create_state.assert_called_once_with("google", ANY, "browser-id", account_name=account)

    def test_drive5_oauth_remains_drive_readonly_and_never_requests_calendar(self):
        with (
            patch.object(application, "PUBLISH_SECRET", "expected-secret"),
            patch.object(application, "require_session_secret", return_value=None),
            patch.object(application, "GOOGLE_CLIENT_ID", "client-id"),
            patch.object(application, "GOOGLE_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth"),
            patch.object(application, "GOOGLE_REDIRECT_URI", "https://example.test/google/callback"),
            patch.object(application, "get_oauth_browser_id", return_value="browser-id"),
            patch.object(application, "create_server_oauth_state"),
        ):
            response = self.client.post(
                "/google/login",
                json={"account": "Drive5"},
                headers={"X-Publish-Secret": "expected-secret"},
            )
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response.location).query)
        self.assertEqual(query["scope"], [application.GOOGLE_DRIVE_READONLY_SCOPE])
        self.assertNotIn("calendar.readonly", query["scope"][0])


if __name__ == "__main__":
    unittest.main()
