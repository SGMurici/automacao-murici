import unittest

import global_admin_core


class FakeCursor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self, result):
        self.fake_cursor = FakeCursor(result)

    def cursor(self):
        return self.fake_cursor


class GlobalAdministratorTests(unittest.TestCase):
    def test_active_global_admin_requires_global_grant_and_active_user(self):
        conn = FakeConnection((True,))
        self.assertTrue(global_admin_core.is_active_global_admin(conn, "user-a"))
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("global_administrators", query)
        self.assertIn("g.status = 'active'", query)
        self.assertIn("g.revoked_at IS NULL", query)
        self.assertIn("u.status = 'active'", query)
        self.assertEqual(params, ("user-a",))

    def test_tenant_admin_is_not_implicitly_global_admin(self):
        conn = FakeConnection((False,))
        self.assertFalse(global_admin_core.is_active_global_admin(conn, "tenant-admin"))
        query, _ = conn.fake_cursor.calls[0]
        self.assertIn("global_administrators", query)
        self.assertNotIn("tenant_memberships", query)

    def test_missing_identity_fails_closed_without_database_query(self):
        conn = FakeConnection((True,))
        self.assertFalse(global_admin_core.is_active_global_admin(conn, None))
        self.assertEqual(conn.fake_cursor.calls, [])

    def test_require_global_admin_rejects_missing_or_inactive_grant(self):
        with self.assertRaises(PermissionError):
            global_admin_core.require_global_admin(FakeConnection((False,)), "user-a")

    def test_require_global_admin_accepts_active_grant(self):
        self.assertTrue(
            global_admin_core.require_global_admin(FakeConnection((True,)), "user-a")
        )


if __name__ == "__main__":
    unittest.main()
