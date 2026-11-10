import unittest
from datetime import datetime, timezone

import google_oauth_exchange as exchange


class GoogleOAuthExchangeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.token_payload = {
            "access_token": "access-token-secret",
            "refresh_token": "refresh-token-secret",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "openid email " + exchange._SCOPE,
        }
        self.userinfo = {
            "sub": "google-subject-123",
            "email": "customer@example.test",
            "email_verified": True,
        }
        def post(url, data):
            self.calls.append(("POST", url, data))
            return 200, self.token_payload
        def get(url, headers):
            self.calls.append(("GET", url, headers))
            return 200, self.userinfo
        self.post = post
        self.get = get

    def test_exchanges_code_with_pkce_and_validates_google_subject(self):
        now = datetime(2026, 11, 10, tzinfo=timezone.utc)
        result = exchange.exchange_authorization_code(
            code="one-time-code",
            code_verifier="v" * 50,
            redirect_uri="https://api.example.test/callback",
            client_id="client-id",
            client_secret="client-secret",
            post_form=self.post,
            get_json=self.get,
            now=now,
        )
        self.assertEqual(result["google_subject"], "google-subject-123")
        self.assertEqual(result["account_label"], "customer@example.test")
        self.assertEqual(result["access_token"], "access-token-secret")
        self.assertEqual(result["refresh_token"], "refresh-token-secret")
        self.assertEqual(result["token_expires_at"], datetime(2026, 11, 10, 1, tzinfo=timezone.utc))
        self.assertEqual(self.calls[0][2]["code_verifier"], "v" * 50)
        self.assertEqual(self.calls[1][2]["Authorization"], "Bearer access-token-secret")

    def test_rejects_invalid_pkce_and_http_redirect(self):
        for verifier, redirect in (("short", "https://valid"), ("v" * 50, "http://bad")):
            with self.subTest(verifier=verifier, redirect=redirect), self.assertRaises(ValueError):
                exchange.exchange_authorization_code(
                    code="code", code_verifier=verifier, redirect_uri=redirect,
                    client_id="id", client_secret="secret",
                    post_form=self.post, get_json=self.get,
                )
        self.assertEqual(self.calls, [])

    def test_requires_refresh_token_for_durable_offline_backup(self):
        self.token_payload.pop("refresh_token")
        with self.assertRaises(exchange.GoogleOAuthExchangeError):
            exchange.exchange_authorization_code(
                code="code", code_verifier="v" * 50,
                redirect_uri="https://api.example.test/callback",
                client_id="id", client_secret="secret",
                post_form=self.post, get_json=self.get,
            )

    def test_rejects_broad_drive_scope(self):
        self.token_payload["scope"] += " https://www.googleapis.com/auth/drive"
        with self.assertRaises(exchange.GoogleOAuthExchangeError):
            exchange.exchange_authorization_code(
                code="code", code_verifier="v" * 50,
                redirect_uri="https://api.example.test/callback",
                client_id="id", client_secret="secret",
                post_form=self.post, get_json=self.get,
            )

    def test_rejects_missing_drive_file_scope(self):
        self.token_payload["scope"] = "openid email"
        with self.assertRaises(exchange.GoogleOAuthExchangeError):
            exchange.exchange_authorization_code(
                code="code", code_verifier="v" * 50,
                redirect_uri="https://api.example.test/callback",
                client_id="id", client_secret="secret",
                post_form=self.post, get_json=self.get,
            )

    def test_rejects_missing_google_subject(self):
        self.userinfo.pop("sub")
        with self.assertRaises(exchange.GoogleOAuthExchangeError):
            exchange.exchange_authorization_code(
                code="code", code_verifier="v" * 50,
                redirect_uri="https://api.example.test/callback",
                client_id="id", client_secret="secret",
                post_form=self.post, get_json=self.get,
            )

    def test_revocation_returns_success_only_for_google_200(self):
        self.assertTrue(exchange.revoke_google_token(
            token="refresh-token", post_form=lambda url, data: (200, {})
        ))
        self.assertFalse(exchange.revoke_google_token(
            token="refresh-token", post_form=lambda url, data: (400, {})
        ))


if __name__ == "__main__":
    unittest.main()
