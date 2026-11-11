"""End-to-end identity OTP route tests on an isolated PostgreSQL schema."""
import os
import unittest
import time
import uuid
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

import psycopg
from psycopg import sql
from cryptography.fernet import Fernet

import app as application
import identity_lookup
import identity_auth_core


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "migrations" / "0002_identity_core.sql",
    ROOT / "migrations" / "0005_otp_request_limits.sql",
    ROOT / "migrations" / "0006_session_authentication_freshness.sql",
    ROOT / "migrations" / "0009_identity_otp_hardening.sql",
    ROOT / "migrations" / "0010_otp_signup_policy_versions.sql",
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
        client_octet = int(uuid.uuid4().hex[:2], 16) or 1
        self.client_ip_headers = {
            "X-Forwarded-For": f"198.51.100.{client_octet}, 10.0.0.1"
        }
        self.env = {
            "IDENTITY_LOOKUP_PEPPER": "identity-lookup-test-pepper-32-bytes-min",
            "OTP_PEPPER": "otp-test-pepper-32-bytes-minimum-value",
            "OTP_RATE_LIMIT_PEPPER": "otp-rate-limit-test-pepper-32-bytes",
            "IDENTITY_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
            "TRUSTED_PROXY_HOPS": "2",
            "TRUSTED_PROXY_CIDRS": "127.0.0.0/8,10.0.0.0/8",
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
        self.auth_enabled_patch = patch.object(application, "AUTH_ROUTES_ENABLED", True)
        self.auth_enabled_patch.start()
        self.db_patch = patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        )
        self.db_patch.start()
        self.mail_patch = patch(
            "app.email_delivery.send_otp_email",
            return_value={"message_id": "<otp-test@example.test>"},
        )
        self.send_mail = self.mail_patch.start()
        self.original_testing = application.app.config.get("TESTING", False)
        application.app.config["TESTING"] = True

    def tearDown(self):
        application.app.config["TESTING"] = self.original_testing
        self.mail_patch.stop()
        self.db_patch.stop()
        self.auth_enabled_patch.stop()
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
            "/api/v1/auth/signup/request",
            json={
                "email": email,
                "terms_accepted": True,
                "privacy_notice_acknowledged": True,
            },
            headers=self.client_ip_headers,
        )

    def _verify_signup(self, email, code):
        return self.client.post(
            "/api/v1/auth/signup/verify",
            json={
                "challenge_id": self.challenge_id,
                "code": code,
                "display_name": "Conta de teste",
                "device_label": "Browser de teste",
            },
            headers=self.client_ip_headers,
        )

    def test_signup_verifies_email_activates_owner_tenant_and_issues_session(self):
        email = f"user-{uuid.uuid4().hex}@example.test"
        requested = self._request_signup(email)
        self.challenge_id = requested.json["challenge_id"]
        self.assertEqual(requested.status_code, 202)
        self.assertEqual(requested.json["status"], "accepted")
        self.send_mail.assert_called_once()
        self.assertEqual(self.send_mail.call_args.args[0], email.lower())
        code = self.send_mail.call_args.args[1]

        verified = self._verify_signup(email, code)
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json["status"], "ok")
        self.assertEqual(verified.json["token_type"], "Bearer")
        self.assertGreaterEqual(len(verified.json["access_token"]), 32)
        me = self.client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {verified.json['access_token']}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json["tenants"][0]["papel"], "owner")

        identity_hash = identity_lookup.hash_identity_lookup(
            "email", email, os.environ["IDENTITY_LOOKUP_PEPPER"].encode("utf-8")
        )
        with self._application_db_connection() as conn:
            user = conn.execute(
                """SELECT u.id, u.status, i.verified_at
                   FROM app_users AS u
                   JOIN user_identities AS i ON i.user_id = u.id
                   WHERE i.identity_type = 'email'
                     AND i.identity_lookup_hash = %s""",
                (identity_hash,),
            ).fetchone()
            user_id = user[0]
            self.assertEqual(user[1], "active")
            self.assertIsNotNone(user[2])
            encrypted_identity = conn.execute(
                "SELECT identity_value_ciphertext FROM user_identities WHERE identity_lookup_hash = %s",
                (identity_hash,),
            ).fetchone()[0]
            self.assertNotIn(email.encode("utf-8"), bytes(encrypted_identity))
            membership = conn.execute(
                """SELECT t.tenant_type, m.role, m.status
                   FROM tenant_memberships AS m
                   JOIN tenants AS t ON t.id = m.tenant_id
                   WHERE m.user_id = %s""",
                (user_id,),
            ).fetchone()
            self.assertEqual(membership, ("personal", "owner", "active"))
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM consent_events WHERE user_id = %s", (user_id,)).fetchone()[0], 1
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM auth_sessions WHERE user_id = %s", (user_id,)).fetchone()[0], 1
            )

    def test_concurrent_signup_requests_create_one_pending_identity(self):
        email = f"race-{uuid.uuid4().hex}@example.test"
        identity_hash = identity_lookup.hash_identity_lookup(
            "email", email, os.environ["IDENTITY_LOOKUP_PEPPER"].encode("utf-8")
        )
        ciphertext = b"ciphertext-for-race-test"

        def create_or_get(_):
            with self._application_db_connection() as conn:
                identity = identity_auth_core.ensure_pending_email_identity(
                    conn, identity_hash, ciphertext
                )
                return str(identity["user_id"])

        with ThreadPoolExecutor(max_workers=4) as executor:
            user_ids = list(executor.map(create_or_get, range(4)))
        self.assertEqual(len(set(user_ids)), 1)
        with self._application_db_connection() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM user_identities WHERE identity_lookup_hash = %s",
                    (identity_hash,),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM app_users WHERE id = %s",
                    (user_ids[0],),
                ).fetchone()[0],
                1,
            )

    def test_wrong_code_increments_attempt_and_correct_code_can_still_verify(self):
        email = f"wrong-{uuid.uuid4().hex}@example.test"
        requested = self._request_signup(email)
        self.assertEqual(requested.status_code, 202)
        self.challenge_id = requested.json["challenge_id"]
        code = self.send_mail.call_args.args[1]
        wrong_code = "00000000" if code != "00000000" else "00000001"
        wrong = self._verify_signup(email, wrong_code)
        self.assertEqual(wrong.status_code, 400)
        time.sleep(1.05)
        verified = self._verify_signup(email, code)
        self.assertEqual(verified.status_code, 200)

    def test_signup_request_is_rate_limited_without_changing_generic_response(self):
        email = f"limited-{uuid.uuid4().hex}@example.test"
        first = self._request_signup(email)
        second = self._request_signup(email)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json["status"], second.json["status"])
        self.assertNotEqual(first.json["challenge_id"], second.json["challenge_id"])
        self.send_mail.assert_called_once()

    def test_unknown_login_returns_generic_response_and_sends_no_email(self):
        email = f"unknown-{uuid.uuid4().hex}@example.test"
        response = self.client.post(
            "/api/v1/auth/login/request",
            json={"email": email},
            headers=self.client_ip_headers,
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json["status"], "accepted")
        self.send_mail.assert_not_called()

    def test_verified_user_can_request_login_and_receive_second_session(self):
        email = f"login-{uuid.uuid4().hex}@example.test"
        signup = self._request_signup(email)
        self.challenge_id = signup.json["challenge_id"]
        signup_code = self.send_mail.call_args.args[1]
        activated = self._verify_signup(email, signup_code)
        self.assertEqual(activated.status_code, 200)

        self.send_mail.reset_mock()
        login_request = self.client.post(
            "/api/v1/auth/login/request",
            json={"email": email},
            headers=self.client_ip_headers,
        )
        self.assertEqual(login_request.status_code, 202)
        self.challenge_id = login_request.json["challenge_id"]
        self.send_mail.assert_called_once()
        login_code = self.send_mail.call_args.args[1]

        login = self.client.post(
            "/api/v1/auth/login/verify",
            json={"challenge_id": self.challenge_id, "code": login_code},
            headers=self.client_ip_headers,
        )
        self.assertEqual(login.status_code, 200)
        self.assertNotEqual(
            login.json["access_token"], activated.json["access_token"]
        )
        identity_hash = identity_lookup.hash_identity_lookup(
            "email", email, os.environ["IDENTITY_LOOKUP_PEPPER"].encode("utf-8")
        )
        with self._application_db_connection() as conn:
            user_id = conn.execute(
                "SELECT user_id FROM user_identities WHERE identity_lookup_hash = %s",
                (identity_hash,),
            ).fetchone()[0]
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM auth_sessions WHERE user_id = %s", (user_id,)).fetchone()[0], 2
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM audit_events WHERE action = 'identity.login' AND actor_user_id = %s",
                    (user_id,),
                ).fetchone()[0],
                1,
            )

    def test_failed_email_delivery_consumes_challenge(self):
        email = f"delivery-fail-{uuid.uuid4().hex}@example.test"
        self.send_mail.side_effect = application.email_delivery.EmailDeliveryError(
            "Não foi possível entregar o e-mail de verificação."
        )
        requested = self._request_signup(email)
        self.assertEqual(requested.status_code, 202)
        challenge_id = requested.json["challenge_id"]
        with self._application_db_connection() as conn:
            state = conn.execute(
                "SELECT delivery_status, consumed_at FROM otp_challenges WHERE id = %s",
                (challenge_id,),
            ).fetchone()
        self.assertEqual(state[0], "failed")
        self.assertIsNotNone(state[1])

    def test_signup_verification_requires_terms_before_consuming_code(self):
        email = f"terms-{uuid.uuid4().hex}@example.test"
        requested = self._request_signup(email)
        self.assertEqual(requested.status_code, 202)
        self.challenge_id = requested.json["challenge_id"]
        code = self.send_mail.call_args.args[1]
        response = self.client.post(
            "/api/v1/auth/signup/request",
            json={"email": email},
            headers=self.client_ip_headers,
        )
        self.assertEqual(response.status_code, 400)
        valid = self._verify_signup(email, code)
        self.assertEqual(valid.status_code, 200)

    def test_catch_all_trusted_proxy_cidrs_fail_closed(self):
        with patch.dict(os.environ, {"TRUSTED_PROXY_CIDRS": "0.0.0.0/0,::/0"}):
            self.assertFalse(application.auth_routes_ready())

    def test_identity_encryption_key_must_differ_from_token_key(self):
        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": os.environ["IDENTITY_ENCRYPTION_KEY"]}):
            self.assertFalse(application.auth_routes_ready())

    def test_missing_trusted_proxy_configuration_fails_closed(self):
        with patch.dict(os.environ, {"TRUSTED_PROXY_HOPS": "0"}):
            email = f"blocked-{uuid.uuid4().hex}@example.test"
            response = self._request_signup(email)
        self.assertEqual(response.status_code, 503)
        self.send_mail.assert_not_called()


if __name__ == "__main__":
    unittest.main()
