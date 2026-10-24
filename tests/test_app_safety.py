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
        self.assertIn("16 * 1024 * 1024", self.source)
        self.assertIn("MAX_EDITORIAL_IMAGE_BYTES = 15 * 1024 * 1024", self.source)

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

    def test_google_write_operations_are_disabled_by_default(self):
        self.assertIn('"GOOGLE_DRIVE_WRITE_ENABLED", "false"', self.source)
        self.assertIn('"GOOGLE_SHEETS_WRITE_ENABLED", "false"', self.source)
        self.assertIn('return jsonify({\n            "status": "blocked"', self.source)

    def test_image_storage_validates_type_size_and_hash(self):
        for marker in (
            "ALLOWED_EDITORIAL_IMAGE_TYPES",
            "MAX_EDITORIAL_IMAGE_BYTES",
            "hashlib.sha256(image_bytes).hexdigest()",
            "editorial_image_assets",
            "ON CONFLICT (post_number, version) DO NOTHING",
            "editorial_image_version_exists",
            "reconcile_editorial_image_assets",
            '"truncated": bool(page_token)',
            '"truncated_scan_possible": bool(drive_result.get("truncated", False))',
            "hashlib.sha256(recovered_bytes).hexdigest() != digest",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.source)

    def test_google_workspace_scopes_are_explicit(self):
        for scope in (
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
        ):
            with self.subTest(scope=scope):
                self.assertIn(scope, self.source)
        self.assertIn('"scope": GOOGLE_WORKSPACE_SCOPES', self.source)

    def test_three_google_accounts_are_allowlisted(self):
        for account in ("Drive5", "Drive1", "SGMurici/pessoal"):
            with self.subTest(account=account):
                self.assertIn(account, self.source)
        self.assertIn("def normalize_google_account_name", self.source)

    def test_gmail_reader_is_read_only_and_account_scoped(self):
        self.assertIn('@app.get("/gmail/messages")', self.source)
        self.assertIn('normalize_google_account_name(request.args.get("account", "Drive5"))', self.source)
        self.assertIn('"mode": "read_only_metadata"', self.source)

    def test_source_parses_as_python(self):
        self.assertIsInstance(self.tree, ast.Module)


if __name__ == "__main__":
    unittest.main()
