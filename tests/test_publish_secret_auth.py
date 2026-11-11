import unittest
from unittest.mock import patch

import app as application


class PublishSecretAuthenticationTests(unittest.TestCase):
    def call_auth(self, header_value=None):
        headers = {}
        if header_value is not None:
            headers["X-Publish-Secret"] = header_value

        with application.app.test_request_context(
            "/db-test",
            headers=headers,
        ):
            return application.require_publish_secret()

    def test_missing_header_returns_401(self):
        with patch.object(application, "PUBLISH_SECRET", "valid-secret"):
            result = self.call_auth()

        self.assertIsNotNone(result)
        self.assertEqual(result[1], 401)

    def test_incorrect_ascii_header_returns_403(self):
        with patch.object(application, "PUBLISH_SECRET", "valid-secret"):
            result = self.call_auth("wrong-secret")

        self.assertIsNotNone(result)
        self.assertEqual(result[1], 403)

    def test_non_ascii_header_returns_403_without_raising(self):
        with patch.object(application, "PUBLISH_SECRET", "valid-secret"):
            result = self.call_auth("segredo-com-acentuação")

        self.assertIsNotNone(result)
        self.assertEqual(result[1], 403)

    def test_correct_ascii_header_is_accepted(self):
        with patch.object(application, "PUBLISH_SECRET", "valid-secret"):
            result = self.call_auth("valid-secret")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
