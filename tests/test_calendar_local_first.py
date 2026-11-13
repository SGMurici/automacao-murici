import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
WORKFLOW_SOURCE = (ROOT / ".github" / "workflows" / "gmail-tests.yml").read_text(encoding="utf-8")


class LocalFirstCalendarTests(unittest.TestCase):
    def test_backend_python_syntax_remains_valid(self):
        ast.parse(APP_SOURCE)

    def test_google_calendar_scope_and_route_are_removed(self):
        self.assertNotIn("calendar.readonly", APP_SOURCE)
        self.assertNotIn("GOOGLE_CALENDAR_READONLY_SCOPE", APP_SOURCE)
        self.assertNotIn('/google-calendar/check', APP_SOURCE)
        self.assertNotIn("google_calendar_readonly_check", APP_SOURCE)

    def test_google_oauth_rejects_calendar_purpose_but_keeps_gmail(self):
        tree = ast.parse(APP_SOURCE)
        google_login = next(
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "google_login"
        )
        source = ast.get_source_segment(APP_SOURCE, google_login) or ""
        self.assertIn('purpose', source)
        self.assertIn('"gmail"', source)
        self.assertIn("GOOGLE_GMAIL_READONLY_SCOPE", source)
        self.assertIn("calendário próprio", source)
        self.assertNotIn("calendar.readonly", source)

    def test_gmail_triage_workflow_remains_and_calendar_job_is_removed(self):
        self.assertIn("gmail-readonly-triage:", WORKFLOW_SOURCE)
        self.assertNotIn("calendar-readonly-check:", WORKFLOW_SOURCE)
        self.assertNotIn("/google-calendar/check", WORKFLOW_SOURCE)


if __name__ == "__main__":
    unittest.main()
