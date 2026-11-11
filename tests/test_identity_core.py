import hashlib
import unittest
from datetime import datetime, timezone

import identity_core


class FakeCursor:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = many or []
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


class IdentitySessionTests(unittest.TestCase):
    def test_hash_requires_long_opaque_token(self):
        with self.assertRaises(ValueError):
            identity_core.hash_session_token("short")
        token = "x" * 48
        self.assertEqual(
            identity_core.hash_session_token(token),
            hashlib.sha256(token.encode()).hexdigest(),
        )

    def test_issue_session_stores_only_hash_and_bounded_ttl(self):
        conn = FakeConnection(one=("token-hash",))
        token = identity_core.issue_session(
            conn, "user-123", ttl_seconds=600, device_label="Android"
        )
        self.assertGreaterEqual(len(token), 32)
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("INSERT INTO auth_sessions", query)
        self.assertIn("authenticated_at", query)
        self.assertIn("status = 'active'", query)
        self.assertEqual(params[0], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, params)
        self.assertEqual(params[1:], (600, "Android", "user-123"))

    def test_issue_session_rejects_unbounded_ttl(self):
        conn = FakeConnection()
        with self.assertRaises(ValueError):
            identity_core.issue_session(conn, "user-123", ttl_seconds=1)
        self.assertEqual(conn.fake_cursor.calls, [])

    def test_validate_session_requires_active_user_and_unrevoked_unexpired_session(self):
        conn = FakeConnection(one=("user-123",))
        token = "t" * 48
        user_id = identity_core.validate_session(conn, token)
        self.assertEqual(user_id, "user-123")
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("u.status = 'active'", query)
        self.assertIn("s.revoked_at IS NULL", query)
        self.assertIn("s.expires_at > NOW()", query)
        self.assertEqual(params, (hashlib.sha256(token.encode()).hexdigest(),))

    def test_recent_session_requires_recent_creation_and_active_user(self):
        conn = FakeConnection(one=(1,))
        self.assertTrue(identity_core.is_recent_session(conn, "r" * 48, 900))
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("s.authenticated_at >=", query)
        self.assertIn("u.status = 'active'", query)
        self.assertEqual(params, (hashlib.sha256(("r" * 48).encode()).hexdigest(), 900))

    def test_recent_session_rejects_invalid_window(self):
        conn = FakeConnection()
        with self.assertRaises(ValueError):
            identity_core.is_recent_session(conn, "r" * 48, 30)
        self.assertEqual(conn.fake_cursor.calls, [])

    def test_rotate_session_revokes_old_and_creates_new(self):
        auth_time = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
        conn = FakeConnection(one=("user-123", auth_time))
        old_token = "o" * 48
        new_token = identity_core.rotate_session(conn, old_token, ttl_seconds=900)
        self.assertIsInstance(new_token, str)
        self.assertNotEqual(new_token, old_token)
        update_query, update_params = conn.fake_cursor.calls[0]
        insert_query, insert_params = conn.fake_cursor.calls[1]
        self.assertIn("SET revoked_at = NOW()", update_query)
        self.assertIn("replaced_by_token_hash", update_query)
        self.assertIn("RETURNING s.user_id, s.authenticated_at", update_query)
        self.assertEqual(update_params[1], hashlib.sha256(old_token.encode()).hexdigest())
        self.assertIn("INSERT INTO auth_sessions", insert_query)
        self.assertIn("authenticated_at", insert_query)
        self.assertEqual(insert_params, (
            hashlib.sha256(new_token.encode()).hexdigest(),
            "user-123",
            auth_time,
            900,
            None,
        ))

    def test_revoked_or_expired_session_cannot_be_rotated(self):
        conn = FakeConnection(one=None)
        result = identity_core.rotate_session(conn, "o" * 48)
        self.assertIsNone(result)
        self.assertEqual(len(conn.fake_cursor.calls), 1)

    def test_revoke_session_is_idempotent(self):
        conn = FakeConnection(one=("hash",))
        self.assertTrue(identity_core.revoke_session(conn, "r" * 48))
        self.assertIn("revoked_at = NOW()", conn.fake_cursor.calls[0][0])

    def test_revoke_all_sessions_returns_count(self):
        conn = FakeConnection(many=[("a",), ("b",), ("c",)])
        self.assertEqual(identity_core.revoke_all_sessions(conn, "user-123"), 3)
        self.assertIn("WHERE user_id = %s", conn.fake_cursor.calls[0][0])


if __name__ == "__main__":
    unittest.main()
