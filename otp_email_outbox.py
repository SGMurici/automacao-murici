"""Encrypted transactional outbox for OTP email delivery.

The API inserts an encrypted delivery intent in the same transaction as its
OTP challenge. A separate one-shot worker claims jobs with recoverable leases.
"""
import json
import os
import uuid

from cryptography.fernet import Fernet, InvalidToken

import identity_auth_core


TERMINAL_ATTEMPTS = 8
LEASE_SECONDS = 45
SMTP_TIMEOUT_MAX_SECONDS = 30


class OutboxConfigurationError(RuntimeError):
    pass


class OutboxPayloadError(RuntimeError):
    pass


def _fernet():
    raw = os.environ.get("OTP_DELIVERY_ENCRYPTION_KEY", "")
    if not raw:
        raise OutboxConfigurationError("OTP delivery encryption key is missing")
    try:
        key = raw.encode("ascii")
        cipher = Fernet(key)
        peers = []
        for name in (
            "IDENTITY_ENCRYPTION_KEY",
            "TOKEN_ENCRYPTION_KEY",
        ):
            value = os.environ.get(name, "")
            if value:
                peers.append(value.encode("ascii"))
        for name in ("IDENTITY_LOOKUP_PEPPER", "OTP_PEPPER", "OTP_RATE_LIMIT_PEPPER"):
            value = os.environ.get(name, "")
            if value:
                peers.append(identity_auth_core.required_pepper(name, os.environ))
        if key in peers:
            raise OutboxConfigurationError("OTP delivery key must be independent")
        return cipher
    except (ValueError, UnicodeEncodeError) as exc:
        raise OutboxConfigurationError("OTP delivery encryption key is invalid") from exc


def validate_key_configuration():
    _fernet()
    return True


