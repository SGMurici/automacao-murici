import unittest
from unittest.mock import patch

import otp_core


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class FakeConnection:
    def __init__(self, rows=None):
        self.cursor_instance = FakeCursor(rows)

    def cursor(self):
        return self.cursor_instance


class OtpCoreTests(unittest.TestCase):
    def setUp(self):
        self.pepper = b"p" * 32
        self.identity_hash = b"i" * 32

    def test_create_stores_only_hmac_digest_and_returns_code_once(self):
        conn = FakeConnection([("challenge-1",)])
        with patch.object(otp_core.secrets, "randbelow", return_value=42):
            result = otp_core.create_otp_challenge(
                conn, "email", self.identity_hash, "login", self.pepper
            )

        self.assertEqual(result, {"challenge_id": "challenge-1", "code": "000042"})
        query, params = conn.cursor_instance.executed[0]
        self.assertIn("INSERT INTO otp_challenges", query)
        self.assertEqual(params[1], "email")
        self.assertEqual(params[2], self.identity_hash)
        self.assertEqual(params[3], "login")
        self.assertEqual(params[4], otp_core._code_digest(
            params[0], "000042", self.pepper
        ))
        self.assertNotIn("000042", params)
        self.assertEqual(params[5:], (300, 5))

    def test_create_rejects_weak_pepper_and_invalid_policy(self):
        conn = FakeConnection([("challenge-1",)])
        with self.assertRaises(ValueError):
            otp_core.create_otp_challenge(
                conn, "email", self.identity_hash, "login", b"short"
            )
        with self.assertRaises(ValueError):
            otp_core.create_otp_challenge(
                conn, "email", self.identity_hash, "login", self.pepper,
                ttl_seconds=30,
            )
        self.assertEqual(conn.cursor_instance.executed, [])

    def test_delivery_status_can_only_be_marked_from_pending(self):
        conn = FakeConnection([("challenge-1",)])
        self.assertTrue(otp_core.mark_otp_delivery(conn, "challenge-1", "sent"))
        query, params = conn.cursor_instance.executed[0]
        self.assertIn("delivery_status = 'pending'", query)
        self.assertEqual(params, ("sent", "challenge-1"))

    def test_delivery_rejects_unknown_status(self):
        conn = FakeConnection()
        with self.assertRaises(ValueError):
            otp_core.mark_otp_delivery(conn, "challenge-1", "delivered")
        self.assertEqual(conn.cursor_instance.executed, [])

    def test_valid_code_is_consumed_atomically(self):
        challenge_id = "challenge-1"
        digest = otp_core._code_digest(challenge_id, "000042", self.pepper)
        conn = FakeConnection([
            (digest, True, None, 0, 5, "sent"),
            (challenge_id,),
        ])
        self.assertTrue(
            otp_core.verify_otp_challenge(conn, challenge_id, "000042", self.pepper)
        )
        self.assertEqual(len(conn.cursor_instance.executed), 2)
        self.assertIn("SET consumed_at = NOW()", conn.cursor_instance.executed[1][0])

    def test_invalid_code_increments_attempts_without_consuming(self):
        challenge_id = "challenge-1"
        digest = otp_core._code_digest(challenge_id, "000042", self.pepper)
        conn = FakeConnection([
            (digest, True, None, 0, 5, "sent"),
            (1,),
        ])
        self.assertFalse(
            otp_core.verify_otp_challenge(conn, challenge_id, "000043", self.pepper)
        )
        self.assertIn(
            "failed_attempts = failed_attempts + 1",
            conn.cursor_instance.executed[1][0],
        )

    def test_expired_unsent_consumed_or_exhausted_challenges_are_rejected(self):
        cases = [
            (False, None, 0, 5, "sent"),
            (True, None, 0, 5, "pending"),
            (True, "2026-11-10T00:00:00Z", 0, 5, "sent"),
            (True, None, 5, 5, "sent"),
        ]
        for row in cases:
            with self.subTest(row=row):
                conn = FakeConnection([(b"x" * 32, *row)])
                self.assertFalse(
                    otp_core.verify_otp_challenge(
                        conn, "challenge-1", "000042", self.pepper
                    )
                )
                self.assertEqual(len(conn.cursor_instance.executed), 1)

    def test_malformed_code_is_rejected_before_database_access(self):
        conn = FakeConnection()
        self.assertFalse(
            otp_core.verify_otp_challenge(
                conn, "challenge-1", "42", self.pepper
            )
        )
        self.assertEqual(conn.cursor_instance.executed, [])


    def test_rate_limit_reserves_first_slot_and_uses_pseudonymous_dimensions(self):
        conn = FakeConnection([(1,)])
        self.assertTrue(
            otp_core.reserve_otp_request_slot(
                conn, "identity", self.identity_hash, "login"
            )
        )
        query, params = conn.cursor_instance.executed[0]
        self.assertIn("ON CONFLICT (dimension_type, dimension_hash, purpose)", query)
        self.assertIn("last_requested_at", query)
        self.assertEqual(params[:3], ("identity", self.identity_hash, "login"))
        self.assertEqual(params[-1], 5)

    def test_rate_limit_rejects_when_cooldown_or_quota_blocks_upsert(self):
        conn = FakeConnection([])
        self.assertFalse(
            otp_core.reserve_otp_request_slot(
                conn, "ip", self.identity_hash, "signup"
            )
        )
        self.assertEqual(len(conn.cursor_instance.executed), 1)

    def test_rate_limit_rejects_invalid_dimensions_and_policy_before_database(self):
        conn = FakeConnection([(1,)])
        invalid = [
            ("email", self.identity_hash, "login"),
            ("identity", b"short", "login"),
            ("device", self.identity_hash, "unknown"),
        ]
        for dimension, digest, purpose in invalid:
            with self.subTest(dimension=dimension, purpose=purpose):
                with self.assertRaises(ValueError):
                    otp_core.reserve_otp_request_slot(
                        conn, dimension, digest, purpose
                    )
        with self.assertRaises(ValueError):
            otp_core.reserve_otp_request_slot(
                conn, "identity", self.identity_hash, "login", cooldown_seconds=0
            )
        self.assertEqual(conn.cursor_instance.executed, [])


if __name__ == "__main__":
    unittest.main()
