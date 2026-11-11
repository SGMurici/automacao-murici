"""Real PostgreSQL integration tests for OTP delivery metadata in migration 0009."""
import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
from psycopg import sql

import otp_core


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
class IdentityOtpHardeningPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "otp_hardening_" + uuid.uuid4().hex
        cls.admin = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema)))
        cls.legacy_sent_id = uuid.uuid4()
        cls.legacy_failed_id = uuid.uuid4()
        try:
            source = MIGRATIONS[0].read_text(encoding="utf-8")
            for statement in source.split(";"):
                if statement.strip():
                    conn.execute(statement, prepare=False)
            conn.execute(
                """INSERT INTO otp_challenges
                   (id, identity_type, identity_lookup_hash, purpose, code_hash,
                    created_at, expires_at, delivery_status)
                   VALUES (%s, 'email', %s, 'signup', %s,
                           NOW() - INTERVAL '3 minutes', NOW() + INTERVAL '10 minutes', 'sent')""",
                (cls.legacy_sent_id, b"l" * 32, b"s" * 32),
            )
            conn.execute(
                """INSERT INTO otp_challenges
                   (id, identity_type, identity_lookup_hash, purpose, code_hash,
                    created_at, expires_at, delivery_status)
                   VALUES (%s, 'email', %s, 'signup', %s,
                           NOW() - INTERVAL '3 minutes', NOW() + INTERVAL '10 minutes', 'failed')""",
                (cls.legacy_failed_id, b"f" * 32, b"x" * 32),
            )
            for migration in MIGRATIONS[1:]:
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

    def _create_challenge(self):
        challenge_id = uuid.uuid4()
        self.conn.execute(
            """INSERT INTO otp_challenges
               (id, user_id, identity_type, identity_lookup_hash, purpose,
                code_hash, expires_at, max_attempts, delivery_status)
               VALUES (%s, %s, 'email', %s, 'signup', %s,
                       NOW() + INTERVAL '10 minutes', 5, 'pending')""",
            (challenge_id, self.user_id, b"i" * 32, b"d" * 32),
        )
        self.conn.commit()
        return challenge_id

    def test_migration_backfills_legacy_sent_and_failed_challenges(self):
        sent = self.conn.execute(
            """SELECT delivery_attempted_at, sent_at, resend_after
               FROM otp_challenges WHERE id = %s""",
            (self.legacy_sent_id,),
        ).fetchone()
        self.assertIsNotNone(sent[0])
        self.assertIsNotNone(sent[1])
        self.assertGreater(sent[2], sent[1])

        failed = self.conn.execute(
            "SELECT consumed_at FROM otp_challenges WHERE id = %s",
            (self.legacy_failed_id,),
        ).fetchone()[0]
        self.assertIsNotNone(failed)

    def test_sent_delivery_transition_persists_timestamps_and_is_one_way(self):
        challenge_id = self._create_challenge()
        self.assertTrue(otp_core.mark_otp_delivery(
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
        self.assertFalse(otp_core.mark_otp_delivery(self.conn, challenge_id, "failed"))
        self.conn.rollback()

    def test_failed_delivery_consumes_challenge_and_cannot_be_reactivated(self):
        challenge_id = self._create_challenge()
        self.assertTrue(otp_core.mark_otp_delivery(self.conn, challenge_id, "failed"))
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
        self.assertFalse(otp_core.mark_otp_delivery(self.conn, challenge_id, "sent"))
        self.conn.rollback()

    def test_delivery_transition_rejects_expired_challenge(self):
        challenge_id = self._create_challenge()
        self.conn.execute(
            """UPDATE otp_challenges SET created_at = NOW() - INTERVAL '2 minutes',
                    expires_at = NOW() - INTERVAL '1 second' WHERE id = %s""",
            (challenge_id,),
        )
        self.conn.commit()
        self.assertFalse(otp_core.mark_otp_delivery(self.conn, challenge_id, "sent"))
        self.conn.rollback()


    OTP_PEPPER = b"otp-integration-pepper-32-bytes-minimum"

    def _create_challenge_with_code(self, purpose="signup"):
        result = otp_core.create_otp_challenge(
            self.conn,
            "email",
            b"i" * 32,
            purpose,
            self.OTP_PEPPER,
            user_id=self.user_id,
        )
        self.conn.commit()
        return result

    def test_challenge_verification_consumes_correct_purpose_once(self):
        challenge = self._create_challenge_with_code("signup")
        self.assertTrue(otp_core.mark_otp_delivery(
            self.conn, challenge["challenge_id"], "sent", "provider-verify-1"
        ))
        self.conn.commit()

        self.assertTrue(otp_core.verify_otp_challenge(
            self.conn, challenge["challenge_id"], "signup", challenge["code"], self.OTP_PEPPER
        ))
        self.conn.commit()
        self.assertFalse(otp_core.verify_otp_challenge(
            self.conn, challenge["challenge_id"], "signup", challenge["code"], self.OTP_PEPPER
        ))
        row = self.conn.execute(
            "SELECT consumed_at, failed_attempts FROM otp_challenges WHERE id = %s",
            (challenge["challenge_id"],),
        ).fetchone()
        self.assertIsNotNone(row[0])
        self.assertEqual(row[1], 0)

    def test_challenge_cannot_be_verified_for_another_purpose(self):
        challenge = self._create_challenge_with_code("signup")
        self.assertTrue(otp_core.mark_otp_delivery(
            self.conn, challenge["challenge_id"], "sent"
        ))
        self.conn.commit()

        self.assertFalse(otp_core.verify_otp_challenge(
            self.conn, challenge["challenge_id"], "login", challenge["code"], self.OTP_PEPPER
        ))
        self.conn.commit()
        attempts = self.conn.execute(
            "SELECT failed_attempts FROM otp_challenges WHERE id = %s",
            (challenge["challenge_id"],),
        ).fetchone()[0]
        self.assertEqual(attempts, 0)
        self.assertTrue(otp_core.verify_otp_challenge(
            self.conn, challenge["challenge_id"], "signup", challenge["code"], self.OTP_PEPPER
        ))
        self.conn.commit()

    def test_failed_attempts_reach_limit_without_consuming_valid_code(self):
        challenge = self._create_challenge_with_code("signup")
        self.assertTrue(otp_core.mark_otp_delivery(
            self.conn, challenge["challenge_id"], "sent"
        ))
        self.conn.commit()

        wrong_code = "99999999" if challenge["code"] != "99999999" else "99999998"
        for _ in range(5):
            self.assertFalse(otp_core.verify_otp_challenge(
                self.conn, challenge["challenge_id"], "signup", wrong_code, self.OTP_PEPPER
            ))
            self.conn.commit()
        self.assertFalse(otp_core.verify_otp_challenge(
            self.conn, challenge["challenge_id"], "signup", challenge["code"], self.OTP_PEPPER
        ))
        self.conn.commit()
        row = self.conn.execute(
            "SELECT failed_attempts, consumed_at FROM otp_challenges WHERE id = %s",
            (challenge["challenge_id"],),
        ).fetchone()
        self.assertEqual(row[0], 5)
        self.assertIsNone(row[1])

    def test_concurrent_verification_consumes_challenge_once(self):
        challenge = self._create_challenge_with_code("signup")
        self.assertTrue(otp_core.mark_otp_delivery(
            self.conn, challenge["challenge_id"], "sent"
        ))
        self.conn.commit()

        def verify_once(_):
            conn = self._connection()
            try:
                result = otp_core.verify_otp_challenge(
                    conn, challenge["challenge_id"], "signup", challenge["code"], self.OTP_PEPPER
                )
                conn.commit()
                return result
            finally:
                conn.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(verify_once, range(2)))
        self.assertEqual(sum(results), 1)

    def test_successful_verification_can_be_rolled_back_by_caller(self):
        challenge = self._create_challenge_with_code("signup")
        self.assertTrue(otp_core.mark_otp_delivery(
            self.conn, challenge["challenge_id"], "sent"
        ))
        self.conn.commit()

        self.assertTrue(otp_core.verify_otp_challenge(
            self.conn, challenge["challenge_id"], "signup", challenge["code"], self.OTP_PEPPER
        ))
        self.conn.rollback()
        self.assertTrue(otp_core.verify_otp_challenge(
            self.conn, challenge["challenge_id"], "signup", challenge["code"], self.OTP_PEPPER
        ))
        self.conn.commit()

if __name__ == "__main__":
    unittest.main()
