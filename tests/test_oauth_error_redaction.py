import io
import unittest
from unittest.mock import patch
import urllib.error

import app as application


class OAuthErrorRedactionTests(unittest.TestCase):
    def setUp(self):
        self.client = application.app.test_client()
        self.secret_patch = patch.object(
            application.app, "secret_key", "test-session-secret"
        )
        self.secret_patch.start()
        self.addCleanup(self.secret_patch.stop)

    def provider_error(self, url):
        return urllib.error.HTTPError(
            url, 401, "Unauthorized", hdrs=None,
            fp=io.BytesIO(
                b'{"error":"invalid_client","error_description":"private provider detail"}'
            ),
        )

    def test_linkedin_token_error_does_not_expose_provider_body(self):
        with self.client.session_transaction() as sess:
            sess["oauth_browser_id"] = "browser-session-id"
        with patch.object(
            application, "consume_server_oauth_state",
            return_value={"provider": "linkedin", "account_name": None},
        ), patch.object(application, "LINKEDIN_CLIENT_ID", "client-id"), patch.object(
            application, "LINKEDIN_CLIENT_SECRET", "client-secret"
        ), patch.object(
            application, "LINKEDIN_REDIRECT_URI", "https://example.test/callback"
        ), patch(
            "app.urllib.request.urlopen",
            side_effect=self.provider_error("https://provider.test/token"),
        ):
            response = self.client.get(
                "/linkedin/callback?code=authorization-code&state=valid-state"
            )

        self.assertEqual(response.status_code, 502)
        body = response.get_data(as_text=True)
        self.assertIn("Falha ao obter token do LinkedIn", body)
        self.assertNotIn("invalid_client", body)
        self.assertNotIn("private provider detail", body)

    def test_google_token_error_does_not_expose_provider_body(self):
        with self.client.session_transaction() as sess:
            sess["oauth_browser_id"] = "browser-session-id"
        with patch.object(
            application, "consume_server_oauth_state",
            return_value={"provider": "google", "account_name": "Drive5"},
        ), patch.object(application, "GOOGLE_CLIENT_ID", "client-id"), patch.object(
            application, "GOOGLE_CLIENT_SECRET", "client-secret"
        ), patch.object(
            application, "GOOGLE_REDIRECT_URI", "https://example.test/callback"
        ), patch(
            "app.urllib.request.urlopen",
            side_effect=self.provider_error("https://provider.test/token"),
        ):
            response = self.client.get(
                "/google/callback?code=authorization-code&state=valid-state"
            )

        self.assertEqual(response.status_code, 502)
        body = response.get_data(as_text=True)
        self.assertIn("Falha ao obter token do Google", body)
        self.assertNotIn("invalid_client", body)
        self.assertNotIn("private provider detail", body)


if __name__ == "__main__":
    unittest.main()
