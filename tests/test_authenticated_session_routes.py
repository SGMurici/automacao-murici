import unittest
from unittest.mock import patch

import app as application


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows=None):
        self.fake_cursor = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.fake_cursor


class AuthenticatedSessionRouteTests(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True)
        self.client = application.app.test_client()

    def test_current_user_requires_bearer_header_without_database_access(self):
        with patch.object(application, "get_db_connection") as get_db:
            response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 401)
        get_db.assert_not_called()

    def test_current_user_rejects_invalid_session_without_listing_tenants(self):
        connection = FakeConnection()
        with (
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application.identity_core, "validate_session", return_value=None),
        ):
            response = self.client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + "x" * 48}
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(connection.fake_cursor.calls, [])

    def test_current_user_returns_only_active_membership_rows(self):
        connection = FakeConnection(rows=[
            ("tenant-1", "personal", "Minha conta", "owner"),
            ("tenant-2", "shared", "Equipe", "member"),
        ])
        with (
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application.identity_core, "validate_session", return_value="user-1"),
        ):
            response = self.client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + "x" * 48}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        payload = response.get_json()
        self.assertEqual(payload["usuario"]["id"], "user-1")
        self.assertEqual(len(payload["tenants"]), 2)
        self.assertEqual(payload["tenants"][0]["papel"], "owner")
        query, params = connection.fake_cursor.calls[0]
        self.assertIn("m.user_id = %s", query)
        self.assertIn("m.status = 'active'", query)
        self.assertEqual(params, ("user-1",))

    def test_logout_validates_then_revokes_presented_session(self):
        connection = FakeConnection()
        with (
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application.identity_core, "validate_session", return_value="user-1") as validate,
            patch.object(application.identity_core, "revoke_session", return_value=True) as revoke,
        ):
            response = self.client.post(
                "/api/v1/logout", headers={"Authorization": "Bearer " + "x" * 48}
            )

        self.assertEqual(response.status_code, 200)
        validate.assert_called_once()
        revoke.assert_called_once_with(connection, "x" * 48)

    def test_logout_rejects_invalid_session_without_revocation(self):
        connection = FakeConnection()
        with (
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application.identity_core, "validate_session", return_value=None),
            patch.object(application.identity_core, "revoke_session") as revoke,
        ):
            response = self.client.post(
                "/api/v1/logout", headers={"Authorization": "Bearer " + "x" * 48}
            )
        self.assertEqual(response.status_code, 401)
        revoke.assert_not_called()

    def test_malformed_bearer_header_is_rejected(self):
        with patch.object(application, "get_db_connection") as get_db:
            response = self.client.get(
                "/api/v1/me", headers={"Authorization": "Bearer  short"}
            )
        self.assertEqual(response.status_code, 401)
        get_db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
