import unittest
from unittest.mock import patch

import app as application


class InternalRouteAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.secret_patch = patch.object(
            application, "PUBLISH_SECRET", "test-operational-secret"
        )
        self.secret_patch.start()
        self.addCleanup(self.secret_patch.stop)

    def test_health_remains_public(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_database_diagnostic_rejects_missing_secret(self):
        response = self.client.get("/db-test")
        self.assertEqual(response.status_code, 401)

    def test_crypto_diagnostic_rejects_missing_secret(self):
        response = self.client.get("/crypto-test")
        self.assertEqual(response.status_code, 401)

    def test_scheduler_rejects_missing_secret(self):
        response = self.client.post("/scheduler/run")
        self.assertEqual(response.status_code, 401)

    def test_internal_routes_reject_incorrect_secret(self):
        headers = {"X-Publish-Secret": "incorrect"}
        responses = [
            self.client.get("/db-test", headers=headers),
            self.client.get("/crypto-test", headers=headers),
            self.client.post("/scheduler/run", headers=headers),
        ]
        self.assertEqual([response.status_code for response in responses], [403, 403, 403])


if __name__ == "__main__":
    unittest.main()
