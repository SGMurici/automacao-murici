"""Basic source-level safety checks for the Flask application.

These tests avoid importing app.py, which may depend on deployment environment
variables and external services.
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


class AppSourceSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source, filename=str(APP_PATH))

    def test_app_has_request_size_limit(self):
        self.assertIn("MAX_CONTENT_LENGTH", self.source)
        self.assertIn("1 * 1024 * 1024", self.source)

    def test_sensitive_configuration_uses_environment_variables(self):
        for variable in (
            "LINKEDIN_CLIENT_SECRET",
            "GOOGLE_CLIENT_SECRET",
            "TOKEN_ENCRYPTION_KEY",
            "PUBLISH_SECRET",
            "FLASK_SECRET_KEY",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, self.source)
        self.assertIn("os.environ.get", self.source)

    def test_automatic_linkedin_analytics_is_disabled_by_default(self):
        self.assertIn("LINKEDIN_ANALYTICS_AUTOMATIC_ENABLED", self.source)
        self.assertIn('"false"', self.source)

    def test_source_parses_as_python(self):
        self.assertIsInstance(self.tree, ast.Module)


if __name__ == "__main__":
    unittest.main()
