"""Provider-agnostic primitives for revocable application sessions.

The caller owns the database transaction. Raw session tokens are returned only
once; only SHA-256 digests are stored in PostgreSQL.
"""
import hashlib
import secrets


MIN_SESSION_TTL_SECONDS = 300
MAX_SESSION_TTL_SECONDS = 60 * 60 * 24 * 30


def hash_session_token(raw_token):
    if not isinstance(raw_token, str) or len(raw_token) < 32:
        raise ValueError("Token de sessão inválido.")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_session(conn, user_id, ttl_seconds=60 * 60 * 24 * 7, device_label=None):
    if not MIN_SESSION_TTL_SECONDS <= int(ttl_seconds) <= MAX_SESSION_TTL_SECONDS:
        raise ValueError("Prazo de sessão fora do limite permitido.")
    raw_token = secrets.token_urlsafe(48)
    token_hash = hash_session_token(raw_token)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO auth_sessions
               (token_hash, user_id, created_at, expires_at, last_seen_at, device_label)
               SELECT %s, id, NOW(),
                      NOW() + (%s * INTERVAL '1 second'), NOW(), %s
               FROM app_users
               WHERE id = %s AND status = 'active'
               RETURNING token_hash""",
            (token_hash, int(ttl_seconds), device_label, user_id),
        )
        if not cur.fetchone():
            raise ValueError("Usuário inexistente ou inativo.")
    return raw_token


def validate_session(conn, raw_token):
    try:
        token_hash = hash_session_token(raw_token)
    except ValueError:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE auth_sessions AS s
               SET last_seen_at = NOW()
               FROM app_users AS u
               WHERE s.token_hash = %s
                 AND s.user_id = u.id
                 AND u.status = 'active'
                 AND s.revoked_at IS NULL
                 AND s.expires_at > NOW()
               RETURNING s.user_id""",
            (token_hash,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def rotate_session(conn, raw_token, ttl_seconds=60 * 60 * 24 * 7, device_label=None):
    if not MIN_SESSION_TTL_SECONDS <= int(ttl_seconds) <= MAX_SESSION_TTL_SECONDS:
        raise ValueError("Prazo de sessão fora do limite permitido.")
    try:
        old_hash = hash_session_token(raw_token)
    except ValueError:
        return None
    new_token = secrets.token_urlsafe(48)
    new_hash = hash_session_token(new_token)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE auth_sessions AS s
               SET revoked_at = NOW(), replaced_by_token_hash = %s
               FROM app_users AS u
               WHERE s.token_hash = %s
                 AND s.user_id = u.id
                 AND u.status = 'active'
                 AND s.revoked_at IS NULL
                 AND s.expires_at > NOW()
               RETURNING s.user_id""",
            (new_hash, old_hash),
        )
        row = cur.fetchone()
        if not row:
            return None
        user_id = row[0]
        cur.execute(
            """INSERT INTO auth_sessions
               (token_hash, user_id, created_at, expires_at, last_seen_at, device_label)
               VALUES (%s, %s, NOW(),
                       NOW() + (%s * INTERVAL '1 second'), NOW(), %s)""",
            (new_hash, user_id, int(ttl_seconds), device_label),
        )
    return new_token


def revoke_session(conn, raw_token):
    try:
        token_hash = hash_session_token(raw_token)
    except ValueError:
        return False
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE auth_sessions
               SET revoked_at = NOW()
               WHERE token_hash = %s AND revoked_at IS NULL
               RETURNING token_hash""",
            (token_hash,),
        )
        return cur.fetchone() is not None


def revoke_all_sessions(conn, user_id):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE auth_sessions SET revoked_at = NOW()
               WHERE user_id = %s AND revoked_at IS NULL
               RETURNING token_hash""",
            (user_id,),
        )
        rows = cur.fetchall()
    return len(rows)
