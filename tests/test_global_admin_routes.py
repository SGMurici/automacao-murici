"""HTTP boundary tests for global KAPPA administrator sessions."""
import unittest
from unittest.mock import patch

import app as application


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class GlobalAdminRouteTests(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True)
        self.client = application.app.test_client()
        self.token = "x" * 48

    def test_admin_session_requires_bearer_token_before_database_access(self):
        with patch.object(application, "get_db_connection") as get_db:
            response = self.client.get("/api/v1/admin/session")
        self.assertEqual(response.status_code, 401)
        get_db.assert_not_called()

    def test_invalid_session_is_rejected_without_global_admin_lookup(self):
        with (
            patch.object(application, "get_db_connection", return_value=FakeConnection()),
            patch.object(application.identity_core, "validate_session", return_value=None),
            patch.object(application.global_admin_core, "require_global_admin") as require_admin,
            patch.object(application.authorization_core, "record_audit_event") as audit,
        ):
            response = self.client.get(
                "/api/v1/admin/session",
                headers={"Authorization": "Bearer " + self.token},
            )
        self.assertEqual(response.status_code, 401)
        require_admin.assert_not_called()
        audit.assert_not_called()

    def test_tenant_admin_without_global_grant_is_denied_and_audited(self):
        connection = FakeConnection()
        with (
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application.identity_core, "validate_session", return_value="tenant-admin"),
            patch.object(
                application.global_admin_core,
                "require_global_admin",
                side_effect=PermissionError("denied"),
            ),
            patch.object(application.authorization_core, "record_audit_event") as audit,
        ):
            response = self.client.get(
                "/api/v1/admin/session",
                headers={"Authorization": "Bearer " + self.token},
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(audit.call_args.kwargs["result"], "denied")
        self.assertEqual(audit.call_args.kwargs["actor_user_id"], "tenant-admin")

    def test_active_global_admin_receives_minimal_no_store_response(self):
        connection = FakeConnection()
        with (
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application.identity_core, "validate_session", return_value="global-admin"),
            patch.object(application.global_admin_core, "require_global_admin", return_value=True),
            patch.object(application.authorization_core, "record_audit_event") as audit,
        ):
            response = self.client.get(
                "/api/v1/admin/session",
                headers={"Authorization": "Bearer " + self.token},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertEqual(response.get_json(), {
            "status": "ok",
            "usuario": {"id": "global-admin"},
            "administrador_global": True,
        })
        self.assertEqual(audit.call_args.kwargs["result"], "success")


if __name__ == "__main__":
    unittest.main()
