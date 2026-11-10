"""PostgreSQL integration tests for the identity migrations.

The suite uses an isolated schema and never touches the configured public schema.
Set TEST_DATABASE_URL to enable it; local runs without PostgreSQL skip cleanly.
"""
import os
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg import sql


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "migrations" / "0001_oauth_states.sql",
    ROOT / "migrations" / "0002_identity_core.sql",
)


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL não configurado")
class IdentityMigrationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "identity_test_" + uuid.uuid4().hex
        cls.admin_conn = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.admin_conn.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema))
        )
        cls.conn = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema))
        )
        try:
            for migration in MIGRATIONS:
                source = migration.read_text(encoding="utf-8")
                for statement in source.split(";"):
                    if statement.strip():
                        cls.conn.execute(statement, prepare=False)
        except Exception:
            cls.conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema))
            )
            cls.conn.close()
            cls.admin_conn.close()
            raise
        cls.conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.admin_conn.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(cls.schema))
        )
        cls.admin_conn.close()

    def setUp(self):
        self.conn = psycopg.connect(DATABASE_URL)
        self.conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema))
        )
        self.user_id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO app_users (id, status) VALUES (%s, 'active')",
            (self.user_id,),
        )
        self.conn.execute(
            "INSERT INTO tenants (id, tenant_type) VALUES (%s, 'personal')",
            (self.tenant_id,),
        )
        self.conn.execute(
            """INSERT INTO tenant_memberships
               (tenant_id, user_id, role, status)
               VALUES (%s, %s, 'owner', 'active')""",
            (self.tenant_id, self.user_id),
        )

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def test_valid_identity_session_consent_and_audit_rows(self):
        identity_id = uuid.uuid4()
        self.conn.execute(
            """INSERT INTO user_identities
               (id, user_id, identity_type, identity_lookup_hash,
                identity_value_ciphertext, verified_at, is_primary)
               VALUES (%s, %s, 'email', %s, %s, NOW(), TRUE)""",
            (identity_id, self.user_id, b"lookup-hash", b"ciphertext"),
        )
        self.conn.execute(
            """INSERT INTO auth_sessions
               (token_hash, user_id, expires_at)
               VALUES (%s, %s, NOW() + INTERVAL '1 day')""",
            ("a" * 64, self.user_id),
        )
        self.conn.execute(
            """INSERT INTO consent_events
               (id, user_id, tenant_id, purpose, policy_version, decision, source)
               VALUES (%s, %s, %s, 'career_data', 'v1', 'granted', 'android')""",
            (uuid.uuid4(), self.user_id, self.tenant_id),
        )
        self.conn.execute(
            """INSERT INTO audit_events
               (id, actor_user_id, tenant_id, action, result)
               VALUES (%s, %s, %s, 'session.created', 'success')""",
            (uuid.uuid4(), self.user_id, self.tenant_id),
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM user_identities").fetchone()[0], 1
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0], 1
        )

    def test_duplicate_identity_lookup_is_rejected(self):
        values = (self.user_id, b"same-hash", b"ciphertext")
        statement = """INSERT INTO user_identities
            (id, user_id, identity_type, identity_lookup_hash, identity_value_ciphertext)
            VALUES (%s, %s, 'email', %s, %s)"""
        self.conn.execute(statement, (uuid.uuid4(), *values))
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.conn.execute(statement, (uuid.uuid4(), *values))

    def test_invalid_membership_role_is_rejected(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute(
                """INSERT INTO tenant_memberships (tenant_id, user_id, role)
                   VALUES (%s, %s, 'superuser')""",
                (uuid.uuid4(), self.user_id),
            )

    def test_external_connection_requires_real_tenant_membership(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.conn.execute(
                """INSERT INTO external_connections
                   (id, user_id, tenant_id, provider, external_account_id)
                   VALUES (%s, %s, %s, 'google', 'account-1')""",
                (uuid.uuid4(), self.user_id, uuid.uuid4()),
            )

    def test_invalid_otp_attempt_limits_and_audit_result_are_rejected(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute(
                """INSERT INTO otp_challenges
                   (id, identity_type, identity_lookup_hash, purpose, code_hash,
                    expires_at, max_attempts)
                   VALUES (%s, 'email', %s, 'login', %s,
                           NOW() + INTERVAL '5 minutes', 11)""",
                (uuid.uuid4(), b"lookup", b"code-hash"),
            )
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute(
                """INSERT INTO audit_events (id, action, result)
                   VALUES (%s, 'profile.read', 'maybe')""",
                (uuid.uuid4(),),
            )


if __name__ == "__main__":
    unittest.main()
