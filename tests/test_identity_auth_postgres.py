"""End-to-end identity OTP route tests on an isolated PostgreSQL schema."""
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql
from cryptography.fernet import Fernet

import app as application


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "migrations" / "0002_identity_core.sql",
    ROOT / "migrations" / "0005_otp_request_limits.sql",
    ROOT / "migrations" / "0006_session_authentication_freshness.sql",
    ROOT / "migrations" / "0009_identity_otp_hardening.sql",
)


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL não configurado")
class IdentityAuthRouteIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "identity_auth_" + uuid.uuid4().hex
        cls.admin = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.admin.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema))
        )
        connection = psycopg.connect(DATABASE_URL, autocommit=True)
        connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema))
        )
        try:
            for migration in MIGRATIONS:
                source = migration.read_text(encoding="utf-8")
                for statement in source.split(";"):
                    if statement.strip():
                        connection.execute(statement, prepare=False)
        except Exception:
            cls.admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema))
            )
            raise
        finally:
            connection.close()

    @classmethod
    def tearDownClass(cls):
        cls.admin.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(cls.schema))
        )
        cls.admin.close()

    def setUp(self):
        self.client = application.app.test_client()
        self.client_ip_headers = {
            "X-Forwarded-For": "198.51.100.20, 10.0.0.1"
        }
        self.env = {
            "IDENTITY_LOOKUP_PEPPER": "identity-lookup-test-pepper-32-bytes-min",
            "OTP_PEPPER": "otp-test-pepper-32-bytes-minimum-value",
            "OTP_RATE_LIMIT_PEPPER": "otp-rate-limit-test-pepper-32-bytes",
            "OTP_TRUSTED_PROXY_HOPS": "2",
            "SMTP_HOST": "email-smtp.sa-east-1.amazonaws.com",
            "SMTP_PORT": "587",
            "SMTP_FROM": "nao-responda@example.test",
            "SMTP_USERNAME": "test-smtp-user",
            "SMTP_PASSWORD": "test-smtp-password",
            "SMTP_USE_TLS": "true",
            "SMTP_USE_SSL": "false",
            "TERMS_POLICY_VERSION": "terms-test-v1",
            "PRIVACY_NOTICE_VERSION": "privacy-test-v1",
        }
        self.env_patch = patch.dict(os.environ, self.env, clear=False)
        self.env_patch.start()
        self.key_patch = patch.object(
            application, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii")
        )
        self.key_patch.start()
        self.db_patch = patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        )
        self.db_patch.start()
        self.mail_patch = patch(
            "app.email_delivery.send_otp_email",
            return_value={"message_id": "<otp-test@example.test>"},
        )
        self.send_mail = self.mail_patch.start()
        self.testing_patch = patch.object(application.app, "testing", True)
        self.testing_patch.start()

    def tearDown(self):
        self.testing_patch.stop()
        self.mail_patch.stop()
        self.db_patch.stop()
        self.key_patch.stop()
        self.env_patch.stop()

    def _application_db_connection(self):
        connection = psycopg.connect(DATABASE_URL)
        connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema))
        )
        return connection

    def _request_signup(self, email):
        return self.client.post(
            "/api/v1/auth/otp/request",
            json={"email": email, "purpose": "signup"},
            headers=self.client_ip_headers,
        )

    def _verify_signup(self, email, code):
        return self.client.post(
            "/api/v1/auth/otp/verify",
            json={
                "email": email,
                "code": code,
                "purpose": "signup",
                "accept_terms": True,
                "acknowledge_privacy": True,
                "display_name": "Conta de teste",
                "device_label": "Browser de teste",
            },
            headers=self.client_ip_headers,
        )

    def test_signup_verifies_email_activates_owner_tenant_and_issues_session(self):
        email = f"user-{uuid.uuid4().hex}@example.test"
        requested = self._request_signup(email)
        self.assertEqual(requested.status_code, 202)
        self.assertEqual(requested.json["status"], "accepted")
        self.assertNotIn("challenge_id", requested.json)
        self.send_mail.assert_called_once()
        self.assertEqual(self.send_mail.call_args.args[0], email.lower())
        code = self.send_mail.call_args.args[1]

        verified = self._verify_signup(email, code)
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json["status"], "ok")
        self.assertEqual(verified.json["token_type"], "Bearer")
        self.assertGreaterEqual(len(verified.json["access_token"]), 32)

        with self._application_db_connection() as conn:
            user = conn.execute(
                """SELECT u.status, i.verified_at
                   FROM app_users AS u
                   JOIN user_identities AS i ON i.user_id = u.id
                   WHERE i.identity_type = 'email'
                     AND i.identity_lookup_hash = (
                         SELECT identity_lookup_hash FROM user_identities
                         WHERE identity_value_ciphertext IS NOT NULL
                         ORDER BY created_at DESC LIMIT 1
                     )
                   ORDER BY i.created_at DESC LIMIT 1"""
            ).fetchone()
            self.assertEqual(user[0], "active")
            self.assertIsNotNone(user[1])
            membership = conn.execute(
                """SELECT t.tenant_type, m.role, m.status
                   FROM tenant_memberships AS m
                   JOIN tenants AS t ON t.id = m.tenant_id
                   WHERE m.user_id = (
                       SELECT user_id FROM user_identities
                       WHERE identity_value_ciphertext IS NOT NULL
                       ORDER BY created_at DESC LIMIT 1
                   )"""
            ).fetchone()
            self.assertEqual(membership, ("personal", "owner", "active"))
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM consent_events").fetchone()[0], 2
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0], 1
            )

    def test_wrong_code_increments_attempt_and_correct_code_can_still_verify(self):
        email = f"wrong-{uuid.uuid4().hex}@example.test"
        self.assertEqual(self._request_signup(email).status_code, 202)
        code = self.send_mail.call_args.args[1]
        wrong_code = "00000000" if code != "00000000" else "00000001"

        wrong = self._verify_signup(email, wrong_code)
        self.assertEqual(wrong.status_code, 400)
        verified = self._verify_signup(email, code)
        self.assertEqual(verified.status_code, 200)

    def test_signup_request_is_rate_limited_without_changing_generic_response(self):
        email = f"limited-{uuid.uuid4().hex}@example.test"
        first = self._request_signup(email)
        second = self._request_signup(email)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json, second.json)
        self.send_mail.assert_called_once()

    def test_unknown_login_returns_generic_response_and_sends_no_email(self):
        email = f"unknown-{uuid.uuid4().hex}@example.test"
        response = self.client.post(
            "/api/v1/auth/otp/request",
            json={"email": email, "purpose": "login"},
            headers=self.client_ip_headers,
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json["status"], "accepted")
        self.send_mail.assert_not_called()

    def test_signup_verification_requires_terms_before_consuming_code(self):
        email = f"terms-{uuid.uuid4().hex}@example.test"
        self.assertEqual(self._request_signup(email).status_code, 202)
        code = self.send_mail.call_args.args[1]
        response = self.client.post(
            "/api/v1/auth/otp/verify",
            json={"email": email, "code": code, "purpose": "signup"},
            headers=self.client_ip_headers,
        )
        self.assertEqual(response.status_code, 400)
        valid = self._verify_signup(email, code)
        self.assertEqual(valid.status_code, 200)

    def test_missing_trusted_proxy_configuration_fails_closed(self):
        with patch.dict(os.environ, {"OTP_TRUSTED_PROXY_HOPS": "0"}):
            email = f"blocked-{uuid.uuid4().hex}@example.test"
            response = self._request_signup(email)
        self.assertEqual(response.status_code, 503)
        self.send_mail.assert_not_called()


if __name__ == "__main__":
    unittest.main()
