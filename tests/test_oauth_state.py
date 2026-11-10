import unittest
from unittest.mock import patch

import app as application


class OAuthStateConsumptionTests(unittest.TestCase):
    def setUp(self):
        self.secret_key_patch = patch.object(
            application.app, "secret_key", "unit-test-only-secret"
        )
        self.secret_key_patch.start()
        self.addCleanup(self.secret_key_patch.stop)

    def test_valid_state_is_removed_from_current_session(self):
        with application.app.test_request_context("/"):
            application.session["oauth_state"] = "expected-state"

            self.assertTrue(
                application.consume_oauth_state(
                    "oauth_state", "expected-state"
                )
            )
            self.assertFalse(
                application.consume_oauth_state(
                    "oauth_state", "expected-state"
                )
            )
            self.assertNotIn("oauth_state", application.session)

    def test_mismatched_state_is_rejected_and_removed(self):
        with application.app.test_request_context("/"):
            application.session["oauth_state"] = "expected-state"

            self.assertFalse(
                application.consume_oauth_state("oauth_state", "wrong-state")
            )
            self.assertNotIn("oauth_state", application.session)

    def test_missing_or_non_ascii_state_is_rejected(self):
        with application.app.test_request_context("/"):
            application.session["oauth_state"] = "expected-state"
            self.assertFalse(
                application.consume_oauth_state("oauth_state", None)
            )
            self.assertNotIn("oauth_state", application.session)

            application.session["oauth_state"] = "expected-state"
            self.assertFalse(
                application.consume_oauth_state(
                    "oauth_state", "estado-com-acentuação"
                )
            )
            self.assertNotIn("oauth_state", application.session)

    def test_missing_expected_state_is_rejected(self):
        with application.app.test_request_context("/"):
            self.assertFalse(
                application.consume_oauth_state("oauth_state", "expected-state")
            )


if __name__ == "__main__":
    unittest.main()
