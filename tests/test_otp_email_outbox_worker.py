"""Worker-level tests for terminal handling of invalid OTP outbox payloads."""
import unittest
from unittest.mock import patch

import otp_email_outbox
import otp_email_outbox_worker


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        return None


class OtpEmailOutboxWorkerTests(unittest.TestCase):
    def test_expired_uncertain_lease_is_included_in_worker_stats(self):
        with (
            patch.object(otp_email_outbox, "expire_due", return_value={"uncertain": 1, "failed": 2}),
            patch.object(otp_email_outbox, "claim_batch", return_value=[]),
        ):
            stats = otp_email_outbox_worker.run_once(Connection)
        self.assertEqual(stats["uncertain"], 1)
        self.assertEqual(stats["failed"], 2)

    def test_ambiguous_smtp_failure_is_uncertain_and_not_retried(self):
        job = {
            "challenge_id": "123e4567-e89b-12d3-a456-426614174000",
            "ciphertext": "encrypted-payload",
            "lease_token": "lease-token",
            "attempts": 1,
        }
        payload = {
            "challenge_id": job["challenge_id"],
            "recipient": "person@example.test",
            "code": "00001234",
            "purpose": "signup",
            "expires_minutes": 10,
        }
        with (
            patch.object(otp_email_outbox, "expire_due"),
            patch.object(otp_email_outbox, "claim_batch", return_value=[job]),
            patch.object(otp_email_outbox, "decrypt_payload", return_value=payload),
            patch.object(otp_email_outbox, "mark_dispatching", return_value=True),
            patch.object(otp_email_outbox, "mark_uncertain", return_value=True) as mark_uncertain,
            patch.object(otp_email_outbox, "mark_failure") as mark_failure,
            patch.object(
                otp_email_outbox_worker.email_delivery,
                "send_otp_email",
                side_effect=otp_email_outbox_worker.email_delivery.EmailDeliveryUncertain(),
            ) as send_email,
        ):
            stats = otp_email_outbox_worker.run_once(Connection)

        send_email.assert_called_once()
        mark_uncertain.assert_called_once_with(unittest.mock.ANY, job["challenge_id"], job["lease_token"])
        mark_failure.assert_not_called()
        self.assertEqual(stats, {"claimed": 1, "sent": 0, "retrying": 0, "failed": 0, "uncertain": 1})

    def test_database_failure_after_smtp_success_is_not_retried(self):
        job = {
            "challenge_id": "123e4567-e89b-12d3-a456-426614174000",
            "ciphertext": "encrypted-payload",
            "lease_token": "lease-token",
            "attempts": 1,
        }
        payload = {
            "challenge_id": job["challenge_id"],
            "recipient": "person@example.test",
            "code": "00001234",
            "purpose": "signup",
            "expires_minutes": 10,
        }
        with (
            patch.object(otp_email_outbox, "expire_due"),
            patch.object(otp_email_outbox, "claim_batch", return_value=[job]),
            patch.object(otp_email_outbox, "decrypt_payload", return_value=payload),
            patch.object(otp_email_outbox, "mark_dispatching", return_value=True),
            patch.object(otp_email_outbox, "mark_sent", side_effect=RuntimeError("database unavailable")),
            patch.object(otp_email_outbox, "mark_failure") as mark_failure,
            patch.object(otp_email_outbox, "mark_uncertain") as mark_uncertain,
            patch.object(
                otp_email_outbox_worker.email_delivery,
                "send_otp_email",
                return_value={"message_id": "<accepted@example.test>"},
            ) as send_email,
        ):
            with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                otp_email_outbox_worker.run_once(Connection)

        send_email.assert_called_once()
        mark_failure.assert_not_called()
        mark_uncertain.assert_not_called()

    def test_pre_send_smtp_failure_remains_retryable(self):
        job = {
            "challenge_id": "123e4567-e89b-12d3-a456-426614174000",
            "ciphertext": "encrypted-payload",
            "lease_token": "lease-token",
            "attempts": 1,
        }
        payload = {
            "challenge_id": job["challenge_id"],
            "recipient": "person@example.test",
            "code": "00001234",
            "purpose": "signup",
            "expires_minutes": 10,
        }
        with (
            patch.object(otp_email_outbox, "expire_due"),
            patch.object(otp_email_outbox, "claim_batch", return_value=[job]),
            patch.object(otp_email_outbox, "decrypt_payload", return_value=payload),
            patch.object(otp_email_outbox, "mark_dispatching", return_value=True),
            patch.object(otp_email_outbox, "mark_failure", return_value=True) as mark_failure,
            patch.object(otp_email_outbox, "mark_uncertain") as mark_uncertain,
            patch.object(
                otp_email_outbox_worker.email_delivery,
                "send_otp_email",
                side_effect=otp_email_outbox_worker.email_delivery.EmailDeliveryError(),
            ),
        ):
            stats = otp_email_outbox_worker.run_once(Connection)

        mark_failure.assert_called_once_with(
            unittest.mock.ANY, job["challenge_id"], job["lease_token"],
            job["attempts"], False, "provider_transient",
        )
        mark_uncertain.assert_not_called()
        self.assertEqual(stats, {"claimed": 1, "sent": 0, "retrying": 1, "failed": 0, "uncertain": 0})

    def test_challenge_mismatch_is_terminal_and_never_sent(self):
        job = {
            "challenge_id": "123e4567-e89b-12d3-a456-426614174000",
            "ciphertext": "encrypted-payload",
            "lease_token": "lease-token",
            "attempts": 1,
        }
        mismatched_payload = {
            "challenge_id": "123e4567-e89b-12d3-a456-426614174001",
            "recipient": "person@example.test",
            "code": "00001234",
            "purpose": "signup",
            "expires_minutes": 10,
        }
        with (
            patch.object(otp_email_outbox, "expire_due"),
            patch.object(otp_email_outbox, "claim_batch", return_value=[job]),
            patch.object(otp_email_outbox, "decrypt_payload", return_value=mismatched_payload),
            patch.object(otp_email_outbox, "mark_failure", return_value=True) as mark_failure,
            patch.object(otp_email_outbox_worker.email_delivery, "send_otp_email") as send_email,
        ):
            stats = otp_email_outbox_worker.run_once(Connection)

        send_email.assert_not_called()
        mark_failure.assert_called_once_with(
            unittest.mock.ANY,
            job["challenge_id"],
            job["lease_token"],
            job["attempts"],
            True,
            "payload_invalid",
        )
        self.assertEqual(stats, {"claimed": 1, "sent": 0, "retrying": 0, "failed": 1, "uncertain": 0})


if __name__ == "__main__":
    unittest.main()
