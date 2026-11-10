"""Provider-agnostic, single-use OTP challenge primitives.

Delivery adapters must send the returned code and then mark delivery as sent.
Never expose the raw code through a public API or write it to logs.
The caller owns and commits the database transaction.
"""
import hashlib
import hmac
import re
import secrets
import uuid


OTP_CODE_DIGITS = 6
MIN_TTL_SECONDS = 60
MAX_TTL_SECONDS = 900
MIN_PEPPER_BYTES = 32
VALID_IDENTITY_TYPES = {"email", "phone"}
VALID_PURPOSES = {"signup", "login", "verify_identity", "recovery"}


def _validate_pepper(pepper):
    if not isinstance(pepper, bytes) or len(pepper) < MIN_PEPPER_BYTES:
        raise ValueError("OTP pepper deve conter ao menos 32 bytes.")
    return pepper


def _validate_identity_hash(identity_lookup_hash):
    if not isinstance(identity_lookup_hash, bytes) or len(identity_lookup_hash) != 32:
        raise ValueError("Hash de identidade deve ser SHA-256 em bytes.")
    return identity_lookup_hash


def _code_digest(challenge_id, code, pepper):
    pepper = _validate_pepper(pepper)
    message = f"{challenge_id}:{code}".encode("ascii")
    return hmac.new(pepper, message, hashlib.sha256).digest()


def create_otp_challenge(
    conn,
    identity_type,
    identity_lookup_hash,
    purpose,
    pepper,
    ttl_seconds=300,
    max_attempts=5,
):
    """Create a challenge and return its raw code once for a private delivery adapter."""
    pepper = _validate_pepper(pepper)
    identity_lookup_hash = _validate_identity_hash(identity_lookup_hash)
    if identity_type not in VALID_IDENTITY_TYPES:
        raise ValueError("Tipo de identidade inválido.")
    if purpose not in VALID_PURPOSES:
        raise ValueError("Finalidade do OTP inválida.")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise ValueError("TTL do OTP deve ser inteiro.")
    if not MIN_TTL_SECONDS <= ttl_seconds <= MAX_TTL_SECONDS:
        raise ValueError("TTL do OTP fora do intervalo permitido.")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
        raise ValueError("Limite de tentativas deve ser inteiro.")
    if not 1 <= max_attempts <= 10:
        raise ValueError("Limite de tentativas fora do intervalo permitido.")

    challenge_id = str(uuid.uuid4())
    code = f"{secrets.randbelow(10 ** OTP_CODE_DIGITS):0{OTP_CODE_DIGITS}d}"
    digest = _code_digest(challenge_id, code, pepper)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO otp_challenges (
                   id, identity_type, identity_lookup_hash, purpose,
                   code_hash, expires_at, max_attempts, delivery_status
               )
               VALUES (
                   %s, %s, %s, %s, %s,
                   NOW() + (%s * INTERVAL '1 second'), %s, 'pending'
               )
               RETURNING id""",
            (
                challenge_id,
                identity_type,
                identity_lookup_hash,
                purpose,
                digest,
                ttl_seconds,
                max_attempts,
            ),
        )
        row = cur.fetchone()
    if not row:
        raise RuntimeError("Não foi possível registrar o desafio OTP.")
    return {"challenge_id": str(row[0]), "code": code}


def mark_otp_delivery(conn, challenge_id, delivery_status):
    """Mark a pending challenge sent/failed after the delivery adapter responds."""
    if delivery_status not in {"sent", "failed"}:
        raise ValueError("Estado de entrega OTP inválido.")
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE otp_challenges
               SET delivery_status = %s
               WHERE id = %s
                 AND delivery_status = 'pending'
                 AND consumed_at IS NULL
                 AND expires_at > NOW()
               RETURNING id""",
            (delivery_status, challenge_id),
        )
        return cur.fetchone() is not None


def verify_otp_challenge(conn, challenge_id, code, pepper):
    """Verify a sent, unexpired challenge once, consuming it atomically on success."""
    pepper = _validate_pepper(pepper)
    if not isinstance(code, str) or re.fullmatch(r"[0-9]{6}", code) is None:
        return False
    if not isinstance(challenge_id, str) or not challenge_id:
        return False

    with conn.cursor() as cur:
        cur.execute(
            """SELECT code_hash, (expires_at > NOW()), consumed_at,
                      failed_attempts, max_attempts, delivery_status
               FROM otp_challenges
               WHERE id = %s
               FOR UPDATE""",
            (challenge_id,),
        )
        row = cur.fetchone()
        if not row:
            return False
        stored_hash, unexpired, consumed_at, failed_attempts, max_attempts, delivery_status = row
        if (
            not unexpired
            or consumed_at is not None
            or delivery_status != "sent"
            or failed_attempts >= max_attempts
        ):
            return False

        candidate = _code_digest(challenge_id, code, pepper)
        if hmac.compare_digest(bytes(stored_hash), candidate):
            cur.execute(
                """UPDATE otp_challenges
                   SET consumed_at = NOW()
                   WHERE id = %s
                     AND consumed_at IS NULL
                     AND failed_attempts < max_attempts
                     AND delivery_status = 'sent'
                     AND expires_at > NOW()
                   RETURNING id""",
                (challenge_id,),
            )
            return cur.fetchone() is not None

        cur.execute(
            """UPDATE otp_challenges
               SET failed_attempts = failed_attempts + 1
               WHERE id = %s
                 AND consumed_at IS NULL
                 AND failed_attempts < max_attempts
                 AND delivery_status = 'sent'
                 AND expires_at > NOW()
               RETURNING failed_attempts""",
            (challenge_id,),
        )
        return False
