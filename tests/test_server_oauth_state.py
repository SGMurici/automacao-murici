import hashlib
import unittest
from unittest.mock import patch

import app as application


class FakeCursor:
    def __init__(self, returned_row=None):
        self.returned_row = returned_row
        self.calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        return self.returned_row


class FakeConnection:
    def __init__(self, returned_row=None):
        self.fake_cursor = FakeCursor(returned_row)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True


class ServerOAuthStateTests(unittest.TestCase):
    def test_create_persists_hash_not_raw_state_and_commits(self):
        connection = FakeConnection()
        raw_state = "high-entropy-oauth-state"

        with patch.object(application, "get_db_connection", return_value=connection):
            result = application.create_server_oauth_state(
                "google", raw_state, "browser-session-id", account_name="Drive5"
            )

        self.assertEqual(result, raw_state)
        self.assertTrue(connection.committed)
        insert_query, params = connection.fake_cursor.calls[1]
        self.assertIn("INSERT INTO oauth_states", insert_query)
        self.assertEqual(params[0], hashlib.sha256(raw_state.encode()).hexdigest())
        self.assertNotIn(raw_state, params)
        self.assertEqual(params[1:], ("google", "browser-session-id", "Drive5"))

    def test_consume_uses_atomic_delete_with_provider_browser_and_expiry(self):
        connection = FakeConnection(returned_row=("Drive5",))
        raw_state = "high-entropy-oauth-state"

        with patch.object(application, "get_db_connection", return_value=connection):
            result = application.consume_server_oauth_state(
                "google", raw_state, "browser-session-id"
            )

        self.assertEqual(
            result, {"provider": "google", "account_name": "Drive5"}
        )
        self.assertTrue(connection.committed)
        query, params = connection.fake_cursor.calls[0]
        self.assertIn("DELETE FROM oauth_states", query)
        self.assertIn("RETURNING account_name", query)
        self.assertIn("expires_at > NOW()", query)
        self.assertEqual(
            params,
            (
                hashlib.sha256(raw_state.encode()).hexdigest(),
                "google",
                "browser-session-id",
            ),
        )

    def test_unknown_or_missing_context_is_rejected_without_database_access(self):
        with patch.object(application, "get_db_connection") as db:
            self.assertIsNone(
                application.consume_server_oauth_state(
                    "google", "state", None
                )
            )
            self.assertIsNone(
                application.consume_server_oauth_state(
                    "unknown", "state", "browser"
                )
            )
            with self.assertRaises(ValueError):
                application.create_server_oauth_state(
                    "unknown", "state", "browser"
                )
            db.assert_not_called()

    def test_invalid_state_is_rejected_without_database_access(self):
        with patch.object(application, "get_db_connection") as db:
            self.assertIsNone(
                application.consume_server_oauth_state(
                    "google", "", "browser-session-id"
                )
            )
            db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
