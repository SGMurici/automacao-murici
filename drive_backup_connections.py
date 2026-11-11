"""Tenant-scoped Google Drive backup connection persistence.

OAuth exchange and consent UI are intentionally separate. Call save_connection
only after a trusted OAuth flow has validated state/PKCE, exchanged the code,
verified the Google subject and confirmed the granted scopes.
"""
from datetime import datetime, timezone


PROVIDER = "google_drive_backup"
REQUIRED_SCOPE = "https://www.googleapis.com/auth/drive.file"
FORBIDDEN_BROAD_SCOPES = {
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.readonly",
}


def validate_granted_scopes(scopes):
    if isinstance(scopes, str):
        scopes = scopes.split()
    if not isinstance(scopes, (list, tuple, set)):
        raise ValueError("Escopos OAuth inválidos.")
    normalized = {scope.strip() for scope in scopes if isinstance(scope, str) and scope.strip()}
    if REQUIRED_SCOPE not in normalized:
        raise ValueError("A autorização não concedeu o escopo mínimo do backup.")
    if normalized & FORBIDDEN_BROAD_SCOPES:
        raise ValueError("A autorização concedeu escopo amplo demais para o backup.")
    return sorted(normalized)


def _required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} é obrigatório.")
    return value.strip()


def _ciphertext(encrypt, token):
    if not callable(encrypt):
        raise ValueError("Função de criptografia indisponível.")
    value = encrypt(token)
    if not isinstance(value, (bytes, bytearray)) or not value:
        raise ValueError("A criptografia não retornou ciphertext binário.")
    return bytes(value)


def save_connection(
    conn,
    *,
    user_id,
    tenant_id,
    google_subject,
    account_label,
    granted_scopes,
    access_token,
    refresh_token,
    token_expires_at,
    encrypt,
):
    """Create/update a Drive connection only for an active tenant member."""
    user_id = _required_text(str(user_id) if user_id is not None else "", "user_id")
    tenant_id = _required_text(str(tenant_id) if tenant_id is not None else "", "tenant_id")
    google_subject = _required_text(google_subject, "google_subject")
    access_token = _required_text(access_token, "access_token")
    refresh_token = _required_text(refresh_token, "refresh_token")
    scopes = validate_granted_scopes(granted_scopes)
    if token_expires_at is not None and not isinstance(token_expires_at, datetime):
        raise ValueError("token_expires_at deve ser datetime ou None.")
    if token_expires_at and token_expires_at.tzinfo is None:
        token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)

    access_ciphertext = _ciphertext(encrypt, access_token)
    refresh_ciphertext = _ciphertext(encrypt, refresh_token)
    label = account_label.strip()[:160] if isinstance(account_label, str) else None

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO external_connections
                   (id, user_id, tenant_id, provider, external_account_id,
                    account_label, granted_scopes, access_token_ciphertext,
                    refresh_token_ciphertext, token_expires_at, status,
                    created_at, updated_at)
               SELECT gen_random_uuid(), u.id, m.tenant_id, %s, %s,
                      %s, %s, %s, %s, %s, 'active', NOW(), NOW()
               FROM app_users AS u
               JOIN tenant_memberships AS m ON m.user_id = u.id
               WHERE u.id = %s
                 AND u.status = 'active'
                 AND m.tenant_id = %s
                 AND m.status = 'active'
               ON CONFLICT (tenant_id, provider, external_account_id)
               DO UPDATE SET
                   account_label = EXCLUDED.account_label,
                   granted_scopes = EXCLUDED.granted_scopes,
                   access_token_ciphertext = EXCLUDED.access_token_ciphertext,
                   refresh_token_ciphertext = EXCLUDED.refresh_token_ciphertext,
                   token_expires_at = EXCLUDED.token_expires_at,
                   status = 'active',
                   revoked_at = NULL,
                   updated_at = NOW()
               WHERE external_connections.user_id = EXCLUDED.user_id
               RETURNING id""",
            (
                PROVIDER, google_subject, label, scopes, access_ciphertext,
                refresh_ciphertext, token_expires_at, user_id, tenant_id,
            ),
        )
        row = cur.fetchone()
    if not row:
        raise PermissionError("Usuário ou vínculo ativo com o tenant não encontrado, ou conexão pertence a outro titular.")
    return row[0]


def get_connection(conn, *, user_id, tenant_id, connection_id, decrypt):
    """Return credentials only to the exact owning user and active tenant."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, external_account_id, account_label, granted_scopes,
                      access_token_ciphertext, refresh_token_ciphertext,
                      token_expires_at
               FROM external_connections
               WHERE id = %s AND user_id = %s AND tenant_id = %s
                 AND provider = %s AND status = 'active'
                 AND revoked_at IS NULL
               LIMIT 1""",
            (connection_id, user_id, tenant_id, PROVIDER),
        )
        row = cur.fetchone()
    if not row:
        return None
    if not callable(decrypt):
        raise ValueError("Função de descriptografia indisponível.")
    access = decrypt(bytes(row[4])) if row[4] else None
    refresh = decrypt(bytes(row[5])) if row[5] else None
    return {
        "id": row[0],
        "google_subject": row[1],
        "account_label": row[2],
        "granted_scopes": list(row[3] or []),
        "access_token": access,
        "refresh_token": refresh,
        "token_expires_at": row[6],
    }


def update_tokens(
    conn, *, user_id, tenant_id, connection_id, access_token,
    refresh_token, token_expires_at, encrypt,
):
    access_ciphertext = _ciphertext(encrypt, _required_text(access_token, "access_token"))
    refresh_ciphertext = _ciphertext(encrypt, _required_text(refresh_token, "refresh_token"))
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE external_connections
               SET access_token_ciphertext = %s,
                   refresh_token_ciphertext = %s,
                   token_expires_at = %s,
                   status = 'active',
                   updated_at = NOW()
               WHERE id = %s AND user_id = %s AND tenant_id = %s
                 AND provider = %s AND status IN ('active', 'expired', 'reauthorization_required')
                 AND revoked_at IS NULL
               RETURNING id""",
            (
                access_ciphertext, refresh_ciphertext, token_expires_at,
                connection_id, user_id, tenant_id, PROVIDER,
            ),
        )
        return cur.fetchone() is not None


def revoke_connection(conn, *, user_id, tenant_id, connection_id):
    """Disable future use and erase stored token ciphertext for this owner."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE external_connections
               SET status = 'revoked',
                   access_token_ciphertext = NULL,
                   refresh_token_ciphertext = NULL,
                   revoked_at = NOW(),
                   updated_at = NOW()
               WHERE id = %s AND user_id = %s AND tenant_id = %s
                 AND provider = %s AND revoked_at IS NULL
               RETURNING id""",
            (connection_id, user_id, tenant_id, PROVIDER),
        )
        return cur.fetchone() is not None


def list_connections(conn, *, user_id, tenant_id):
    """Return metadata only; never return token material."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, external_account_id, account_label, granted_scopes,
                      status, token_expires_at, created_at, updated_at
               FROM external_connections
               WHERE user_id = %s AND tenant_id = %s AND provider = %s
               ORDER BY created_at DESC""",
            (user_id, tenant_id, PROVIDER),
        )
        rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "google_subject": row[1],
            "account_label": row[2],
            "granted_scopes": list(row[3] or []),
            "status": row[4],
            "token_expires_at": row[5],
            "created_at": row[6],
            "updated_at": row[7],
        }
        for row in rows
    ]
