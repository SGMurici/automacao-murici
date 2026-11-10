import hashlib
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import drive_backup_oauth as oauth


class FakeCursor:
    def __init__(self, one=None):
        self.one = one
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def execute(self, query, params=None):
        self.calls.append((query, params))
    def fetchone(self):
        return self.one


class FakeConnection:
    def __init__(self, one=None):
        self.fake_cursor = FakeCursor(one)
    def cursor(self):
        return self.fake_cursor


class DriveBackupOAuthTests(unittest.TestCase):
    def setUp(self):
        self.vault = {}
        def encrypt(value):
            ciphertext = b"cipher:" + hashlib.sha256(value.encode()).digest()
            self.vault[ciphertext] = value
            return ciphertext
        self.encrypt = encrypt
        self.decrypt = lambda value: self.vault[value]

    def test_create_flow_uses_pkce_s256_and_minimal_scope(self):
        conn = FakeConnection(one=("state-hash",))
        result = oauth.create_flow(
            conn, user_id="user-1", tenant_id="tenant-1",
            redirect_uri="https://api.example.test/api/v1/integrations/google-drive/callback",
            client_id="client-id", encrypt=self.encrypt,
        )
        params = parse_qs(urlparse(result["authorization_url"]).query)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["response_type"], ["code"])
        self.assertIn(oauth.GOOGLE_DRIVE_SCOPE, params["scope"][0])
        self.assertNotIn("https://www.googleapis.com/auth/drive ", params["scope"][0])
        self.assertEqual(params["state"], [result["state"]])
        query, values = conn.fake_cursor.calls[0]
        self.assertIn("u.status = 'active'", query)
        self.assertIn("m.status = 'active'", query)
        self.assertEqual(values[1:3], (oauth.FLOW_PROVIDER, oauth.FLOW_PURPOSE))
        self.assertTrue(values[3].startswith(b"cipher:"))
        self.assertNotIn(result["state"].encode(), values[3])
        self.assertNotIn(result["state"], repr(values))

    def test_rejects_non_https_redirect_and_missing_client_id(self):
        conn = FakeConnection(one=("x",))
        with self.assertRaises(ValueError):
            oauth.create_flow(
                conn, user_id="u", tenant_id="t", redirect_uri="http://bad",
                client_id="client", encrypt=self.encrypt,
            )
        with self.assertRaises(ValueError):
            oauth.create_flow(
                conn, user_id="u", tenant_id="t", redirect_uri="https://good",
                client_id="", encrypt=self.encrypt,
            )
        self.assertEqual(conn.fake_cursor.calls, [])

    def test_create_flow_requires_active_tenant_membership(self):
        conn = FakeConnection(one=None)
        with self.assertRaises(PermissionError):
            oauth.create_flow(
                conn, user_id="u", tenant_id="t", redirect_uri="https://good",
                client_id="client", encrypt=self.encrypt,
            )

    def test_consume_flow_is_atomic_single_use_and_returns_pkce_context(self):
        row = ("user-1", "tenant-1", self.encrypt("v" * 50), "https://redirect.test/callback")
        conn = FakeConnection(one=row)
        state = "s" * 43
        result = oauth.consume_flow(conn, state=state, decrypt=self.decrypt)
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("DELETE FROM oauth_states", query)
        self.assertIn("expires_at > NOW()", query)
        self.assertEqual(params, (hashlib.sha256(state.encode()).hexdigest(), "google", "drive_backup"))
        self.assertEqual(result["user_id"], "user-1")
        self.assertEqual(result["tenant_id"], "tenant-1")
        self.assertEqual(result["code_verifier"], "v" * 50)
        self.assertEqual(result["redirect_uri"], "https://redirect.test/callback")

    def test_expired_or_unknown_state_returns_none(self):
        conn = FakeConnection(one=None)
        self.assertIsNone(oauth.consume_flow(conn, state="s" * 43, decrypt=self.decrypt))

    def test_invalid_state_returns_none_without_database_query(self):
        conn = FakeConnection(one=None)
        self.assertIsNone(oauth.consume_flow(conn, state="short", decrypt=self.decrypt))
        self.assertEqual(conn.fake_cursor.calls, [])

    def test_decryption_failure_does_not_return_verifier(self):
        conn = FakeConnection(one=("user", "tenant", b"cipher", "https://redirect"))
        with self.assertRaises(ValueError):
            oauth.consume_flow(conn, state="s" * 43, decrypt=None)


if __name__ == "__main__":
    unittest.main()
