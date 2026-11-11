"""PostgreSQL integration tests for the feature-gated email OTP auth routes."""
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from cryptography.fernet import Fernet
from psycopg import sql

import app as application
import identity_lookup


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "migrations" / "0002_identity_core.sql",
    ROOT / "migrations" / "0005_otp_request_limits.sql",
    ROOT / "migrations" / "0006_session_authentication_freshness.sql",
    ROOT / "migrations" / "0009_identity_otp_hardening.sql",
)


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL não configurado")
class EmailOtpAuthRoutePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "auth_routes_" + uuid.uuid4().hex
        cls.admin = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema)))
        try:
            for migration in MIGRATIONS:
                source = migration.read_text(encoding="utf-8")
                for statement in source.split(";"):
                    if statement.strip():
                        conn.execute(statement, prepare=False)
        except Exception:
            cls.admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(cls.schema)))
            conn.close()
            cls.admin.close()
            raise
        conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(cls.schema)))
        cls.admin.close()

    def _connection(self):
        conn = psycopg.connect(DATABASE_URL)
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        return conn

    def setUp(self):
        with self._connection() as conn:
            conn.execute("TRUNCATE app_users, tenants, otp_request_limits CASCADE")

    def _env(self):
        return {
            "IDENTITY_LOOKUP_PEPPER": "identity-lookup-pepper-for-tests-32-bytes",
            "OTP_PEPPER": "otp-pepper-for-auth-route-tests-32-bytes",
            "OTP_RATE_LIMIT_PEPPER": "rate-limit-pepper-for-auth-tests-32-bytes",
            "IDENTITY_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
            "TRUSTED_PROXY_HOPS": "1",
            "TRUSTED_PROXY_CIDRS": "10.0.0.0/8",
            "TERMS_POLICY_VERSION": "terms-test-v1",
            "PRIVACY_NOTICE_VERSION": "privacy-test-v1",
            "SMTP_HOST": "email-smtp.sa-east-1.amazonaws.com",
            "SMTP_PORT": "587",
            "SMTP_FROM": "no-reply@example.com",
            "SMTP_USERNAME": "smtp-test-user",
            "SMTP_PASSWORD": "smtp-test-password",
            "SMTP_USE_TLS": "true",
            "SMTP_USE_SSL": "false",
        }

    def _post(self, client, path, payload, ip="198.51.100.10"):
        return client.post(
            path,
            json=payload,
            headers={"X-Forwarded-For": ip},
            environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
        )

    def test_signup_verifies_email_activates_user_creates_tenant_and_login_works(self):
        sent = []

        def send_email(recipient, code, purpose, expires_minutes=10):
            sent.append((recipient, code, purpose))
            return {"message_id": f"<test-{len(sent)}@mail.example>"}

        client = application.app.test_client()
        with (
            patch.dict(os.environ, self._env(), clear=False),
            patch.object(application, "AUTH_ROUTES_ENABLED", True),
            patch.object(application, "get_db_connection", side_effect=self._connection),
            patch.object(application.email_delivery, "send_otp_email", side_effect=send_email),
        ):
            requested = self._post(
                client, "/api/v1/auth/signup/request", {
                    "email": "New.User@example.com",
                    "terms_accepted": True,
                    "privacy_notice_acknowledged": True,
                }
            )
            self.assertEqual(requested.status_code, 202)
            self.assertEqual(requested.get_json()["status"], "accepted")
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0][0], "new.user@example.com")
            self.assertEqual(sent[0][2], "signup")
            signup_verified = self._post(
                client,
                "/api/v1/auth/signup/verify",
                {"challenge_id": requested.get_json()["challenge_id"], "code": sent[0][1]},
            )
            self.assertEqual(signup_verified.status_code, 200)
            signup_token = signup_verified.get_json()["access_token"]
            self.assertTrue(signup_token)

            user_id = signup_verified.get_json()["usuario"]["id"]
            with self._connection() as conn:
                user = conn.execute(
                    "SELECT status FROM app_users WHERE id = %s", (user_id,)
                ).fetchone()
                identity = conn.execute(
                    """SELECT verified_at, identity_value_ciphertext
                       FROM user_identities WHERE user_id = %s""",
                    (user_id,),
                ).fetchone()
                membership = conn.execute(
                    """SELECT t.tenant_type, m.role
                       FROM tenant_memberships AS m
                       JOIN tenants AS t ON t.id = m.tenant_id
                       WHERE m.user_id = %s""",
                    (user_id,),
                ).fetchone()
            self.assertEqual(user[0], "active")
            self.assertIsNotNone(identity[0])
            self.assertNotIn(b"new.user@example.com", bytes(identity[1]))
            self.assertEqual(membership, ("personal", "owner"))
            with self._connection() as conn:
                terms = conn.execute(
                    """SELECT policy_version, decision FROM consent_events
                       WHERE user_id = %s AND purpose = 'terms_of_service'""",
                    (user_id,),
                ).fetchone()
                privacy = conn.execute(
                    """SELECT metadata->>'policy_version' FROM audit_events
                       WHERE actor_user_id = %s AND action = 'privacy_notice.acknowledged'""",
                    (user_id,),
                ).fetchone()
            self.assertEqual(terms, ("terms-test-v1", "granted"))
            self.assertEqual(privacy[0], "privacy-test-v1")

            login_requested = self._post(
                client, "/api/v1/auth/login/request", {"email": "new.user@example.com"},
                ip="198.51.100.21",
            )
            self.assertEqual(login_requested.status_code, 202)
            self.assertEqual(len(sent), 2)
            self.assertEqual(sent[1][2], "login")
            login_verified = self._post(
                client,
                "/api/v1/auth/login/verify",
                {
                    "challenge_id": login_requested.get_json()["challenge_id"],
                    "code": sent[1][1],
                },
                ip="198.51.100.21",
            )
            self.assertEqual(login_verified.status_code, 200)
            self.assertNotEqual(login_verified.get_json()["access_token"], signup_token)

    def test_signup_and_login_requests_do_not_disclose_unknown_or_existing_accounts(self):
        sent = []
        env = self._env()
        registered_email = "registered@example.com"
        user_id = uuid.uuid4()
        lookup_hash = identity_lookup.hash_identity_lookup(
            "email", registered_email, env["IDENTITY_LOOKUP_PEPPER"].encode("utf-8")
        )
        ciphertext = Fernet(env["IDENTITY_ENCRYPTION_KEY"].encode("ascii")).encrypt(
            registered_email.encode("utf-8")
        )
        with self._connection() as conn:
            conn.execute("INSERT INTO app_users (id, status) VALUES (%s, 'active')", (user_id,))
            conn.execute(
                """INSERT INTO user_identities
                   (id, user_id, identity_type, identity_lookup_hash,
                    identity_value_ciphertext, verified_at, is_primary)
                   VALUES (%s, %s, 'email', %s, %s, NOW(), TRUE)""",
                (uuid.uuid4(), user_id, lookup_hash, ciphertext),
            )

        def send_email(recipient, code, purpose, expires_minutes=10):
            sent.append((recipient, code, purpose))
            return {"message_id": f"<test-{len(sent)}@mail.example>"}

        client = application.app.test_client()
        with (
            patch.dict(os.environ, env, clear=False),
            patch.object(application, "AUTH_ROUTES_ENABLED", True),
            patch.object(application, "get_db_connection", side_effect=self._connection),
            patch.object(application.email_delivery, "send_otp_email", side_effect=send_email),
        ):
            unknown = self._post(
                client, "/api/v1/auth/login/request", {"email": "unknown@example.com"}
            )
            registered = self._post(
                client, "/api/v1/auth/login/request", {"email": registered_email},
                ip="198.51.100.11",
            )
            self.assertEqual(unknown.status_code, registered.status_code)
            self.assertEqual(set(unknown.get_json()), set(registered.get_json()))
            self.assertEqual(unknown.get_json()["status"], "accepted")
            self.assertEqual(registered.get_json()["status"], "accepted")
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0][0], registered_email)

    def test_signup_requires_explicit_terms_and_privacy_notice_acknowledgement(self):
        client = application.app.test_client()
        with (
            patch.dict(os.environ, self._env(), clear=False),
            patch.object(application, "AUTH_ROUTES_ENABLED", True),
            patch.object(application, "get_db_connection", side_effect=self._connection),
        ):
            response = client.post(
                "/api/v1/auth/signup/request",
                json={"email": "person@example.com"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["status"], "erro")

    def test_routes_fail_closed_when_feature_flag_or_proxy_chain_is_missing(self):
        client = application.app.test_client()
        with patch.object(application, "AUTH_ROUTES_ENABLED", False):
            disabled = client.post(
                "/api/v1/auth/signup/request", json={"email": "person@example.com"}
            )
        self.assertEqual(disabled.status_code, 503)

        with (
            patch.dict(os.environ, self._env(), clear=False),
            patch.object(application, "AUTH_ROUTES_ENABLED", True),
        ):
            missing_proxy = client.post(
                "/api/v1/auth/signup/request",
                json={"email": "person@example.com"},
                environ_overrides={"REMOTE_ADDR": "10.0.0.1"},
            )
        self.assertEqual(missing_proxy.status_code, 503)

    def test_trusted_proxy_ip_uses_rightmost_configured_hop_count(self):
        with patch.dict(os.environ, {"TRUSTED_PROXY_HOPS": "2", "TRUSTED_PROXY_CIDRS": "10.0.0.0/8"}, clear=False):
            with application.app.test_request_context(
                "/",
                headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
                environ_overrides={"REMOTE_ADDR": "10.0.0.2"},
            ):
                self.assertEqual(application.trusted_auth_client_ip(), "203.0.113.9")


if __name__ == "__main__":
    unittest.main()
