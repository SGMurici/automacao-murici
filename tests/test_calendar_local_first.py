import unittest
from unittest.mock import patch

import app as application


class LocalFirstCalendarTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.secret_key_patch = patch.dict(
            application.app.config, {"SECRET_KEY": "test-flask-session-secret"}
        )
        self.secret_key_patch.start()
        self.addCleanup(self.secret_key_patch.stop)
        self.client_id_patch = patch.object(application, "GOOGLE_CLIENT_ID", "test-google-client")
        self.client_id_patch.start()
        self.addCleanup(self.client_id_patch.stop)

    def test_calendar_oauth_purpose_is_rejected(self):
        response = self.client.get(
            "/google/login?account=SG&purpose=calendar_readonly"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("calendário próprio", response.get_json()["mensagem"])

    def test_external_google_calendar_route_is_not_registered(self):
        response = self.client.get("/google-calendar/check")
        self.assertEqual(response.status_code, 404)

    def test_gmail_oauth_purpose_remains_available(self):
        with patch.object(application, "GOOGLE_REDIRECT_URI", "https://example.test/callback"):
            response = self.client.get("/google/login?account=SG&purpose=gmail")
        self.assertEqual(response.status_code, 302)
        self.assertIn("gmail.readonly", response.headers["Location"])
        self.assertNotIn("calendar.readonly", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
