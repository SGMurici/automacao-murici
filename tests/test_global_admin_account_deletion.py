"""Global-administrator safety gates in account deletion."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import account_deletion_core


class FakeCursor:
    def __init__(self, one_rows=None, all_rows=None):
        self.one_rows = list(one_rows or [])
        self.all_rows = list(all_rows or [])
        self.calls = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        self.rowcount = 1 if (
            "DELETE FROM global_administrators" in query
            or "DELETE FROM app_users" in query
            or "UPDATE app_users" in query
        ) else 0

    def executemany(self, query, params):
        self.calls.append((query, params))

    def fetchone(self):
        return self.one_rows.pop(0) if self.one_rows else None

    def fetchall(self):
        return self.all_rows.pop(0) if self.all_rows else []


class FakeConnection:
    def __init__(self, one_rows=None, all_rows=None):
        self.cursor_value = FakeCursor(one_rows, all_rows)

    def cursor(self):
        return self.cursor_value


class GlobalAdministratorDeletionTests(unittest.TestCase):
    def test_active_or_suspended_global_grant_blocks_deletion_request(self):
        for grant in (("active", None), ("suspended", None)):
            with self.subTest(grant=grant):
                conn = FakeConnection(one_rows=[("active",), grant])
                with self.assertRaises(account_deletion_core.GlobalAdministratorMustBeRevoked):
                    account_deletion_core.request_account_deletion(conn, "user-1")
                queries = [query for query, _ in conn.cursor_value.calls]
                self.assertFalse(any("INSERT INTO account_deletion_requests" in q for q in queries))

    def test_revoked_global_grant_allows_deletion_request(self):
        revoked_at = datetime(2026, 11, 12, tzinfo=timezone.utc)
        conn = FakeConnection(one_rows=[("active",), ("revoked", revoked_at)])
        with patch("identity_core.revoke_all_sessions") as revoke:
            result = account_deletion_core.request_account_deletion(conn, "user-1")
        self.assertTrue(result["request_id"])
        self.assertTrue(result["receipt"])
        revoke.assert_called_once_with(conn, "user-1")

    def test_primary_purge_removes_only_revoked_grant_before_user(self):
        revoked_at = datetime(2026, 11, 12, tzinfo=timezone.utc)
        external_steps = [
            (system, "completed", "evidence-" + system)
            for system in (
                "connected_providers", "app_storage", "backups", "legal_retention"
            )
        ]
        conn = FakeConnection(
            one_rows=[("user-1", "processing"), ("revoked", revoked_at)],
            all_rows=[external_steps, [], []],
        )
        self.assertTrue(account_deletion_core.process_primary_database_deletion(conn, "request-1"))
        queries = [query for query, _ in conn.cursor_value.calls]
        grant_delete = next(i for i, q in enumerate(queries) if "DELETE FROM global_administrators" in q)
        user_delete = next(i for i, q in enumerate(queries) if "DELETE FROM app_users" in q)
        self.assertLess(grant_delete, user_delete)
        self.assertIn("status = 'revoked'", queries[grant_delete])
        self.assertIn("revoked_at IS NOT NULL", queries[grant_delete])

    def test_primary_purge_refuses_non_revoked_grant(self):
        external_steps = [
            (system, "completed", "evidence-" + system)
            for system in (
                "connected_providers", "app_storage", "backups", "legal_retention"
            )
        ]
        conn = FakeConnection(
            one_rows=[("user-1", "processing"), ("suspended", None)],
            all_rows=[external_steps, [], []],
        )
        with self.assertRaises(account_deletion_core.GlobalAdministratorMustBeRevoked):
            account_deletion_core.process_primary_database_deletion(conn, "request-1")
        queries = [query for query, _ in conn.cursor_value.calls]
        self.assertFalse(any("DELETE FROM app_users" in q for q in queries))


if __name__ == "__main__":
    unittest.main()
