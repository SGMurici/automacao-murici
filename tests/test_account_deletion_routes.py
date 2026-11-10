import unittest
from unittest.mock import patch

import app as application


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class AccountDeletionRouteTests(unittest.TestCase):
    def setUp(self):
        application.app.config.update(TESTING=True)
        self.client = application.app.test_client()

    def test_deletion_request_requires_authenticated_session(self):
        with patch.object(application, "get_db_connection") as get_db:
            response = self.client.post(
                "/api/v1/account/deletion-request",
                json={"confirmacao": "EXCLUIR MINHA CONTA"},
            )
        self.assertEqual(response.status_code, 401)
        get_db.assert_not_called()

    def test_deletion_request_requires_exact_confirmation(self):
        with patch.object(application, "get_db_connection") as get_db:
            response = self.client.post(
                "/api/v1/account/deletion-request",
                headers={"Authorization": "Bearer " + "x" * 48},
                json={"confirmacao": "excluir"},
            )
        self.assertEqual(response.status_code, 400)
        get_db.assert_not_called()

    def test_deletion_request_returns_one_time_receipt_without_caching(self):
        connection = FakeConnection()
        deletion = {"request_id": "request-123", "receipt": "r" * 48}
        with (
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application.identity_core, "validate_session", return_value="user-123"),
            patch.object(application.identity_core, "is_recent_session", return_value=True),
            patch.object(
                application.account_deletion_core,
                "request_account_deletion",
                return_value=deletion,
            ) as request_deletion,
        ):
            response = self.client.post(
                "/api/v1/account/deletion-request",
                headers={"Authorization": "Bearer " + "x" * 48},
                json={"confirmacao": "EXCLUIR MINHA CONTA"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertEqual(response.get_json()["comprovante_exclusao"], "r" * 48)
        request_deletion.assert_called_once_with(connection, "user-123")

    def test_deletion_request_requires_recent_reauthentication(self):
        connection = FakeConnection()
        with (
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(application.identity_core, "validate_session", return_value="user-123"),
            patch.object(application.identity_core, "is_recent_session", return_value=False),
            patch.object(application.account_deletion_core, "request_account_deletion") as request_deletion,
        ):
            response = self.client.post(
                "/api/v1/account/deletion-request",
                headers={"Authorization": "Bearer " + "x" * 48},
                json={"confirmacao": "EXCLUIR MINHA CONTA"},
            )
        self.assertEqual(response.status_code, 401)
        request_deletion.assert_not_called()

    def test_deletion_status_requires_receipt(self):
        with patch.object(application, "get_db_connection") as get_db:
            response = self.client.get("/api/v1/account/deletion-status")
        self.assertEqual(response.status_code, 401)
        get_db.assert_not_called()

    def test_deletion_status_returns_minimal_progress_without_caching(self):
        connection = FakeConnection()
        expected = {
            "request_id": "request-123",
            "status": "requested",
            "steps": [{"system": "primary_database", "status": "pending"}],
        }
        with (
            patch.object(application, "get_db_connection", return_value=connection),
            patch.object(
                application.account_deletion_core,
                "get_deletion_status",
                return_value=expected,
            ) as get_status,
        ):
            response = self.client.get(
                "/api/v1/account/deletion-status",
                headers={"X-Deletion-Receipt": "r" * 48},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.assertEqual(response.get_json(), expected)
        get_status.assert_called_once_with(connection, "r" * 48)


if __name__ == "__main__":
    unittest.main()