def enqueue(conn, challenge_id, recipient, code, purpose, expires_minutes=10):
    if purpose not in {"signup", "login", "verify_identity", "recovery"}:
        raise ValueError("Invalid OTP purpose")
    if not isinstance(recipient, str) or not recipient or len(recipient) > 254:
        raise ValueError("Invalid OTP recipient")
    if not isinstance(code, str) or len(code) != 8 or not code.isascii() or not code.isdigit():
        raise ValueError("Invalid OTP code")
    if isinstance(expires_minutes, bool) or not isinstance(expires_minutes, int) or not 1 <= expires_minutes <= 15:
        raise ValueError("Invalid OTP expiry")
    payload = {
        "challenge_id": str(uuid.UUID(str(challenge_id))),
        "recipient": recipient,
        "code": code,
        "purpose": purpose,
        "expires_minutes": expires_minutes,
    }
    ciphertext = _fernet().encrypt(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).decode("ascii")
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO otp_email_outbox
                   (challenge_id, payload_ciphertext, status, attempts, available_at)
               VALUES (%s, %s, 'pending', 0, NOW())""",
            (payload["challenge_id"], ciphertext),
        )


def expire_due(conn):
    """Fail and erase queued payloads whose OTP challenge expired before delivery."""
    with conn.cursor() as cur:
        cur.execute(
            """WITH expired AS (
                   UPDATE otp_email_outbox o
                   SET status = 'failed', payload_ciphertext = NULL,
                       lease_token = NULL, lease_expires_at = NULL,
                       last_error_code = 'expired', updated_at = NOW()
                   FROM otp_challenges c
                   WHERE c.id = o.challenge_id
                     AND c.expires_at <= NOW()
                     AND o.status IN ('pending', 'processing')
                   RETURNING o.challenge_id
               )
               UPDATE otp_challenges c
               SET delivery_status = 'failed',
                   delivery_attempted_at = COALESCE(delivery_attempted_at, NOW()),
                   consumed_at = COALESCE(consumed_at, NOW())
               FROM expired
               WHERE c.id = expired.challenge_id
                 AND c.delivery_status = 'pending'
               RETURNING c.id"""
        )
        return cur.rowcount


def claim_batch(conn, limit=10):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Invalid batch size")
    with conn.cursor() as cur:
        cur.execute(
            """WITH due AS (
                   SELECT o.challenge_id
                   FROM otp_email_outbox o
                   JOIN otp_challenges c ON c.id = o.challenge_id
                   WHERE (
                       (o.status = 'pending' AND o.available_at <= NOW())
                       OR (o.status = 'processing' AND o.lease_expires_at <= NOW())
                   )
                     AND c.expires_at > NOW()
                     AND c.consumed_at IS NULL
                     AND c.delivery_status = 'pending'
                     AND o.attempts < %s
                   ORDER BY o.available_at, o.created_at
                   FOR UPDATE OF o SKIP LOCKED
                   LIMIT %s
               )
               UPDATE otp_email_outbox o
               SET status = 'processing',
                   attempts = o.attempts + 1,
                   lease_token = gen_random_uuid(),
                   lease_expires_at = NOW() + (%s * INTERVAL '1 second'),
                   updated_at = NOW()
               FROM due
               WHERE o.challenge_id = due.challenge_id
               RETURNING o.challenge_id, o.payload_ciphertext,
                         o.lease_token, o.attempts""",
            (TERMINAL_ATTEMPTS, limit, LEASE_SECONDS),
        )
        rows = cur.fetchall()
    return [
        {
            "challenge_id": str(row[0]),
            "ciphertext": row[1],
            "lease_token": str(row[2]),
            "attempts": row[3],
        }
        for row in rows
    ]


def decrypt_payload(ciphertext):
    try:
        raw = _fernet().decrypt(ciphertext.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, UnicodeError) as exc:
        raise OutboxPayloadError("OTP outbox payload is invalid") from exc
    required = {"challenge_id", "recipient", "code", "purpose", "expires_minutes"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise OutboxPayloadError("OTP outbox payload schema is invalid")
    if str(uuid.UUID(payload["challenge_id"])) == "":
        raise OutboxPayloadError("OTP outbox challenge is invalid")
    if payload["purpose"] not in {"signup", "login", "verify_identity", "recovery"}:
        raise OutboxPayloadError("OTP outbox purpose is invalid")
    if not isinstance(payload["recipient"], str) or not payload["recipient"]:
        raise OutboxPayloadError("OTP outbox recipient is invalid")
    if not isinstance(payload["code"], str) or len(payload["code"]) != 8 or not payload["code"].isascii() or not payload["code"].isdigit():
        raise OutboxPayloadError("OTP outbox code is invalid")
    if isinstance(payload["expires_minutes"], bool) or not isinstance(payload["expires_minutes"], int) or not 1 <= payload["expires_minutes"] <= 15:
        raise OutboxPayloadError("OTP outbox expiry is invalid")
    return payload


def mark_sent(conn, challenge_id, lease_token, provider_reference):
    if not isinstance(provider_reference, str) or not provider_reference.strip() or len(provider_reference) > 160:
        raise ValueError("Invalid provider reference")
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE otp_email_outbox
               SET status = 'sent', payload_ciphertext = NULL,
                   provider_reference = %s, lease_token = NULL,
                   lease_expires_at = NULL, last_error_code = NULL,
                   sent_at = NOW(), updated_at = NOW()
               WHERE challenge_id = %s AND status = 'processing'
                 AND lease_token = %s AND lease_expires_at > NOW()
               RETURNING challenge_id""",
            (provider_reference.strip(), challenge_id, lease_token),
        )
        row = cur.fetchone()
    if not row:
        return False
    import otp_core
    if not otp_core.mark_otp_delivery(conn, challenge_id, "sent", provider_reference):
        raise RuntimeError("OTP challenge could not be marked sent")
    return True


def mark_failure(conn, challenge_id, lease_token, attempts, terminal, error_code):
    allowed_codes = {"configuration", "provider_transient", "payload_invalid", "expired"}
    if error_code not in allowed_codes:
        error_code = "provider_transient"
    terminal = bool(terminal or attempts >= TERMINAL_ATTEMPTS)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE otp_email_outbox o
               SET status = CASE WHEN %s THEN 'failed' ELSE 'pending' END,
                   payload_ciphertext = CASE WHEN %s THEN NULL ELSE payload_ciphertext END,
                   available_at = CASE WHEN %s THEN o.available_at
                       ELSE NOW() + (LEAST(900, (2 ^ LEAST(o.attempts, 9))::int) * INTERVAL '1 second') END,
                   lease_token = NULL, lease_expires_at = NULL,
                   last_error_code = %s, updated_at = NOW()
               WHERE o.challenge_id = %s AND o.status = 'processing'
                 AND o.lease_token = %s
               RETURNING o.challenge_id""",
            (terminal, terminal, terminal, error_code, challenge_id, lease_token),
        )
        row = cur.fetchone()
    if not row:
        return False
    if terminal:
        import otp_core
        if not otp_core.mark_otp_delivery(conn, challenge_id, "failed"):
            raise RuntimeError("OTP challenge could not be marked failed")
    return True
