import unittest
from unittest.mock import patch

import app as application


class SecurityHeadersAndReadinessTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.secret_patch = patch.object(
            application, "PUBLISH_SECRET", "test-operational-secret"
        )
        self.secret_patch.start()
        self.addCleanup(self.secret_patch.stop)

    def test_security_headers_are_applied_to_public_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertEqual(response.headers.get("Permissions-Policy"), "camera=(), microphone=(), geolocation=()")
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_readiness_requires_operational_secret(self):
        response = self.client.get("/readiness")
        self.assertEqual(response.status_code, 401)

    def test_readiness_rejects_incorrect_operational_secret(self):
        response = self.client.get(
            "/readiness", headers={"X-Publish-Secret": "incorrect"}
        )
        self.assertEqual(response.status_code, 403)

    def test_readiness_reports_only_names_and_never_checks_database(self):
        with (
            patch.dict(application.app.config, {"SECRET_KEY": "sentinel-flask-secret"}),
            patch.object(application, "DATABASE_URL", "sentinel-database-url"),
            patch.object(application, "LINKEDIN_CLIENT_ID", "sentinel-linkedin-id"),
            patch.object(application, "LINKEDIN_CLIENT_SECRET", "sentinel-linkedin-secret"),
            patch.object(application, "GOOGLE_CLIENT_ID", "sentinel-google-id"),
            patch.object(application, "GOOGLE_CLIENT_SECRET", "sentinel-google-secret"),
            patch.object(application, "TOKEN_ENCRYPTION_KEY", "sentinel-token-key"),
        ):
            response = self.client.get(
                "/readiness",
                headers={"X-Publish-Secret": "test-operational-secret"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ready")
        self.assertFalse(payload["secrets_exposed"])
        self.assertFalse(payload["database_checked"])
        body = response.get_data(as_text=True)
        for secret in (
            "sentinel-flask-secret", "sentinel-database-url",
            "sentinel-linkedin-id", "sentinel-linkedin-secret",
            "sentinel-google-id", "sentinel-google-secret",
            "sentinel-token-key", "test-operational-secret",
        ):
            self.assertNotIn(secret, body)

    def test_readiness_returns_503_with_missing_setting_names_only(self):
        with (
            patch.dict(application.app.config, {"SECRET_KEY": None}),
            patch.object(application, "DATABASE_URL", None),
            patch.object(application, "LINKEDIN_CLIENT_ID", None),
            patch.object(application, "LINKEDIN_CLIENT_SECRET", None),
            patch.object(application, "GOOGLE_CLIENT_ID", None),
            patch.object(application, "GOOGLE_CLIENT_SECRET", None),
            patch.object(application, "TOKEN_ENCRYPTION_KEY", None),
        ):
            response = self.client.get(
                "/readiness",
                headers={"X-Publish-Secret": "test-operational-secret"},
            )

        self.assertEqual(response.status_code, 503)
        payload = response.get_json()
        self.assertEqual(payload["status"], "configuration_incomplete")
        self.assertIn("DATABASE_URL", payload["missing_settings"])
        self.assertFalse(payload["secrets_exposed"])


if __name__ == "__main__":
    unittest.main()
