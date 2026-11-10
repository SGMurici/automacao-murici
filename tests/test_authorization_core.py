import json
import unittest

import authorization_core


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


class TenantAuthorizationTests(unittest.TestCase):
    def test_active_membership_returns_role_and_scopes_query_to_tenant_user(self):
        conn = FakeConnection(one=("admin",))
        role = authorization_core.active_tenant_role(
            conn, "user-a", "tenant-a", allowed_roles={"owner", "admin"}
        )
        self.assertEqual(role, "admin")
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("tenant_id = %s", query)
        self.assertIn("user_id = %s", query)
        self.assertIn("status = 'active'", query)
        self.assertEqual(params, ("tenant-a", "user-a"))

    def test_missing_or_disallowed_membership_is_denied(self):
        self.assertIsNone(
            authorization_core.active_tenant_role(
                FakeConnection(one=None), "user-a", "tenant-b"
            )
        )
        self.assertIsNone(
            authorization_core.active_tenant_role(
                FakeConnection(one=("member",)), "user-a", "tenant-a",
                allowed_roles={"owner"},
            )
        )

    def test_invalid_allowed_roles_are_rejected(self):
        with self.assertRaises(ValueError):
            authorization_core.active_tenant_role(
                FakeConnection(), "user-a", "tenant-a", allowed_roles={"root"}
            )

    def test_consent_is_recorded_as_append_only_event(self):
        conn = FakeConnection(one=("consent-event-id",))
        result = authorization_core.record_consent_event(
            conn, "user-a", "career_data_processing", "v1", "granted",
            "android_app", tenant_id="tenant-a", metadata={"screen": "signup"},
        )
        self.assertEqual(result, "consent-event-id")
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("INSERT INTO consent_events", query)
        self.assertEqual(params[5], "granted")
        self.assertEqual(json.loads(params[-1]), {"screen": "signup"})

    def test_invalid_consent_decision_is_rejected(self):
        with self.assertRaises(ValueError):
            authorization_core.record_consent_event(
                FakeConnection(), "user-a", "analytics", "v1", "yes", "android"
            )

    def test_audit_event_uses_minimal_structured_metadata(self):
        conn = FakeConnection(one=("audit-event-id",))
        result = authorization_core.record_audit_event(
            conn, "profile.export", "success", actor_user_id="user-a",
            tenant_id="tenant-a", resource_type="profile",
            resource_id="profile-a", metadata={"format": "encrypted_backup"},
        )
        self.assertEqual(result, "audit-event-id")
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("INSERT INTO audit_events", query)
        self.assertEqual(params[6], "success")
        self.assertEqual(json.loads(params[-1]), {"format": "encrypted_backup"})

    def test_invalid_audit_result_is_rejected(self):
        with self.assertRaises(ValueError):
            authorization_core.record_audit_event(
                FakeConnection(), "profile.read", "maybe"
            )


if __name__ == "__main__":
    unittest.main()
