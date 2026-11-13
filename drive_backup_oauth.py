"""Short-lived, tenant-bound Google Drive OAuth authorization-code + PKCE flow.

This module stores only a hash of state and an encrypted PKCE verifier.
The authorization code exchange must happen server-side using the exact
redirect_uri persisted with the flow. Never log state, verifier, code or tokens.
"""
import base64
import hashlib
import secrets
import urllib.parse


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
FLOW_PURPOSE = "drive_backup"
FLOW_PROVIDER = "google"


def _encrypt(encrypt, value):
    if not callable(encrypt):
        raise ValueError("Criptografia indisponível.")
    ciphertext = encrypt(value)
    if not isinstance(ciphertext, (bytes, bytearray)) or not ciphertext:
        raise ValueError("Ciphertext inválido.")
    return bytes(ciphertext)


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def create_flow(conn, *, user_id, tenant_id, redirect_uri, client_id, encrypt):
    """Create a 10-minute OAuth flow; verifier stays encrypted server-side."""
    if not isinstance(redirect_uri, str) or not redirect_uri.startswith("https://"):
        raise ValueError("Redirect URI HTTPS obrigatória.")
    if not isinstance(client_id, str) or not client_id.strip():
        raise ValueError("Client ID Google obrigatório.")
    state = secrets.token_urlsafe(32)
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    verifier_ciphertext = _encrypt(encrypt, verifier)

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO oauth_states
                   (state_hash, provider, browser_session_id, account_name,
                    purpose, user_id, tenant_id, code_verifier_ciphertext,
                    redirect_uri, created_at, expires_at)
               SELECT %s, %s, NULL, NULL, %s, u.id, m.tenant_id, %s, %s,
                      NOW(), NOW() + INTERVAL '10 minutes'
               FROM app_users AS u
               JOIN tenant_memberships AS m ON m.user_id = u.id
               WHERE u.id = %s AND u.status = 'active'
                 AND m.tenant_id = %s AND m.status = 'active'
               RETURNING state_hash""",
            (
                hashlib.sha256(state.encode("utf-8")).hexdigest(),
                FLOW_PROVIDER, FLOW_PURPOSE, verifier_ciphertext, redirect_uri,
                user_id, tenant_id,
            ),
        )
        if not cur.fetchone():
            raise PermissionError("Usuário ativo ou vínculo com tenant não encontrado.")

    params = {
        "client_id": client_id.strip(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": f"openid email {GOOGLE_DRIVE_SCOPE}",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "false",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return {
        "state": state,
        "authorization_url": f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}",
        "expires_in": 600,
    }


def consume_flow(conn, *, state, decrypt):
    """Atomically consume state once and return its bound OAuth context."""
    if not isinstance(state, str) or len(state) < 32:
        return None
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    with conn.cursor() as cur:
        cur.execute(
            """DELETE FROM oauth_states
               WHERE state_hash = %s
                 AND provider = %s
                 AND purpose = %s
                 AND expires_at > NOW()
               RETURNING user_id, tenant_id, code_verifier_ciphertext, redirect_uri""",
            (state_hash, FLOW_PROVIDER, FLOW_PURPOSE),
        )
        row = cur.fetchone()
    if not row:
        return None
    if not callable(decrypt) or not row[2]:
        raise ValueError("Verificador PKCE indisponível.")
    verifier = decrypt(bytes(row[2]))
    if not isinstance(verifier, str) or len(verifier) < 43:
        raise ValueError("Verificador PKCE inválido.")
    return {
        "user_id": row[0],
        "tenant_id": row[1],
        "code_verifier": verifier,
        "redirect_uri": row[3],
    }
