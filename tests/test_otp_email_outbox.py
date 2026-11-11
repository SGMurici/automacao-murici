import unittest
from unittest.mock import patch

import otp_email_outbox


class OutboxCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows = list(self.rows)
        self.rows.clear()
        return rows


class OutboxConnection:
    def __init__(self, rows=None):
        self.cursor_value = OutboxCursor(rows)

    def cursor(self):
        return self.cursor_value


class OtpEmailOutboxTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {
            "OTP_DELIVERY_ENCRYPTION_KEY": "b" * 0,
        })
        self.env.start()
        from cryptography.fernet import Fernet
        self.key = Fernet.generate_key().decode("ascii")
        import os
        os.environ["OTP_DELIVERY_ENCRYPTION_KEY"] = self.key
        os.environ["IDENTITY_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        for name in ("IDENTITY_LOOKUP_PEPPER", "OTP_PEPPER", "OTP_RATE_LIMIT_PEPPER"):
            os.environ[name] = ("p" + name).encode().hex() + "x" * 40

    def tearDown(self):
        self.env.stop()

    def test_payload_is_encrypted_and_round_trips(self):
        payload = {
            "challenge_id": "123e4567-e89b-12d3-a456-426614174000",
            "recipient": "person@example.test",
            "code": "00001234",
            "purpose": "signup",
            "expires_minutes": 10,
        }
        with patch.object(otp_email_outbox, "_fernet") as fernet_factory:
            from cryptography.fernet import Fernet
            fernet_factory.return_value = Fernet(self.key.encode())
            encrypted = fernet_factory.return_value.encrypt(
                __import__("json").dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()
            ).decode()
            self.assertNotIn(payload["code"], encrypted)
            self.assertEqual(otp_email_outbox.decrypt_payload(encrypted), payload)

    def test_enqueue_writes_only_ciphertext(self):
        conn = OutboxConnection()
        with patch.object(otp_email_outbox, "_fernet") as fernet_factory:
            from cryptography.fernet import Fernet
            fernet_factory.return_value = Fernet(self.key.encode())
            otp_email_outbox.enqueue(
                conn, "123e4567-e89b-12d3-a456-426614174000",
                "person@example.test", "00001234", "signup",
            )
        query, params = conn.cursor_value.executed[0]
        self.assertIn("INSERT INTO otp_email_outbox", query)
        self.assertNotIn("00001234", params[1])
        self.assertNotIn("person@example.test", params[1])

    def test_claim_uses_skip_locked_and_expired_lease_recovery(self):
        conn = OutboxConnection()
        otp_email_outbox.claim_batch(conn, 5)
        query, params = conn.cursor_value.executed[0]
        self.assertIn("FOR UPDATE OF o SKIP LOCKED", query)
        self.assertIn("lease_expires_at <= NOW()", query)
        self.assertEqual(params, (8, 5, 45))

    def test_mark_sent_requires_current_lease_and_erases_ciphertext(self):
        conn = OutboxConnection([("challenge",)])
        with patch("otp_core.mark_otp_delivery", return_value=True):
            self.assertTrue(otp_email_outbox.mark_sent(
                conn, "challenge", "lease", "<id@example.test>"
            ))
        query = conn.cursor_value.executed[0][0]
        self.assertIn("lease_token = %s", query)
        self.assertIn("payload_ciphertext = NULL", query)

    def test_failure_is_retryable_or_terminal_and_lease_bound(self):
        conn = OutboxConnection([("challenge",)])
        self.assertTrue(otp_email_outbox.mark_failure(
            conn, "challenge", "lease", 1, False, "provider_transient"
        ))
        query, params = conn.cursor_value.executed[0]
        self.assertIn("lease_token = %s", query)
        self.assertIn("lease_expires_at > NOW()", query)
        self.assertEqual(params[0], False)

    def test_configuration_key_must_be_independent(self):
        import os
        os.environ["IDENTITY_ENCRYPTION_KEY"] = self.key
        with self.assertRaises(otp_email_outbox.OutboxConfigurationError):
            otp_email_outbox.validate_key_configuration()


if __name__ == "__main__":
    unittest.main()
