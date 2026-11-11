"""Security primitives for purpose-bound email OTP challenges.

The caller owns the database transaction. This module never sends email and
never logs OTPs or secrets. Challenges store only keyed digests.
"""
import hashlib
import hmac
import math
import secrets
import uuid
from datetime import datetime, timedelta, timezone


OTP_DIGITS = 8
OTP_TTL_SECONDS = 600
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_PEPPER_ENV = "OTP_PEPPER"
VALID_PURPOSES = {"signup", "login", "verify_identity", "recovery"}
VALID_RATE_LIMIT_SCOPES = {"otp_identity", "otp_ip"}


def normalize_email(value):
    """Normalize an email for lookup; intentionally conservative, not RFC parsing."""
    if not isinstance(value, str):
        raise ValueError("E-mail inválido.")
    email = value.strip().lower()
    if len(email) > 254 or email.count("@") != 1:
        raise ValueError("E-mail inválido.")
    local, domain = email.rsplit("@", 1)
    if not local or not domain or len(local) > 64 or "." not in domain:
        raise ValueError("E-mail inválido.")
    if any(ch.isspace() for ch in email) or any(ord(ch) < 33 for ch in email):
        raise ValueError("E-mail inválido.")
    if domain.startswith(".") or domain.endswith(".") or ".." in email:
        raise ValueError("E-mail inválido.")
    return email


def _secret_bytes(secret):
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("OTP_PEPPER ausente ou fraco.")
    return secret


def generate_otp():
    """Return an eight-digit code, preserving leading zeroes."""
    return "".join(secrets.choice("0123456789") for _ in range(OTP_DIGITS))


def generate_challenge_id():
    return str(uuid.uuid4())


def otp_digest(secret, challenge_id, purpose, code):
    """Bind a keyed digest to challenge ID and purpose to prevent cross-use."""
    key = _secret_bytes(secret)
    if purpose not in VALID_PURPOSES:
        raise ValueError("Finalidade OTP inválida.")
    try:
        challenge = str(uuid.UUID(str(challenge_id)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Desafio OTP inválido.")
    if not isinstance(code, str) or len(code) != OTP_DIGITS or not code.isascii() or not code.isdigit():
        raise ValueError("Código OTP inválido.")
    message = f"kappa-otp-v1:{challenge}:{purpose}:{code}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).digest()


def verify_otp(secret, challenge_id, purpose, code, expected_digest):
    if not isinstance(expected_digest, (bytes, bytearray)):
        return False
    try:
        candidate = otp_digest(secret, challenge_id, purpose, code)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, bytes(expected_digest))


def privacy_key_hash(secret, scope, value):
    """HMAC lookup key; raw email/IP must not be persisted in limiter buckets."""
    key = _secret_bytes(secret)
    if scope not in VALID_RATE_LIMIT_SCOPES:
        raise ValueError("Escopo de limite inválido.")
    if not isinstance(value, str) or not value:
        raise ValueError("Chave de limite inválida.")
    normalized = value.strip().lower() if scope == "otp_identity" else value.strip()
    if not normalized or len(normalized) > 512:
        raise ValueError("Chave de limite inválida.")
    message = f"kappa-rate-limit-v1:{scope}:{normalized}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).digest()


def challenge_expiry(now=None, ttl_seconds=OTP_TTL_SECONDS):
    if isinstance(ttl_seconds, bool) or not 60 <= int(ttl_seconds) <= 900:
        raise ValueError("Validade OTP fora do limite permitido.")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Data/hora precisa conter fuso horário.")
    return current + timedelta(seconds=int(ttl_seconds))


def rate_limit_window(now, window_seconds):
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Data/hora precisa conter fuso horário.")
    if isinstance(window_seconds, bool) or not 60 <= int(window_seconds) <= 86400:
        raise ValueError("Janela de limite inválida.")
    epoch = math.floor(now.timestamp() / int(window_seconds)) * int(window_seconds)
    start = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return start, start + timedelta(seconds=int(window_seconds))


def record_rate_limit_hit(conn, scope, key_hash, now, window_seconds, limit):
    """Atomically consume one slot in a shared fixed-window PostgreSQL bucket.

    Returns False once the bucket reaches limit. Caller commits/rolls back.
    """
    if scope not in VALID_RATE_LIMIT_SCOPES:
        raise ValueError("Escopo de limite inválido.")
    if not isinstance(key_hash, (bytes, bytearray)) or len(key_hash) != 32:
        raise ValueError("Hash de limite inválido.")
    if isinstance(limit, bool) or not 1 <= int(limit) <= 10000:
        raise ValueError("Limite de requisições inválido.")
    start, end = rate_limit_window(now, window_seconds)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO auth_rate_limit_buckets
                   (scope, key_hash, window_started_at, hit_count, expires_at, updated_at)
               VALUES (%s, %s, %s, 1, %s, NOW())
               ON CONFLICT (scope, key_hash, window_started_at)
               DO UPDATE SET hit_count = auth_rate_limit_buckets.hit_count + 1,
                             updated_at = NOW()
               WHERE auth_rate_limit_buckets.hit_count < %s
               RETURNING hit_count""",
            (scope, bytes(key_hash), start, end, int(limit)),
        )
        return cur.fetchone() is not None


def mark_challenge_delivery(conn, challenge_id, delivery_status, provider_reference=None):
    """Move a pending challenge to sent or failed; failed codes become unusable."""
    if delivery_status not in {"sent", "failed"}:
        raise ValueError("Estado de entrega inválido.")
    if provider_reference is not None:
        if not isinstance(provider_reference, str) or not provider_reference.strip() or len(provider_reference) > 160:
            raise ValueError("Referência de entrega inválida.")
        provider_reference = provider_reference.strip()
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE otp_challenges
               SET delivery_attempted_at = COALESCE(delivery_attempted_at, NOW()),
                   delivery_status = %s,
                   sent_at = CASE WHEN %s = 'sent' THEN NOW() ELSE NULL END,
                   provider_reference = CASE WHEN %s = 'sent' THEN %s ELSE NULL END,
                   consumed_at = CASE WHEN %s = 'failed' THEN NOW() ELSE consumed_at END,
                   resend_after = CASE WHEN %s = 'sent'
                       THEN NOW() + (%s * INTERVAL '1 second') ELSE resend_after END
               WHERE id = %s
                 AND delivery_status = 'pending'
                 AND consumed_at IS NULL
                 AND expires_at > NOW()
               RETURNING id""",
            (
                delivery_status, delivery_status, delivery_status, provider_reference,
                delivery_status, delivery_status, OTP_RESEND_COOLDOWN_SECONDS, challenge_id,
            ),
        )
        return cur.fetchone() is not None
