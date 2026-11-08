import unittest
from datetime import datetime, timedelta, timezone

from scheduler_policy import (
    InvalidTransition,
    PUBLISHED,
    RETRYABLE_FAILED,
    UNCERTAIN,
    classify_publish_outcome,
    lease_expired,
    retry_delay_seconds,
    validate_transition,
)


class SchedulerPolicyTests(unittest.TestCase):
    def test_published_is_terminal(self):
        with self.assertRaises(InvalidTransition):
            validate_transition(PUBLISHED, "processing")

    def test_uncertain_must_be_reconciled_before_processing(self):
        with self.assertRaises(InvalidTransition):
            validate_transition(UNCERTAIN, "processing")

    def test_uncertain_can_be_confirmed_or_marked_retryable(self):
        validate_transition(UNCERTAIN, PUBLISHED)
        validate_transition(UNCERTAIN, RETRYABLE_FAILED)

    def test_lease_expiration_uses_utc_aware_timestamps(self):
        now = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
        self.assertFalse(lease_expired(now - timedelta(seconds=29), now=now, lease_seconds=30))
        self.assertTrue(lease_expired(now - timedelta(seconds=30), now=now, lease_seconds=30))

    def test_missing_lock_is_not_expired(self):
        now = datetime.now(timezone.utc)
        self.assertFalse(lease_expired(None, now=now, lease_seconds=30))

    def test_naive_timestamp_is_rejected(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            lease_expired(datetime(2026, 11, 8), now=now, lease_seconds=30)

    def test_backoff_is_exponential_and_bounded(self):
        self.assertEqual(retry_delay_seconds(1), 30)
        self.assertEqual(retry_delay_seconds(2), 60)
        self.assertEqual(retry_delay_seconds(20), 3600)

    def test_invalid_attempt_is_rejected(self):
        with self.assertRaises(ValueError):
            retry_delay_seconds(0)

    def test_ambiguous_outcome_is_uncertain(self):
        self.assertEqual(
            classify_publish_outcome(
                provider_accepted=False,
                provider_id=None,
                transport_ambiguous=True,
            ),
            UNCERTAIN,
        )

    def test_confirmed_provider_id_is_published(self):
        self.assertEqual(
            classify_publish_outcome(
                provider_accepted=True,
                provider_id="urn:li:share:123",
                transport_ambiguous=False,
            ),
            PUBLISHED,
        )

    def test_definite_pre_acceptance_failure_is_retryable(self):
        self.assertEqual(
            classify_publish_outcome(
                provider_accepted=False,
                provider_id=None,
                transport_ambiguous=False,
            ),
            RETRYABLE_FAILED,
        )


if __name__ == "__main__":
    unittest.main()
