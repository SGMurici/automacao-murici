import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import identity_otp_core as otp


class FakeCursor:
    def __init__(self, one=None):
        self.one = one
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        return self.one


class FakeConnection:
    def __init__(self, one=None):
        self.fake_cursor = FakeCursor(one)

    def cursor(self):
        return self.fake_cursor


class OtpCoreTests(unittest.TestCase):
    SECRET = b"x" * 32
    CHALLENGE = "b8c28c9c-67e5-4c93-80bb-4e126a8c1a30"

    def test_normalize_email(self):
        self.assertEqual(otp.normalize_email("  User.Name@Example.COM "), "user.name@example.com")

    def test_reject_invalid_email(self):
        for value in ["", "x", "x@", "@example.com", "a b@example.com", "x@example", "x@@example.com"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                otp.normalize_email(value)

    def test_generate_otp_is_eight_digits(self):
        with patch.object(otp.secrets, "choice", side_effect=list("00123456")):
            self.assertEqual(otp.generate_otp(), "00123456")

    def test_digest_is_bound_to_challenge_and_purpose(self):
        digest = otp.otp_digest(self.SECRET, self.CHALLENGE, "signup", "00123456")
        self.assertEqual(len(digest), 32)
        self.assertTrue(otp.verify_otp(self.SECRET, self.CHALLENGE, "signup", "00123456", digest))
        self.assertFalse(otp.verify_otp(self.SECRET, self.CHALLENGE, "login", "00123456", digest))
        self.assertFalse(otp.verify_otp(self.SECRET, "a8c28c9c-67e5-4c93-80bb-4e126a8c1a30", "signup", "00123456", digest))

    def test_digest_rejects_short_secret_and_invalid_code(self):
        with self.assertRaises(ValueError):
            otp.otp_digest(b"short", self.CHALLENGE, "signup", "00123456")
        with self.assertRaises(ValueError):
            otp.otp_digest(self.SECRET, self.CHALLENGE, "signup", "123")
        with self.assertRaises(ValueError):
            otp.otp_digest(self.SECRET, self.CHALLENGE, "unknown", "00123456")

    def test_verify_returns_false_for_malformed_input(self):
        self.assertFalse(otp.verify_otp(self.SECRET, self.CHALLENGE, "signup", "bad", b"x" * 32))

    def test_privacy_hash_is_scoped_and_non_reversible(self):
        a = otp.privacy_key_hash(self.SECRET, "otp_identity", "User@example.com")
        b = otp.privacy_key_hash(self.SECRET, "otp_identity", "user@example.com")
        c = otp.privacy_key_hash(self.SECRET, "otp_ip", "user@example.com")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(len(a), 32)

    def test_expiry_is_bounded_and_timezone_aware(self):
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        self.assertEqual(otp.challenge_expiry(now), datetime(2026, 11, 11, 12, 10, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            otp.challenge_expiry(now, 30)
        with self.assertRaises(ValueError):
            otp.challenge_expiry(datetime(2026, 11, 11, 12))

    def test_rate_limit_window_aligns_to_fixed_interval(self):
        now = datetime(2026, 11, 11, 12, 3, 45, tzinfo=timezone.utc)
        start, end = otp.rate_limit_window(now, 900)
        self.assertEqual(start, datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc))
        self.assertEqual((end - start).total_seconds(), 900)

    def test_rate_limit_hit_is_atomic_upsert(self):
        conn = FakeConnection(one=(1,))
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        self.assertTrue(otp.record_rate_limit_hit(conn, "otp_ip", b"h" * 32, now, 900, 10))
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("ON CONFLICT", query)
        self.assertIn("WHERE auth_rate_limit_buckets.hit_count <", query)
        self.assertEqual(params[-1], 10)

    def test_rate_limit_rejects_at_limit(self):
        conn = FakeConnection(one=None)
        now = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        self.assertFalse(otp.record_rate_limit_hit(conn, "otp_ip", b"h" * 32, now, 900, 10))

    def test_delivery_transition_is_conditional_and_failed_code_consumed(self):
        conn = FakeConnection(one=("challenge",))
        self.assertTrue(otp.mark_challenge_delivery(conn, self.CHALLENGE, "failed"))
        query, params = conn.fake_cursor.calls[0]
        self.assertIn("delivery_status = 'pending'", query)
        self.assertIn("consumed_at = CASE WHEN %s = 'failed'", query)
        self.assertEqual(params[0], "failed")

    def test_delivery_rejects_provider_reference_for_failed_delivery(self):
        conn = FakeConnection()
        self.assertFalse(otp.mark_challenge_delivery(conn, self.CHALLENGE, "failed", "provider-id"))
        self.assertEqual(conn.fake_cursor.calls[0][1][3], "provider-id")

    def test_delivery_rejects_invalid_state(self):
        with self.assertRaises(ValueError):
            otp.mark_challenge_delivery(FakeConnection(), self.CHALLENGE, "pending")


if __name__ == "__main__":
    unittest.main()
