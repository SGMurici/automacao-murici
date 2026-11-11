"""Real PostgreSQL integration tests for OTP hardening migration 0009."""
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

import identity_otp_core as otp


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "migrations" / "0002_identity_core.sql",
    ROOT / "migrations" / "0009_identity_otp_hardening.sql",
)


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL não configurado")
class IdentityOtpHardeningPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "otp_hardening_" + uuid.uuid4().hex
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
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))
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
        self.conn = self._connection()
        self.user_id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()
        self.conn.execute("INSERT INTO app_users (id, status) VALUES (%s, 'active')", (self.user_id,))
        self.conn.execute("INSERT INTO tenants (id, tenant_type) VALUES (%s, 'personal')", (self.tenant_id,))
        self.conn.execute(
            """INSERT INTO tenant_memberships (tenant_id, user_id, role, status)
               VALUES (%s, %s, 'owner', 'active')""",
            (self.tenant_id, self.user_id),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def _create_challenge(self, delivery_status="pending"):
        challenge_id = uuid.uuid4()
        self.conn.execute(
            """INSERT INTO otp_challenges
               (id, user_id, identity_type, identity_lookup_hash, purpose,
                code_hash, expires_at, max_attempts, delivery_status)
               VALUES (%s, %s, 'email', %s, 'signup', %s,
                       NOW() + INTERVAL '10 minutes', 5, %s)""",
            (challenge_id, self.user_id, b"i" * 32, b"d" * 32, delivery_status),
        )
        self.conn.commit()
        return challenge_id

    def test_sent_delivery_transition_persists_timestamps_and_is_one_way(self):
        challenge_id = self._create_challenge()
        self.assertTrue(otp.mark_challenge_delivery(
            self.conn, challenge_id, "sent", "provider-message-123"
        ))
        self.conn.commit()
        row = self.conn.execute(
            """SELECT delivery_status, delivery_attempted_at, sent_at,
                      resend_after, provider_reference, consumed_at
               FROM otp_challenges WHERE id = %s""",
            (challenge_id,),
        ).fetchone()
        self.assertEqual(row[0], "sent")
        self.assertIsNotNone(row[1])
        self.assertIsNotNone(row[2])
        self.assertGreater(row[3], row[2])
        self.assertEqual(row[4], "provider-message-123")
        self.assertIsNone(row[5])
        self.assertFalse(otp.mark_challenge_delivery(self.conn, challenge_id, "failed"))
        self.conn.rollback()

    def test_failed_delivery_consumes_challenge_and_cannot_be_reactivated(self):
        challenge_id = self._create_challenge()
        self.assertTrue(otp.mark_challenge_delivery(self.conn, challenge_id, "failed"))
        self.conn.commit()
        row = self.conn.execute(
            """SELECT delivery_status, delivery_attempted_at, sent_at,
                      provider_reference, consumed_at
               FROM otp_challenges WHERE id = %s""",
            (challenge_id,),
        ).fetchone()
        self.assertEqual(row[0], "failed")
        self.assertIsNotNone(row[1])
        self.assertIsNone(row[2])
        self.assertIsNone(row[3])
        self.assertIsNotNone(row[4])
        self.assertFalse(otp.mark_challenge_delivery(self.conn, challenge_id, "sent"))
        self.conn.rollback()

    def test_delivery_transition_rejects_expired_challenge(self):
        challenge_id = self._create_challenge()
        self.conn.execute(
            "UPDATE otp_challenges SET created_at = NOW() - INTERVAL '2 minutes',
                    expires_at = NOW() - INTERVAL '1 second' WHERE id = %s",
            (challenge_id,),
        )
        self.conn.commit()
        self.assertFalse(otp.mark_challenge_delivery(self.conn, challenge_id, "sent"))
        self.conn.rollback()

    def test_rate_limit_enforces_shared_quota_under_concurrency(self):
        key_hash = uuid.uuid4().bytes + uuid.uuid4().bytes
        now = datetime.now(timezone.utc)

        def reserve(_):
            conn = self._connection()
            try:
                allowed = otp.record_rate_limit_hit(
                    conn, "otp_identity", key_hash, now, 3600, 5
                )
                conn.commit()
                return allowed
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(reserve, range(24)))

        self.assertEqual(sum(results), 5)
        count = self.conn.execute(
            """SELECT hit_count FROM auth_rate_limit_buckets
               WHERE scope = 'otp_identity' AND key_hash = %s""",
            (key_hash,),
        ).fetchone()[0]
        self.assertEqual(count, 5)

    def test_rate_limit_scopes_are_independent(self):
        key_hash = uuid.uuid4().bytes + uuid.uuid4().bytes
        now = datetime.now(timezone.utc)
        self.assertTrue(otp.record_rate_limit_hit(
            self.conn, "otp_identity", key_hash, now, 3600, 1
        ))
        self.assertTrue(otp.record_rate_limit_hit(
            self.conn, "otp_ip", key_hash, now, 3600, 1
        ))
        self.conn.commit()
        count = self.conn.execute(
            "SELECT COUNT(*) FROM auth_rate_limit_buckets WHERE key_hash = %s",
            (key_hash,),
        ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_rate_limit_reservation_rolls_back_with_caller_transaction(self):
        key_hash = uuid.uuid4().bytes + uuid.uuid4().bytes
        now = datetime.now(timezone.utc)
        self.assertTrue(otp.record_rate_limit_hit(
            self.conn, "otp_identity", key_hash, now, 3600, 3
        ))
        self.conn.rollback()
        count = self.conn.execute(
            "SELECT COUNT(*) FROM auth_rate_limit_buckets WHERE key_hash = %s",
            (key_hash,),
        ).fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
