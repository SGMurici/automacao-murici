import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import drive_backup_connections as drive


class FakeCursor:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = list(many or [])
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def execute(self, query, params=None):
        self.calls.append((query, params))
    def fetchone(self):
        return self.one
    def fetchall(self):
        return self.many


class FakeConnection:
    def __init__(self, one=None, many=None):
        self.fake_cursor = FakeCursor(one=one, many=many)
    def cursor(self):
        return self.fake_cursor


class DriveBackupConnectionTests(unittest.TestCase):
    def setUp(self):
        self.scopes = [drive.REQUIRED_SCOPE, "openid", "email"]
        self.vault = {}
        def encrypt(value):
            ciphertext = b"cipher:" + hashlib.sha256(value.encode()).digest()
            self.vault[ciphertext] = value
            return ciphertext
        self.encrypt = encrypt
        self.decrypt = lambda value: self.vault[value]

    def test_accepts_minimal_drive_file_scope(self):
        self.assertEqual(
            drive.validate_granted_scopes(self.scopes),
            sorted(self.scopes),
        )

    def test_rejects_missing_broad_or_unrelated_scope(self):
        invalid_scope_sets = (
            ["openid"],
            [drive.REQUIRED_SCOPE, "https://www.googleapis.com/auth/drive"],
            [drive.REQUIRED_SCOPE, "https://www.googleapis.com/auth/gmail.readonly"],
            [drive.REQUIRED_SCOPE, "https://www.googleapis.com/auth/calendar"],
            [drive.REQUIRED_SCOPE, None],
        )
        for scopes in invalid_scope_sets:
            with self.subTest(scopes=scopes), self.assertRaises(ValueError):
                drive.validate_granted_scopes(scopes)

    def test_save_encrypts_tokens_and_binds_active_tenant_membership(self):
        conn = FakeConnection(one=("connection-1",))
        connection_id = drive.save_connection(
            conn,
            user_id="user-1",
            tenant_id="tenant-1",
            google_subject="google-subject-1",
            account_label="client@example.test",
            granted_scopes=self.scopes,
            access_token="access-secret",
            refresh_token="refresh-secret",
            token_expires_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
            encrypt=self.encrypt,
        )
        query, params = conn.fake_cursor.calls[0]
        self.assertEqual(connection_id, "connection-1")
        self.assertIn("u.status = 'active'", query)
        self.assertIn("m.status = 'active'", query)
        self.assertIn("WHERE external_connections.user_id = EXCLUDED.user_id", query)
        self.assertEqual(params[0], drive.PROVIDER)
        self.assertEqual(params[4], self.encrypt("access-secret"))
        self.assertEqual(params[5], self.encrypt("refresh-secret"))
        self.assertNotIn("access-secret", repr(params))
        self.assertNotIn("refresh-secret", repr(params))

    def test_save_rejects_inactive_or_foreign_membership(self):
        conn = FakeConnection(one=None)
        with self.assertRaises(PermissionError):
            drive.save_connection(
                conn, user_id="user-1", tenant_id="tenant-2",
                google_subject="subject", account_label=None,
                granted_scopes=self.scopes, access_token="a",
                refresh_token="r", token_expires_at=None, encrypt=self.encrypt,
            )

    def test_get_connection_is_scoped_and_decrypts_only_after_match(self):
        row = (
            "connection-1", "subject-1", "account@example.test",
            self.scopes, self.encrypt("a"), self.encrypt("r"), None,
        )
        conn = FakeConnection(one=row)
        result = drive.get_connection(
            conn, user_id="user-1", tenant_id="tenant-1",
            connection_id="connection-1", decrypt=self.decrypt,
        )
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("user_id = %s AND tenant_id = %s", query)
        self.assertEqual(params, ("connection-1", "user-1", "tenant-1", drive.PROVIDER))
        self.assertEqual(result["access_token"], "a")
        self.assertEqual(result["refresh_token"], "r")

    def test_get_connection_does_not_disclose_cross_tenant_credentials(self):
        conn = FakeConnection(one=None)
        self.assertIsNone(
            drive.get_connection(
                conn, user_id="user-2", tenant_id="tenant-2",
                connection_id="connection-1", decrypt=self.decrypt,
            )
        )
        self.assertNotIn("access_token", repr(conn.fake_cursor.calls[0][1]))

    def test_refresh_updates_only_owned_connection(self):
        conn = FakeConnection(one=("connection-1",))
        updated = drive.update_tokens(
            conn, user_id="user-1", tenant_id="tenant-1",
            connection_id="connection-1", access_token="new-a",
            refresh_token="new-r", token_expires_at=None, encrypt=self.encrypt,
        )
        query, params = conn.fake_cursor.calls[0]
        self.assertTrue(updated)
        self.assertIn("user_id = %s AND tenant_id = %s", query)
        self.assertEqual(params[0:2], (self.encrypt("new-a"), self.encrypt("new-r")))

    def test_revoke_erases_token_ciphertext_and_is_owner_scoped(self):
        conn = FakeConnection(one=("connection-1",))
        self.assertTrue(drive.revoke_connection(
            conn, user_id="user-1", tenant_id="tenant-1", connection_id="connection-1"
        ))
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("access_token_ciphertext = NULL", query)
        self.assertIn("refresh_token_ciphertext = NULL", query)
        self.assertEqual(params, ("connection-1", "user-1", "tenant-1", drive.PROVIDER))

    def test_list_returns_metadata_without_token_columns(self):
        conn = FakeConnection(many=[
            ("id", "subject", "label", self.scopes, "active", None, None, None)
        ])
        result = drive.list_connections(conn, user_id="user-1", tenant_id="tenant-1")
        query, params = conn.fake_cursor.calls[0]
        self.assertNotIn("token_ciphertext", query)
        self.assertEqual(params, ("user-1", "tenant-1", drive.PROVIDER))
        self.assertNotIn("access_token", result[0])
        self.assertNotIn("refresh_token", result[0])

    def test_save_rejects_missing_tokens_before_database_write(self):
        conn = FakeConnection()
        with self.assertRaises(ValueError):
            drive.save_connection(
                conn, user_id="user-1", tenant_id="tenant-1",
                google_subject="subject", account_label=None,
                granted_scopes=self.scopes, access_token="",
                refresh_token="refresh", token_expires_at=None, encrypt=self.encrypt,
            )
        self.assertEqual(conn.fake_cursor.calls, [])


if __name__ == "__main__":
    unittest.main()
