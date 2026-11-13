"""Google authorization-code exchange and token revocation adapters.

Network I/O is injected so the OAuth protocol can be tested without contacting
Google. Provider error bodies must never be returned to clients or logged.
"""
from datetime import datetime, timedelta, timezone
import re


TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REVOCATION_URL = "https://oauth2.googleapis.com/revoke"
_SCOPE = "https://www.googleapis.com/auth/drive.file"
_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


class GoogleOAuthExchangeError(RuntimeError):
    """Sanitized OAuth failure; never contains raw provider payloads."""


def exchange_authorization_code(
    *,
    code,
    code_verifier,
    redirect_uri,
    client_id,
    client_secret,
    post_form,
    get_json,
    now=None,
):
    """Exchange a one-use code with PKCE and validate Google account identity."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Authorization code ausente.")
    if not isinstance(code_verifier, str) or not _VERIFIER_RE.fullmatch(code_verifier):
        raise ValueError("PKCE verifier inválido.")
    if not isinstance(redirect_uri, str) or not redirect_uri.startswith("https://"):
        raise ValueError("Redirect URI HTTPS obrigatória.")
    if not isinstance(client_id, str) or not client_id.strip():
        raise ValueError("Client ID Google obrigatório.")
    if not isinstance(client_secret, str) or not client_secret.strip():
        raise ValueError("Client secret Google obrigatório.")
    if not callable(post_form) or not callable(get_json):
        raise ValueError("Adaptadores HTTP indisponíveis.")

    status, token_data = post_form(
        TOKEN_URL,
        {
            "code": code,
            "code_verifier": code_verifier,
            "client_id": client_id.strip(),
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    if status != 200 or not isinstance(token_data, dict):
        raise GoogleOAuthExchangeError("Google não concluiu a troca do authorization code.")

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    token_type = token_data.get("token_type")
    expires_in = token_data.get("expires_in")
    scopes = token_data.get("scope", "").split() if isinstance(token_data.get("scope"), str) else []

    if not isinstance(access_token, str) or not access_token:
        raise GoogleOAuthExchangeError("Google não retornou access token.")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise GoogleOAuthExchangeError("Google não retornou refresh token; autorização offline incompleta.")
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        raise GoogleOAuthExchangeError("Tipo de token Google inesperado.")
    if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in <= 0:
        raise GoogleOAuthExchangeError("Expiração do token Google inválida.")
    from drive_backup_connections import validate_granted_scopes

    try:
        scopes = validate_granted_scopes(scopes)
    except ValueError:
        raise GoogleOAuthExchangeError(
            "Google concedeu permissões fora do escopo mínimo do backup."
        ) from None

    userinfo_status, userinfo = get_json(
        USERINFO_URL,
        {"Authorization": f"Bearer {access_token}"},
    )
    if userinfo_status != 200 or not isinstance(userinfo, dict):
        raise GoogleOAuthExchangeError("Não foi possível validar a conta Google.")
    subject = userinfo.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise GoogleOAuthExchangeError("Google não retornou identificador estável da conta.")
    email = userinfo.get("email")
    if email is not None and not isinstance(email, str):
        email = None

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    return {
        "google_subject": subject,
        "account_label": email,
        "granted_scopes": scopes,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": current_time + timedelta(seconds=expires_in),
    }


def refresh_google_access_token(
    *,
    refresh_token,
    client_id,
    client_secret,
    granted_scopes,
    post_form,
    now=None,
):
    """Refresh an access token while preserving the durable refresh credential."""
    if not isinstance(refresh_token, str) or not refresh_token:
        raise ValueError("Refresh token Google ausente.")
    if not isinstance(client_id, str) or not client_id.strip():
        raise ValueError("Client ID Google obrigatório.")
    if not isinstance(client_secret, str) or not client_secret.strip():
        raise ValueError("Client secret Google obrigatório.")
    if not callable(post_form):
        raise ValueError("Adaptador HTTP indisponível.")

    from drive_backup_connections import validate_granted_scopes

    previous_scopes = validate_granted_scopes(granted_scopes)
    status, token_data = post_form(
        TOKEN_URL,
        {
            "client_id": client_id.strip(),
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    if status != 200 or not isinstance(token_data, dict):
        raise GoogleOAuthExchangeError("Google não renovou a autorização do backup.")

    access_token = token_data.get("access_token")
    token_type = token_data.get("token_type")
    expires_in = token_data.get("expires_in")
    if not isinstance(access_token, str) or not access_token:
        raise GoogleOAuthExchangeError("Google não retornou access token renovado.")
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        raise GoogleOAuthExchangeError("Tipo de token Google inesperado.")
    if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in <= 0:
        raise GoogleOAuthExchangeError("Expiração do token Google inválida.")

    returned_scope = token_data.get("scope")
    scopes = returned_scope.split() if isinstance(returned_scope, str) and returned_scope.strip() else previous_scopes
    try:
        scopes = validate_granted_scopes(scopes)
    except ValueError:
        raise GoogleOAuthExchangeError(
            "Google alterou os escopos concedidos; reautorização necessária."
        ) from None
    rotated_refresh = token_data.get("refresh_token")
    if not isinstance(rotated_refresh, str) or not rotated_refresh:
        rotated_refresh = refresh_token

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    return {
        "access_token": access_token,
        "refresh_token": rotated_refresh,
        "token_expires_at": current_time + timedelta(seconds=expires_in),
        "granted_scopes": scopes,
    }


def revoke_google_token(*, token, post_form):
    """Ask Google to revoke a token; caller must retain local credentials on failure."""
    if not isinstance(token, str) or not token:
        raise ValueError("Token Google ausente.")
    if not callable(post_form):
        raise ValueError("Adaptador HTTP indisponível.")
    status, _ = post_form(REVOCATION_URL, {"token": token})
    return status == 200
