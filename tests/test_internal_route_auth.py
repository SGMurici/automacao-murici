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

    def test_internal_diagnostic_routes_reject_missing_secret(self):
        for method, path in (
            ("get", "/db-test"),
            ("get", "/crypto-test"),
        ):
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, 401)

    def test_operational_routes_reject_missing_secret(self):
        protected_routes = (
            ("get", "/google-drive/accounts"),
            ("get", "/google-drive/check"),
            ("get", "/google-drive/art-folder"),
            ("post", "/google-drive/test"),
            ("get", "/google-drive/health"),
            ("get", "/google-drive/router"),
            ("post", "/storage-test"),
            ("post", "/linkedin/publish"),
            ("post", "/scheduler/queue"),
            ("get", "/scheduler/status"),
            ("post", "/scheduler/run"),
            ("get", "/analytics/prepare"),
            ("post", "/analytics/record"),
        )

        for method, path in protected_routes:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, 401)

    def test_operational_routes_reject_incorrect_secret(self):
        headers = {"X-Publish-Secret": "incorrect"}
        protected_routes = (
            ("get", "/db-test"),
            ("get", "/crypto-test"),
            ("get", "/google-drive/accounts"),
            ("get", "/google-drive/check"),
            ("get", "/google-drive/art-folder"),
            ("post", "/google-drive/test"),
            ("get", "/google-drive/health"),
            ("get", "/google-drive/router"),
            ("post", "/storage-test"),
            ("post", "/linkedin/publish"),
            ("post", "/scheduler/queue"),
            ("get", "/scheduler/status"),
            ("post", "/scheduler/run"),
            ("get", "/analytics/prepare"),
            ("post", "/analytics/record"),
        )

        for method, path in protected_routes:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, headers=headers)
                self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
