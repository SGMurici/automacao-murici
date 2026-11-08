"""Pure scheduling policy helpers.

This module deliberately has no database, network, Flask, or provider dependencies.
It is safe to unit-test without touching production services.
"""

from datetime import datetime, timedelta, timezone


SCHEDULED = "scheduled"
PROCESSING = "processing"
PUBLISHED = "published"
RETRYABLE_FAILED = "retryable_failed"
UNCERTAIN = "uncertain"
OVERDUE = "overdue"

TERMINAL_STATES = {PUBLISHED}
KNOWN_STATES = {
    SCHEDULED,
    PROCESSING,
    PUBLISHED,
    RETRYABLE_FAILED,
    UNCERTAIN,
    OVERDUE,
}

_ALLOWED_TRANSITIONS = {
    SCHEDULED: {PROCESSING, OVERDUE},
    PROCESSING: {PUBLISHED, RETRYABLE_FAILED, UNCERTAIN, OVERDUE},
    RETRYABLE_FAILED: {PROCESSING, OVERDUE},
    UNCERTAIN: {PUBLISHED, RETRYABLE_FAILED, OVERDUE},
    OVERDUE: {PROCESSING, UNCERTAIN},
    PUBLISHED: set(),
}


class InvalidTransition(ValueError):
    """Raised when a queue item attempts an unsupported state transition."""


def validate_transition(current: str, target: str) -> None:
    """Raise InvalidTransition unless target is allowed from current."""
    if current not in KNOWN_STATES or target not in KNOWN_STATES:
        raise InvalidTransition("Unknown scheduler state.")
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"Transition {current!r} -> {target!r} is not allowed.")


def lease_expired(locked_at: datetime | None, *, now: datetime, lease_seconds: int) -> bool:
    """Return whether a processing lease has expired.

    Naive timestamps and non-positive lease durations are rejected to avoid
    silently mixing local time with UTC or disabling recovery accidentally.
    """
    if locked_at is None:
        return False
    if locked_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Lease timestamps must be timezone-aware.")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive.")
    return now.astimezone(timezone.utc) >= (
        locked_at.astimezone(timezone.utc) + timedelta(seconds=lease_seconds)
    )


def retry_delay_seconds(attempt: int, *, base_seconds: int = 30, max_seconds: int = 3600) -> int:
    """Bounded exponential backoff; first retry waits base_seconds."""
    if attempt < 1:
        raise ValueError("attempt must be >= 1.")
    if base_seconds < 1 or max_seconds < base_seconds:
        raise ValueError("Invalid backoff bounds.")
    return min(base_seconds * (2 ** (attempt - 1)), max_seconds)


def classify_publish_outcome(*, provider_accepted: bool, provider_id: str | None, transport_ambiguous: bool) -> str:
    """Classify provider outcome conservatively; never retry ambiguous outcomes blindly."""
    if provider_accepted and provider_id:
        return PUBLISHED
    if transport_ambiguous or provider_accepted:
        return UNCERTAIN
    return RETRYABLE_FAILED
