import os
import json
import secrets
import hashlib
import io
import zipfile
import urllib.parse
import urllib.request
import urllib.error

from datetime import datetime, timezone, timedelta

from flask import Flask, jsonify, redirect, request, session
import psycopg
from cryptography.fernet import Fernet


app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("FLASK_ENV", "").lower() == "production"
        or os.environ.get("RENDER", "").lower() == "true"
    ),
    # Limite para upload de ZIP; limites por imagem e conteúdo extraído são validados na rota.
    MAX_CONTENT_LENGTH=80 * 1024 * 1024,
)

DATABASE_URL = os.environ.get("DATABASE_URL")

LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY")

PUBLISH_SECRET = os.environ.get("PUBLISH_SECRET")

LINKEDIN_ACCOUNT_NAME = "LinkedIn Principal"


LINKEDIN_REDIRECT_URI = (
    "https://automacao-murici.onrender.com/linkedin/callback"
)

# No ramo de testes, o retorno OAuth usa o dominio de testes por padrao.
# A URI deve tambem estar cadastrada no cliente OAuth do Google Cloud.
GOOGLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "https://automacao-murici-testes-controlados.onrender.com/google/callback",
)

GOOGLE_OAUTH_SCOPE = os.environ.get(
    "GOOGLE_OAUTH_SCOPE",
    "https://www.googleapis.com/auth/drive "
    "https://www.googleapis.com/auth/spreadsheets "
    "https://www.googleapis.com/auth/gmail.readonly",
).strip()


LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"

LINKEDIN_PUBLISH_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_API_VERSION = os.environ.get("LINKEDIN_API_VERSION", "202608")

LINKEDIN_ANALYTICS_URL = (
    "https://api.linkedin.com/rest/memberCreatorPostAnalytics"
)

LINKEDIN_ANALYTICS_VERSION = os.environ.get(
    "LINKEDIN_ANALYTICS_VERSION",
    "202608",
)

# Coleta automatica desativada por padrao; as metricas serao analisadas a partir de relatorios enviados manualmente.
LINKEDIN_ANALYTICS_AUTOMATIC_ENABLED = (
    os.environ.get("LINKEDIN_ANALYTICS_AUTOMATIC_ENABLED", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)

LINKEDIN_OAUTH_SCOPE = os.environ.get(
    "LINKEDIN_OAUTH_SCOPE",
    "openid profile email w_member_social",
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
GOOGLE_DRIVE_ART_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_ART_FOLDER_ID", "").strip()



SCHEDULER_LOCK_KEY = 83746291


class LinkedInAnalyticsError(RuntimeError):
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload
        super().__init__(
            f"LinkedIn analytics retornou HTTP {status_code}."
        )


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL nao configurado.")

    return psycopg.connect(DATABASE_URL, connect_timeout=10)


def require_session_secret():
    """Evita iniciar fluxos OAuth com sessoes Flask sem chave segura."""
    if not app.secret_key:
        app.logger.error("FLASK_SECRET_KEY nao configurado")
        return jsonify({
            "status": "erro",
            "mensagem": "Configuracao de sessao indisponivel no servidor.",
        }), 500
    return None


def safe_error_response(message="Falha interna. Consulte os logs do servidor.", status=500):
    """Resposta externa sem expor SQL, tokens ou detalhes internos."""
    return jsonify({"status": "erro", "mensagem": message}), status


def get_fernet():
    if not TOKEN_ENCRYPTION_KEY:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY nao configurado.")

    return Fernet(TOKEN_ENCRYPTION_KEY.encode())


def encrypt_value(value):
    if value is None:
        return None

    fernet = get_fernet()
    return fernet.encrypt(value.encode()).decode()


def decrypt_value(value):
    if value is None:
        return None

    fernet = get_fernet()
    return fernet.decrypt(value.encode()).decode()


def ensure_analytics_tables():
    """
    Garante as tabelas atuais de armazenamento das metricas do LinkedIn.
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS linkedin_post_metrics (
                    id BIGSERIAL PRIMARY KEY,

                    editorial_post_id BIGINT
                        REFERENCES editorial_posts(id)
                        ON DELETE SET NULL,

                    linkedin_post_id TEXT NOT NULL,

                    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                    impressions BIGINT,
                    members_reached BIGINT,
                    reactions BIGINT,
                    comments BIGINT,
                    reposts BIGINT,

                    post_saves BIGINT,
                    post_sends BIGINT,
                    link_clicks BIGINT,
                    premium_cta_clicks BIGINT,

                    followers_gained_from_content BIGINT,
                    profile_views_from_content BIGINT,

                    engagement_total BIGINT,

                    source VARCHAR(50) NOT NULL DEFAULT 'linkedin_api',

                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                    CONSTRAINT linkedin_post_metrics_unique_snapshot
                        UNIQUE (linkedin_post_id, measured_at)
                );
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_linkedin_post_metrics_post
                    ON linkedin_post_metrics(linkedin_post_id);
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_linkedin_post_metrics_editorial
                    ON linkedin_post_metrics(editorial_post_id);
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_linkedin_post_metrics_measured_at
                    ON linkedin_post_metrics(measured_at);
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS linkedin_metrics_collection_runs (
                    id BIGSERIAL PRIMARY KEY,

                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMPTZ,

                    status VARCHAR(30) NOT NULL DEFAULT 'started',

                    posts_found INTEGER DEFAULT 0,
                    posts_updated INTEGER DEFAULT 0,
                    metrics_saved INTEGER DEFAULT 0,

                    error_message TEXT,

                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_linkedin_metrics_runs_started
                    ON linkedin_metrics_collection_runs(started_at);
                """
            )

        conn.commit()


def ensure_scheduler_tables():
    """
    Garante a fila de publicacoes automaticas.
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS linkedin_publish_queue (
                    id BIGSERIAL PRIMARY KEY,

                    post_number INTEGER,

                    title TEXT,

                    content TEXT NOT NULL,

                    scheduled_for TIMESTAMPTZ NOT NULL,

                    status VARCHAR(30) NOT NULL DEFAULT 'agendado',

                    attempts INTEGER NOT NULL DEFAULT 0,

                    locked_at TIMESTAMPTZ,

                    published_at TIMESTAMPTZ,

                    linkedin_post_id TEXT,

                    editorial_post_id BIGINT
                        REFERENCES editorial_posts(id)
                        ON DELETE SET NULL,

                    error_message TEXT,

                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_linkedin_publish_queue_due
                ON linkedin_publish_queue(
                    status,
                    scheduled_for
                );
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_linkedin_publish_queue_post_number
                ON linkedin_publish_queue(post_number);
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_linkedin_publish_queue_linkedin_post
                ON linkedin_publish_queue(linkedin_post_id);
                """
            )

            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_linkedin_publish_queue_active_post_number
                ON linkedin_publish_queue(post_number)
                WHERE post_number IS NOT NULL
                  AND status IN (
                      'agendado',
                      'processando',
                      'publicado'
                  );
                """
            )

        conn.commit()


def linkedin_token_from_database():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT access_token
                FROM linkedin_accounts
                WHERE account_name = %s
                LIMIT 1
                """,
                (LINKEDIN_ACCOUNT_NAME,),
            )

            row = cur.fetchone()

            if not row:
                return None

            encrypted_token = row[0]

            if not encrypted_token:
                return None

            return decrypt_value(encrypted_token)


def linkedin_member_id_from_database():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT linkedin_member_id
                FROM linkedin_accounts
                WHERE account_name = %s
                LIMIT 1
                """,
                (LINKEDIN_ACCOUNT_NAME,),
            )

            row = cur.fetchone()

            if not row:
                return None

            return row[0]


def normalize_google_account_name(account_name):
    """Restringe as operacoes do projeto exclusivamente a conta Google Drive5."""
    if account_name is None or not str(account_name).strip():
        return "Drive5"
    normalized = str(account_name).strip()
    if normalized != "Drive5":
        raise ValueError(
            "Esta automacao esta configurada para usar exclusivamente "
            "a conta Drive5."
        )
    return "Drive5"


def google_tokens_from_database(account_name="Drive5"):
    """Recupera tokens criptografados da conta Google informada."""
    account_name = normalize_google_account_name(account_name)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT access_token, refresh_token, token_expires_at
                FROM google_accounts
                WHERE account_name = %s
                LIMIT 1
                """,
                (account_name,),
            )
            row = cur.fetchone()
    if not row:
        return None, None, None
    access_token = decrypt_value(row[0]) if row[0] else None
    refresh_token = decrypt_value(row[1]) if row[1] else None
    return access_token, refresh_token, row[2]


def google_authorized_accounts():
    """Lista somente metadados das contas Google autorizadas."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT account_name, provider, token_expires_at, updated_at
                FROM google_accounts
                ORDER BY account_name;
                """
            )
            rows = cur.fetchall()
    return [
        {
            "account_name": row[0],
            "provider": row[1],
            "token_expires_at": row[2].isoformat() if row[2] else None,
            "updated_at": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    ]


def refresh_google_access_token(account_name="Drive5"):
    """Renova o access token da conta Google informada."""
    account_name = normalize_google_account_name(account_name)
    _, refresh_token, _ = google_tokens_from_database(account_name)
    if not refresh_token:
        raise RuntimeError(f"Refresh token do Google {account_name} nao encontrado no banco.")
    token_payload = urllib.parse.urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    token_request = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=token_payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(token_request, timeout=30) as response:
            token_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = body
        raise RuntimeError(
            "Falha ao renovar o token do Google: "
            f"HTTP {error.code}: {json.dumps(detail)}"
        )
    new_access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in")
    if not new_access_token:
        raise RuntimeError("Google nao retornou um novo access token.")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE google_accounts
                SET access_token = %s,
                    token_expires_at = NOW() + (%s * INTERVAL '1 second'),
                    updated_at = NOW()
                WHERE account_name = %s;
                """,
                (encrypt_value(new_access_token), expires_in or 0, account_name),
            )
        conn.commit()
    return new_access_token


def google_drive_access_token(account_name="Drive5"):
    """Retorna um access token valido e renova quando necessario."""
    account_name = normalize_google_account_name(account_name)
    access_token, refresh_token, token_expires_at = google_tokens_from_database(account_name)
    if not access_token:
        raise RuntimeError(f"Token de acesso do Google {account_name} nao encontrado no banco.")
    if not refresh_token:
        raise RuntimeError(f"Refresh token do Google {account_name} nao encontrado no banco.")
    should_refresh = token_expires_at is None
    if token_expires_at is not None:
        now = datetime.now(timezone.utc)
        expires_at = token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        should_refresh = expires_at <= now + timedelta(minutes=5)
    return refresh_google_access_token(account_name) if should_refresh else access_token


def google_drive_api_request(method, url, data=None, account_name="Drive5"):
    """Faz uma chamada autenticada à Google Drive API v3."""
    account_name = normalize_google_account_name(account_name)
    access_token = google_drive_access_token(account_name)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    status_code, response_data, response_headers = http_json_request(
        url, method=method, headers=headers, data=data
    )
    if status_code not in (200, 201, 202, 204):
        raise RuntimeError(
            "Google Drive recusou a requisicao. "
            f"HTTP {status_code}: {json.dumps(response_data)}"
        )
    return response_data, response_headers


def google_drive_readonly_check(account_name="Drive5"):
    """Valida acesso real à Google Drive API sem criar, alterar ou excluir arquivos."""
    account_name = normalize_google_account_name(account_name)
    query = urllib.parse.urlencode(
        {
            "pageSize": "1",
            "fields": "files(id)",
        }
    )
    response_data, _ = google_drive_api_request(
        "GET", f"{GOOGLE_DRIVE_FILES_URL}?{query}", account_name=account_name
    )
    files = response_data.get("files", [])
    return {
        "status": "ok",
        "mensagem": "Acesso à Google Drive API confirmado para a conta autorizada; este teste não altera arquivos.",
        "conta": account_name,
        "arquivos_acessiveis": len(files),
        "teste": "somente_leitura",
    }

def google_drive_list_art_folder(account_name="Drive5"):
    """Lista metadados dos arquivos da pasta configurada, sem baixar ou alterar arquivos."""
    account_name = normalize_google_account_name(account_name)
    folder_id = GOOGLE_DRIVE_ART_FOLDER_ID
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_ART_FOLDER_ID nao configurado.")

    files = []
    page_token = None
    # Limite de seguranca: no maximo 10 paginas de 100 arquivos.
    for _ in range(10):
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "pageSize": "100",
            "orderBy": "name",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,webViewLink,parents)",
        }
        if page_token:
            params["pageToken"] = page_token
        query = urllib.parse.urlencode(params)
        response_data, _ = google_drive_api_request(
            "GET", f"{GOOGLE_DRIVE_FILES_URL}?{query}", account_name=account_name
        )
        page_files = response_data.get("files", [])
        if isinstance(page_files, list):
            for item in page_files:
                if not isinstance(item, dict):
                    continue
                files.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "mimeType": item.get("mimeType"),
                    "size": item.get("size"),
                    "modifiedTime": item.get("modifiedTime"),
                    "webViewLink": item.get("webViewLink"),
                    "parents": item.get("parents", []),
                })
        page_token = response_data.get("nextPageToken")
        if not page_token:
            break

    return {
        "status": "ok",
        "mensagem": "Metadados listados em modo somente leitura; nenhum arquivo foi baixado ou alterado.",
        "conta": account_name,
        "pasta_id": folder_id,
        "quantidade": len(files),
        "limite_paginas": 10,
        "arquivos": files,
    }


def google_drive_health_check():
    """Verifica exclusivamente Drive5, sem modificar o Google Drive."""
    resultado = {"conta": "Drive5", "status": "erro"}
    try:
        teste = google_drive_readonly_check("Drive5")
        resultado.update({
            "status": "ok",
            "arquivos_acessiveis": teste.get("arquivos_acessiveis", 0),
            "teste": "somente_leitura",
        })
    except Exception:
        app.logger.exception(
            "Falha na verificacao somente leitura do Google Drive para conta=Drive5"
        )
        resultado["mensagem"] = "Falha na verificacao; consulte os logs do servidor."
    return {
        "status": resultado["status"],
        "total_contas": 1,
        "contas_ok": 1 if resultado["status"] == "ok" else 0,
        "contas_com_erro": 0 if resultado["status"] == "ok" else 1,
        "contas": [resultado],
    }


def google_drive_route_account(preferred_account=None):
    """Valida exclusivamente Drive5; nunca tenta usar contas alternativas."""
    if preferred_account:
        normalize_google_account_name(preferred_account)
    google_drive_readonly_check("Drive5")
    return {
        "status": "ok",
        "conta_selecionada": "Drive5",
        "preferida": "Drive5",
        "mensagem": "Drive5 validada em modo somente leitura; nenhuma conta alternativa sera usada.",
    }


def google_drive_test(account_name="Drive5"):
    """Teste seguro de conectividade; não cria nem altera itens no Drive."""
    account_name = normalize_google_account_name(account_name)
    return google_drive_readonly_check(account_name)


def http_json_request(
    url,
    method="GET",
    headers=None,
    data=None,
):
    if headers is None:
        headers = {}

    request_data = None

    if data is not None:
        request_data = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=request_data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")

            if not body:
                return response.status, {}, response.headers

            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"raw": body}

            return response.status, payload, response.headers

    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8")

        try:
            payload = json.loads(error_body)
        except json.JSONDecodeError:
            payload = {"raw": error_body}

        return error.code, payload, error.headers

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Erro de comunicacao externa: {error.reason}"
        )


def publish_linkedin_text(commentary):
    """
    Publica um post de texto no perfil pessoal autorizado.
    """

    access_token = linkedin_token_from_database()
    member_id = linkedin_member_id_from_database()

    if not access_token:
        raise RuntimeError(
            "Token do LinkedIn nao encontrado no banco."
        )

    if not member_id:
        raise RuntimeError(
            "LinkedIn Member ID nao encontrado no banco."
        )

    author_urn = f"urn:li:person:{member_id}"

    payload = {
        "author": author_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Linkedin-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }

    status_code, response_data, response_headers = http_json_request(
        LINKEDIN_PUBLISH_URL,
        method="POST",
        headers=headers,
        data=payload,
    )

    if status_code not in (200, 201, 202, 204):
        raise RuntimeError(
            f"LinkedIn recusou a publicacao. "
            f"HTTP {status_code}: {json.dumps(response_data)}"
        )

    post_id = response_headers.get("x-restli-id")

    if not post_id and isinstance(response_data, dict):
        post_id = response_data.get("id")

    if not post_id:
        raise RuntimeError(
            "LinkedIn publicou, mas nao retornou o ID da publicacao."
        )

    return post_id


def analytics_metric_type(element):
    metric_type = element.get("metricType")

    if isinstance(metric_type, str):
        return metric_type

    if isinstance(metric_type, dict):
        for value in metric_type.values():
            if isinstance(value, str):
                return value

    return None


def analytics_count(element):
    value = element.get("count")

    if value is None:
        value = element.get("value")

    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value if value >= 0 else None

    if isinstance(value, float):
        return int(value) if value >= 0 else None

    if isinstance(value, str):
        try:
            parsed = int(value)
            return parsed if parsed >= 0 else None
        except ValueError:
            return None

    return None


def linkedin_post_analytics(post_id):
    """
    Consulta as metricas oficiais de uma publicacao especifica.

    A API do LinkedIn exige o tipo de URN correto no finder `entity`:
    `ugc` para urn:li:ugcPost e `share` para urn:li:share.
    """

    if not isinstance(post_id, str):
        raise ValueError("linkedin_post_id deve ser uma URN do LinkedIn.")
    if post_id.startswith("urn:li:ugcPost:"):
        entity_type = "ugc"
    elif post_id.startswith("urn:li:share:"):
        entity_type = "share"
    else:
        raise ValueError(
            "Tipo de linkedin_post_id nao reconhecido; esperado urn:li:ugcPost ou urn:li:share."
        )

    access_token = linkedin_token_from_database()

    if not access_token:
        raise RuntimeError(
            "Token do LinkedIn nao encontrado no banco."
        )

    metric_types = [
        "IMPRESSION",
        "MEMBERS_REACHED",
        "RESHARE",
        "REACTION",
        "COMMENT",
        "POST_SAVE",
        "POST_SEND",
        "LINK_CLICKS",
        "PREMIUM_CTA_CLICKS",
        "FOLLOWER_GAINED_FROM_CONTENT",
        "PROFILE_VIEW_FROM_CONTENT",
    ]

    encoded_urn = urllib.parse.quote(post_id, safe="")
    entity_filter = f"({entity_type}:{encoded_urn})"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Linkedin-Version": LINKEDIN_ANALYTICS_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }

    metrics = {}
    raw_elements = []

    for metric_type in metric_types:
        url = (
            f"{LINKEDIN_ANALYTICS_URL}"
            f"?q=entity"
            f"&entity={entity_filter}"
            f"&queryType={urllib.parse.quote(metric_type, safe='')}"
            f"&aggregation=TOTAL"
        )

        status_code, response_data, _ = http_json_request(
            url,
            method="GET",
            headers=headers,
        )

        if status_code != 200:
            raise LinkedInAnalyticsError(
                status_code,
                response_data,
            )

        elements = response_data.get("elements", [])

        if not isinstance(elements, list):
            elements = []

        for element in elements:
            if not isinstance(element, dict):
                continue

            detected_metric = analytics_metric_type(element)
            count = analytics_count(element)

            if detected_metric and count is not None:
                metrics[detected_metric] = count

            raw_elements.append(element)

    return metrics, {"elements": raw_elements}


def calculate_engagement_total(metrics):
    engagement_fields = [
        "REACTION",
        "COMMENT",
        "RESHARE",
        "POST_SAVE",
        "POST_SEND",
        "LINK_CLICKS",
        "PREMIUM_CTA_CLICKS",
    ]

    return sum(
        int(metrics.get(field, 0) or 0)
        for field in engagement_fields
    )


def require_publish_secret():
    if not PUBLISH_SECRET:
        return (
            jsonify(
                {
                    "status": "erro",
                    "mensagem": "PUBLISH_SECRET nao configurado.",
                }
            ),
            503,
        )

    provided_secret = request.headers.get("X-Publish-Secret")

    if not provided_secret:
        return (
            jsonify(
                {
                    "status": "erro",
                    "mensagem": "Chave de publicacao nao informada.",
                }
            ),
            401,
        )

    if not secrets.compare_digest(provided_secret, PUBLISH_SECRET):
        return (
            jsonify(
                {
                    "status": "erro",
                    "mensagem": "Chave de publicacao invalida.",
                }
            ),
            403,
        )

    return None


def parse_scheduled_for(value):
    """
    Converte uma data ISO 8601 em datetime com timezone.

    A fila exige timezone explicito para evitar erro entre
    horario do Brasil e UTC.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "scheduled_for e obrigatorio e deve ser uma data ISO 8601."
        )

    normalized = value.strip()

    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError(
            "scheduled_for invalido. Use ISO 8601, por exemplo "
            "2026-10-10T14:30:00-03:00."
        )

    if parsed.tzinfo is None:
        raise ValueError(
            "scheduled_for precisa informar o timezone."
        )

    return parsed.astimezone(timezone.utc)


def scheduler_publish_one():
    """
    Localiza e processa no maximo uma publicacao vencida.

    Mantem uma conexao dedicada aberta durante toda a operacao para que
    o advisory lock continue ativo enquanto a chamada ao LinkedIn ocorre.
    """
    ensure_scheduler_tables()

    lock_conn = get_db_connection()
    lock_acquired = False

    try:
        with lock_conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_lock(%s);",
                (SCHEDULER_LOCK_KEY,),
            )
            lock_row = cur.fetchone()
            lock_acquired = bool(lock_row and lock_row[0])

        if not lock_acquired:
            return {
                "status": "busy",
                "mensagem": "Outra execucao do scheduler ja esta em andamento.",
            }

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        post_number,
                        title,
                        content,
                        scheduled_for,
                        attempts
                    FROM linkedin_publish_queue
                    WHERE status = 'agendado'
                      AND scheduled_for <= NOW()
                    ORDER BY scheduled_for ASC, id ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED;
                    """
                )
                row = cur.fetchone()

                if not row:
                    return {
                        "status": "idle",
                        "mensagem": "Nenhuma publicacao vencida na fila.",
                    }

                (
                    queue_id,
                    post_number,
                    title,
                    content,
                    scheduled_for,
                    attempts,
                ) = row

                cur.execute(
                    """
                    UPDATE linkedin_publish_queue
                    SET
                        status = 'processando',
                        attempts = attempts + 1,
                        locked_at = NOW(),
                        updated_at = NOW(),
                        error_message = NULL
                    WHERE id = %s;
                    """,
                    (queue_id,),
                )
            conn.commit()

        try:
            post_id = publish_linkedin_text(content)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO editorial_posts (
                            post_number,
                            title,
                            content,
                            status,
                            published_at,
                            linkedin_post_id,
                            updated_at
                        )
                        VALUES (%s, %s, %s, %s, NOW(), %s, NOW())
                        RETURNING id;
                        """,
                        (post_number, title, content, "publicado", post_id),
                    )
                    editorial_post_id = cur.fetchone()[0]

                    cur.execute(
                        """
                        UPDATE linkedin_publish_queue
                        SET
                            status = 'publicado',
                            published_at = NOW(),
                            linkedin_post_id = %s,
                            editorial_post_id = %s,
                            updated_at = NOW(),
                            locked_at = NULL,
                            error_message = NULL
                        WHERE id = %s;
                        """,
                        (post_id, editorial_post_id, queue_id),
                    )
                conn.commit()

            return {
                "status": "publicado",
                "mensagem": "Publicacao da fila realizada no LinkedIn.",
                "queue_id": queue_id,
                "post_number": post_number,
                "linkedin_post_id": post_id,
                "editorial_post_id": editorial_post_id,
            }

        except Exception as error:
            app.logger.exception(
                "Falha no processamento da fila id=%s, post_number=%s; "
                "post_id_retornado=%s",
                queue_id,
                post_number,
                bool(locals().get("post_id")),
            )
            # If LinkedIn returned an ID, publication may already exist even if
            # the local DB write failed. Keep the row out of automatic retries.
            if locals().get("post_id"):
                safe_message = (
                    "O LinkedIn pode ter recebido a publicacao, mas o registro local falhou. "
                    "Confira a publicacao no LinkedIn antes de qualquer nova tentativa."
                )
                stored_error = (
                    "RECONCILIACAO MANUAL NECESSARIA: LinkedIn retornou um identificador, "
                    "mas o processamento local falhou. Consulte os logs do servidor."
                )
            else:
                safe_message = (
                    "A publicacao falhou e nao sera repetida automaticamente. "
                    "Consulte os logs para identificar a causa."
                )
                stored_error = (
                    "Falha antes da confirmacao da publicacao no LinkedIn. "
                    "Consulte os logs do servidor para detalhes."
                )
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE linkedin_publish_queue
                            SET
                                status = 'erro',
                                error_message = %s,
                                updated_at = NOW(),
                                locked_at = NULL
                            WHERE id = %s;
                            """,
                            (stored_error, queue_id),
                        )
                    conn.commit()
            except Exception:
                app.logger.exception(
                    "Tambem falhou a gravacao do erro na fila id=%s", queue_id
                )

            return {
                "status": "erro",
                "mensagem": safe_message,
                "queue_id": queue_id,
                "post_number": post_number,
                "reconciliacao_manual": bool(locals().get("post_id")),
            }

    finally:
        if lock_acquired:
            try:
                with lock_conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s);", (SCHEDULER_LOCK_KEY,))
            except Exception:
                app.logger.exception("Falha ao liberar bloqueio do scheduler")
        lock_conn.close()


@app.get("/")
def home():
    return jsonify(
        {
            "projeto": "Automacao Murici",
            "status": "online"
        }
    )


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ok"
        }
    )


@app.get("/db-test")
def db_test():
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT NOW();")
                result = cur.fetchone()

        return jsonify(
            {
                "status": "ok",
                "mensagem": "Conexao com PostgreSQL funcionando.",
                "servidor": str(result[0]),
            }
        )

    except Exception:
        app.logger.exception("Falha no teste de conexao com PostgreSQL")
        return safe_error_response("Falha na conexao com PostgreSQL. Consulte os logs do servidor.")


@app.get("/crypto-test")
def crypto_test():
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error

    try:
        original = "automacao-murici-teste"

        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)

        if decrypted != original:
            raise RuntimeError(
                "Falha na validacao da criptografia."
            )

        return jsonify(
            {
                "status": "ok",
                "mensagem": "Criptografia funcionando corretamente.",
            }
        )

    except Exception:
        app.logger.exception("Falha no teste de criptografia")
        return safe_error_response("Falha no teste de criptografia. Consulte os logs do servidor.")


@app.get("/google-drive/accounts")
def google_drive_accounts_route():
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    try:
        return jsonify({"status": "ok", "contas": google_authorized_accounts()})
    except Exception:
        app.logger.exception("Falha na rota /google-drive/accounts")
        return jsonify({"status": "erro", "mensagem": "Falha interna. Consulte os logs do servidor."}), 500


@app.get("/google-drive/check")
def google_drive_check_route():
    """Verifica acesso ao Drive; pode renovar tokens armazenados no banco."""
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    try:
        account_name = normalize_google_account_name(request.args.get("account", "Drive5"))
        return jsonify(google_drive_readonly_check(account_name))
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400
    except Exception:
        app.logger.exception("Falha na rota /google-drive/check")
        return jsonify({"status": "erro", "mensagem": "Falha interna. Consulte os logs do servidor."}), 500

@app.get("/google-drive/art-folder")
def google_drive_art_folder_route():
    """Lista os metadados dos arquivos da pasta de artes configurada."""
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    try:
        account_name = normalize_google_account_name(request.args.get("account", "Drive5"))
        return jsonify(google_drive_list_art_folder(account_name))
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400
    except Exception:
        app.logger.exception("Falha na rota /google-drive/art-folder")
        return jsonify({"status": "erro", "mensagem": "Falha interna. Consulte os logs do servidor."}), 500


def google_drive_list_existing_art_files(account_name="Drive5"):
    """Lista metadados dos arquivos existentes na pasta de artes, sem baixá-los."""
    account_name = normalize_google_account_name(account_name)
    folder_id = GOOGLE_DRIVE_ART_FOLDER_ID
    if not folder_id:
        raise RuntimeError("GOOGLE_DRIVE_ART_FOLDER_ID nao configurado.")

    files = []
    page_token = None
    for _ in range(10):
        params = {
            "q": f"'{folder_id}' in parents and trashed = false",
            "pageSize": "100",
            "orderBy": "name",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "fields": "nextPageToken,files(id,name,mimeType,size,md5Checksum,appProperties)",
        }
        if page_token:
            params["pageToken"] = page_token
        response_data, _ = google_drive_api_request(
            "GET",
            f"{GOOGLE_DRIVE_FILES_URL}?{urllib.parse.urlencode(params)}",
            account_name=account_name,
        )
        files.extend(
            item for item in response_data.get("files", [])
            if isinstance(item, dict)
        )
        page_token = response_data.get("nextPageToken")
        if not page_token:
            break
    return files


def google_drive_upload_art_bytes(name, content, mime_type, sha256_hex, account_name="Drive5"):
    """Envia uma imagem ao Drive e registra seu SHA-256 em appProperties."""
    account_name = normalize_google_account_name(account_name)
    if not GOOGLE_DRIVE_ART_FOLDER_ID:
        raise RuntimeError("GOOGLE_DRIVE_ART_FOLDER_ID nao configurado.")
    token = google_drive_access_token(account_name)
    boundary = "murici_drive_upload_" + secrets.token_hex(16)
    metadata = {
        "name": name,
        "mimeType": mime_type,
        "parents": [GOOGLE_DRIVE_ART_FOLDER_ID],
        "appProperties": {"sha256": sha256_hex},
    }
    query = urllib.parse.urlencode({
        "uploadType": "multipart",
        "supportsAllDrives": "true",
        "fields": "id,name,mimeType,size,md5Checksum,webViewLink,parents,appProperties",
    })
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        + json.dumps(metadata, ensure_ascii=False)
        + f"\r\n--{boundary}\r\n"
        + f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"https://www.googleapis.com/upload/drive/v3/files?{query}",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        app.logger.error(
            "Google Drive upload falhou: HTTP %s; arquivo=%s; detalhe=%s",
            error.code, name, detail[:1000],
        )
        raise RuntimeError(f"Google Drive recusou o envio (HTTP {error.code}).") from None
    if not payload.get("id"):
        raise RuntimeError("Google Drive nao confirmou o arquivo enviado.")
    return payload


@app.post("/google-drive/upload-art-zip")
def google_drive_upload_art_zip_route():
    """Recebe um ZIP e envia imagens para a pasta configurada, sem sobrescrever."""
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error

    try:
        account_name = normalize_google_account_name(
            request.args.get("account", "Drive5")
        )
        if account_name != "Drive5":
            return jsonify({
                "status": "erro",
                "mensagem": "Este endpoint aceita exclusivamente a conta Drive5.",
            }), 400
        if not GOOGLE_DRIVE_ART_FOLDER_ID:
            raise RuntimeError("GOOGLE_DRIVE_ART_FOLDER_ID nao configurado.")

        uploaded_file = request.files.get("archive") or request.files.get("file")
        if not uploaded_file or not uploaded_file.filename:
            return jsonify({
                "status": "erro",
                "mensagem": "Envie um arquivo ZIP no campo multipart 'archive'.",
            }), 400
        if not uploaded_file.filename.lower().endswith(".zip"):
            return jsonify({"status": "erro", "mensagem": "O arquivo deve ser ZIP."}), 400

        archive_bytes = uploaded_file.read()
        if not archive_bytes:
            return jsonify({"status": "erro", "mensagem": "O ZIP está vazio."}), 400
        if len(archive_bytes) > 80 * 1024 * 1024:
            return jsonify({"status": "erro", "mensagem": "ZIP excede o limite de 80 MiB."}), 413

        allowed_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        candidates = []
        total_uncompressed = 0
        seen_hashes = set()
        seen_names = set()
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                entries = [entry for entry in archive.infolist() if not entry.is_dir()]
                # Detecta nomes repetidos antes de processar os arquivos para
                # que nenhum dos lados de um conflito seja enviado por engano.
                from collections import Counter
                basename_counts = Counter(
                    entry.filename.replace("\\", "/").rsplit("/", 1)[-1]
                    for entry in entries
                    if entry.filename.replace("\\", "/").rsplit("/", 1)[-1]
                    and "__MACOSX" not in entry.filename.replace("\\", "/").split("/")
                )
                conflicting_basenames = {
                    name for name, count in basename_counts.items() if count > 1
                }
                if len(entries) > 500:
                    return jsonify({
                        "status": "erro",
                        "mensagem": "O ZIP contém mais de 500 entradas; nenhum arquivo foi enviado.",
                    }), 400
                for entry in entries:
                    raw_name = entry.filename.replace("\\", "/")
                    basename = raw_name.rsplit("/", 1)[-1]
                    if not basename or basename in {".", ".."} or "__MACOSX" in raw_name.split("/"):
                        continue
                    extension = "." + basename.rsplit(".", 1)[-1].lower() if "." in basename else ""
                    mime_type = allowed_types.get(extension)
                    if not mime_type:
                        continue
                    if entry.flag_bits & 0x1:
                        return jsonify({
                            "status": "erro",
                            "mensagem": "ZIP criptografado não é aceito; nenhum arquivo foi enviado.",
                        }), 400
                    if entry.file_size <= 0 or entry.file_size > 20 * 1024 * 1024:
                        return jsonify({
                            "status": "erro",
                            "mensagem": f"Imagem fora do limite permitido: {basename}.",
                        }), 400
                    total_uncompressed += entry.file_size
                    if total_uncompressed > 300 * 1024 * 1024:
                        return jsonify({
                            "status": "erro",
                            "mensagem": "Conteúdo descompactado excede 300 MiB; nenhum arquivo foi enviado.",
                        }), 400
                    content = archive.read(entry)
                    digest = hashlib.sha256(content).hexdigest()
                    if digest in seen_hashes:
                        continue
                    seen_hashes.add(digest)
                    if basename in seen_names:
                        continue
                    seen_names.add(basename)
                    candidates.append({
                        "name": basename,
                        "content": content,
                        "mime_type": mime_type,
                        "sha256": digest,
                        "size": len(content),
                        "zip_name_conflict": basename in conflicting_basenames,
                    })
        except (zipfile.BadZipFile, RuntimeError) as error:
            app.logger.info("ZIP de artes inválido: %s", str(error)[:300])
            return jsonify({"status": "erro", "mensagem": "ZIP inválido ou corrompido."}), 400

        if not candidates:
            return jsonify({
                "status": "erro",
                "mensagem": "Nenhuma imagem PNG, JPG, JPEG, WEBP ou GIF foi encontrada.",
            }), 400

        existing = google_drive_list_existing_art_files("Drive5")
        by_hash = {
            item.get("appProperties", {}).get("sha256"): item
            for item in existing
            if isinstance(item.get("appProperties"), dict)
            and item.get("appProperties", {}).get("sha256")
        }
        by_name = {}
        for item in existing:
            by_name.setdefault(item.get("name"), []).append(item)

        result = {
            "status": "ok",
            "conta": "Drive5",
            "pasta_id": GOOGLE_DRIVE_ART_FOLDER_ID,
            "recebidas_no_zip": len(candidates),
            "enviadas": [],
            "ignoradas_duplicadas": [],
            "ignoradas_conflito_nome": [],
            "erros": [],
            "nota": "Arquivos existentes nunca são sobrescritos; conflitos de nome exigem revisão.",
        }
        for item in candidates:
            if item["sha256"] in by_hash:
                result["ignoradas_duplicadas"].append({
                    "nome": item["name"],
                    "motivo": "SHA-256 já registrado no Drive5",
                })
                continue
            if item["zip_name_conflict"] or item["name"] in by_name:
                result["ignoradas_conflito_nome"].append({
                    "nome": item["name"],
                    "motivo": "Nome repetido no ZIP ou já existente no Drive; não foi sobrescrito",
                })
                continue
            try:
                uploaded = google_drive_upload_art_bytes(
                    item["name"], item["content"], item["mime_type"],
                    item["sha256"], "Drive5",
                )
                result["enviadas"].append({
                    "nome": uploaded.get("name", item["name"]),
                    "id": uploaded.get("id"),
                    "tamanho": uploaded.get("size", item["size"]),
                    "sha256": item["sha256"],
                    "link": uploaded.get("webViewLink"),
                })
                by_hash[item["sha256"]] = uploaded
                by_name.setdefault(item["name"], []).append(uploaded)
            except Exception as error:
                app.logger.exception("Falha ao enviar arte para Drive5: %s", item["name"])
                result["erros"].append({
                    "nome": item["name"],
                    "mensagem": str(error)[:250],
                })

        if result["erros"]:
            result["status"] = "parcial" if result["enviadas"] else "erro"
            return jsonify(result), 207 if result["enviadas"] else 502
        return jsonify(result), 200
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400
    except Exception:
        app.logger.exception("Falha na rota /google-drive/upload-art-zip")
        return jsonify({
            "status": "erro",
            "mensagem": "Falha interna no envio. Consulte os logs do servidor.",
        }), 500


def google_drive_get_file_metadata(file_id, account_name="Drive5"):
    """Busca metadados de um item pelo ID, sem baixar seu conteúdo."""
    if not file_id or "/" in file_id:
        raise ValueError("ID de arquivo/pasta inválido.")
    params = {"fields": "id,name,mimeType,parents,trashed,md5Checksum,size,modifiedTime,webViewLink"}
    url = f"{GOOGLE_DRIVE_FILES_URL}/{urllib.parse.quote(file_id, safe='')}?{urllib.parse.urlencode(params)}"
    result, _ = google_drive_api_request("GET", url, account_name=account_name)
    return result


def google_drive_list_files(parent_id=None, account_name="Drive5", page_size=100, return_meta=False):
    """Lista metadados; opcionalmente informa se o limite de páginas foi atingido."""
    account_name = normalize_google_account_name(account_name)
    page_size = max(1, min(int(page_size), 100))
    items, page_token = [], None
    for _ in range(20):
        params = {
            "pageSize": str(page_size),
            "orderBy": "name",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
            "fields": "nextPageToken,files(id,name,mimeType,parents,trashed,md5Checksum,size,modifiedTime,webViewLink)",
            "q": "trashed = false" + (f" and '{parent_id}' in parents" if parent_id else ""),
        }
        if page_token:
            params["pageToken"] = page_token
        payload, _ = google_drive_api_request(
            "GET", f"{GOOGLE_DRIVE_FILES_URL}?{urllib.parse.urlencode(params)}", account_name=account_name
        )
        items.extend(x for x in payload.get("files", []) if isinstance(x, dict))
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    result = {"arquivos": items, "truncated": bool(page_token), "next_page_token": page_token}
    return result if return_meta else items


def google_drive_create_folder(name, parent_id=None, account_name="Drive5"):
    name = str(name or "").strip()
    if not name or len(name) > 200 or name in {".", ".."}:
        raise ValueError("Informe um nome de pasta válido (1 a 200 caracteres).")
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        parent = google_drive_get_file_metadata(parent_id, account_name)
        if parent.get("mimeType") != "application/vnd.google-apps.folder" or parent.get("trashed"):
            raise ValueError("A pasta de destino não existe ou não está disponível.")
        metadata["parents"] = [parent_id]
    payload, _ = google_drive_api_request("POST", GOOGLE_DRIVE_FILES_URL, data=metadata, account_name=account_name)
    return payload


def google_drive_rename_file(file_id, new_name, account_name="Drive5"):
    new_name = str(new_name or "").strip()
    if not new_name or len(new_name) > 200 or new_name in {".", ".."}:
        raise ValueError("Informe um nome válido (1 a 200 caracteres).")
    google_drive_get_file_metadata(file_id, account_name)
    url = f"{GOOGLE_DRIVE_FILES_URL}/{urllib.parse.quote(file_id, safe='')}?fields=id,name,mimeType,parents,webViewLink"
    payload, _ = google_drive_api_request("PATCH", url, data={"name": new_name}, account_name=account_name)
    return payload


def google_drive_move_file(file_id, destination_folder_id, account_name="Drive5"):
    source = google_drive_get_file_metadata(file_id, account_name)
    destination = google_drive_get_file_metadata(destination_folder_id, account_name)
    if source.get("trashed"):
        raise ValueError("O item de origem está na lixeira.")
    if destination.get("mimeType") != "application/vnd.google-apps.folder" or destination.get("trashed"):
        raise ValueError("A pasta de destino não é válida.")
    if source.get("mimeType") == "application/vnd.google-apps.folder":
        source_id = source.get("id")
        current_id = destination.get("id")
        visited = set()
        # Percorre os ancestrais do destino para impedir ciclos de pastas.
        while current_id:
            if current_id == source_id:
                raise ValueError("Uma pasta não pode ser movida para dentro de si mesma ou de uma pasta descendente.")
            if current_id in visited:
                raise ValueError("A hierarquia de pastas retornada pelo Drive contém um ciclo; operação cancelada.")
            visited.add(current_id)
            current = google_drive_get_file_metadata(current_id, account_name)
            parents = current.get("parents", [])
            current_id = parents[0] if parents else None
    old_parents = source.get("parents", [])
    params = {"addParents": destination_folder_id, "fields": "id,name,mimeType,parents,webViewLink"}
    if old_parents:
        params["removeParents"] = ",".join(old_parents)
    url = f"{GOOGLE_DRIVE_FILES_URL}/{urllib.parse.quote(file_id, safe='')}?{urllib.parse.urlencode(params)}"
    payload, _ = google_drive_api_request("PATCH", url, data={}, account_name=account_name)
    return payload


def google_drive_trash_file(file_id, confirmation, account_name="Drive5"):
    """Move para a lixeira; exige confirmação literal e não exclui permanentemente."""
    if confirmation != f"TRASH FILE {file_id}":
        raise ValueError("Confirmação inválida. Envie exatamente: TRASH FILE <ID>.")
    metadata = google_drive_get_file_metadata(file_id, account_name)
    if metadata.get("trashed"):
        return {"status": "ok", "mensagem": "O item já está na lixeira.", "id": file_id}
    url = f"{GOOGLE_DRIVE_FILES_URL}/{urllib.parse.quote(file_id, safe='')}?fields=id,name,trashed"
    payload, _ = google_drive_api_request("PATCH", url, data={"trashed": True}, account_name=account_name)
    return {"status": "ok", "mensagem": "Item movido para a lixeira; não houve exclusão permanente.", **payload}


def google_drive_find_duplicates(parent_id=None, account_name="Drive5"):
    """Detecta duplicatas prováveis por checksum MD5; não altera nem exclui itens."""
    listing = google_drive_list_files(parent_id, account_name, return_meta=True)
    items = listing["arquivos"]
    groups = {}
    for item in items:
        if item.get("mimeType") == "application/vnd.google-apps.folder":
            continue
        checksum = item.get("md5Checksum")
        size = item.get("size")
        if checksum and size is not None:
            groups.setdefault((checksum, str(size)), []).append({
                "id": item.get("id"), "name": item.get("name"),
                "size": size, "modifiedTime": item.get("modifiedTime"),
                "webViewLink": item.get("webViewLink"),
            })
    duplicates = [group for group in groups.values() if len(group) > 1]
    return {"status": "parcial" if listing["truncated"] else "ok", "modo": "somente_leitura", "itens_analisados": len(items),
            "truncated": listing["truncated"], "next_page_token": listing["next_page_token"],
            "grupos_duplicados": len(duplicates), "duplicatas": duplicates,
            "nota": "Nenhum item foi alterado. Revise cada grupo antes de enviar um ID à rota de lixeira." if not listing["truncated"] else "Atingido o limite de 20 páginas; resultados incompletos. Refine a pasta ou implemente paginação antes de concluir a auditoria."}


@app.get("/google-drive/files")
def google_drive_files_route():
    auth_error = require_publish_secret()
    if auth_error: return auth_error
    try:
        parent_id = request.args.get("folder_id") or None
        listing = google_drive_list_files(parent_id, "Drive5", return_meta=True)
        return jsonify({"status": "parcial" if listing["truncated"] else "ok", "conta": "Drive5", "quantidade": len(listing["arquivos"]), "truncated": listing["truncated"], "next_page_token": listing["next_page_token"], "arquivos": listing["arquivos"]})
    except Exception:
        app.logger.exception("Falha ao listar itens do Google Drive")
        return jsonify({"status": "erro", "mensagem": "Falha ao listar itens. Consulte os logs."}), 500


@app.post("/google-drive/folders")
def google_drive_create_folder_route():
    auth_error = require_publish_secret()
    if auth_error: return auth_error
    try:
        body = request.get_json(silent=True) or {}
        payload = google_drive_create_folder(body.get("name"), body.get("parent_id"), "Drive5")
        return jsonify({"status": "ok", "pasta": payload}), 201
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400
    except Exception:
        app.logger.exception("Falha ao criar pasta no Google Drive")
        return jsonify({"status": "erro", "mensagem": "Falha ao criar pasta. Consulte os logs."}), 500


@app.patch("/google-drive/files/<file_id>")
def google_drive_update_file_route(file_id):
    auth_error = require_publish_secret()
    if auth_error: return auth_error
    try:
        body = request.get_json(silent=True) or {}
        has_name, has_parent = "name" in body, "parent_id" in body
        if has_name == has_parent:
            return jsonify({"status": "erro", "mensagem": "Informe somente 'name' para renomear ou 'parent_id' para mover."}), 400
        payload = google_drive_rename_file(file_id, body.get("name"), "Drive5") if has_name else google_drive_move_file(file_id, body.get("parent_id"), "Drive5")
        return jsonify({"status": "ok", "arquivo": payload})
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400
    except Exception:
        app.logger.exception("Falha ao atualizar item no Google Drive")
        return jsonify({"status": "erro", "mensagem": "Falha ao atualizar item. Consulte os logs."}), 500


@app.post("/google-drive/upload")
def google_drive_upload_file_route():
    """Upload genérico de um arquivo para uma pasta do Drive; máximo de 20 MiB."""
    auth_error = require_publish_secret()
    if auth_error: return auth_error
    try:
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return jsonify({"status": "erro", "mensagem": "Envie o arquivo no campo multipart 'file'."}), 400
        filename = uploaded.filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not filename or filename in {".", ".."} or len(filename) > 200:
            return jsonify({"status": "erro", "mensagem": "Nome de arquivo inválido."}), 400
        content = uploaded.read(20 * 1024 * 1024 + 1)
        if not content:
            return jsonify({"status": "erro", "mensagem": "O arquivo está vazio."}), 400
        if len(content) > 20 * 1024 * 1024:
            return jsonify({"status": "erro", "mensagem": "O arquivo excede o limite de 20 MiB."}), 413
        parent_id = (request.form.get("folder_id") or "").strip()
        if parent_id:
            parent = google_drive_get_file_metadata(parent_id, "Drive5")
            if parent.get("mimeType") != "application/vnd.google-apps.folder" or parent.get("trashed"):
                return jsonify({"status": "erro", "mensagem": "Pasta de destino inválida."}), 400
        mime_type = uploaded.mimetype or "application/octet-stream"
        boundary = "murici_upload_" + secrets.token_hex(16)
        metadata = {"name": filename}
        if parent_id: metadata["parents"] = [parent_id]
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                + json.dumps(metadata, ensure_ascii=False)
                + f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n").encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
        query = urllib.parse.urlencode({"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id,name,mimeType,size,md5Checksum,webViewLink,parents"})
        req = urllib.request.Request(
            f"https://www.googleapis.com/upload/drive/v3/files?{query}", data=body,
            headers={"Authorization": f"Bearer {google_drive_access_token('Drive5')}",
                     "Content-Type": f"multipart/related; boundary={boundary}"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            app.logger.error("Google Drive upload genérico falhou: HTTP %s", error.code)
            return jsonify({"status": "erro", "mensagem": f"Google Drive recusou o upload (HTTP {error.code})."}), 502
        if not payload.get("id"):
            return jsonify({"status": "erro", "mensagem": "O Drive não confirmou o arquivo enviado."}), 502
        return jsonify({"status": "ok", "arquivo": payload}), 201
    except Exception:
        app.logger.exception("Falha no upload genérico do Google Drive")
        return jsonify({"status": "erro", "mensagem": "Falha no upload. Consulte os logs."}), 500


@app.get("/google-drive/duplicates")
def google_drive_duplicates_route():
    auth_error = require_publish_secret()
    if auth_error: return auth_error
    try:
        return jsonify(google_drive_find_duplicates(request.args.get("folder_id") or None, "Drive5"))
    except Exception:
        app.logger.exception("Falha ao identificar duplicatas no Google Drive")
        return jsonify({"status": "erro", "mensagem": "Falha ao identificar duplicatas. Consulte os logs."}), 500


@app.post("/google-drive/files/<file_id>/trash")
def google_drive_trash_file_route(file_id):
    auth_error = require_publish_secret()
    if auth_error: return auth_error
    try:
        body = request.get_json(silent=True) or {}
        result = google_drive_trash_file(file_id, body.get("confirmation"), "Drive5")
        return jsonify(result)
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400
    except Exception:
        app.logger.exception("Falha ao mover item para lixeira do Google Drive")
        return jsonify({"status": "erro", "mensagem": "Falha ao mover item para lixeira. Consulte os logs."}), 500


@app.post("/google-drive/test")
def google_drive_test_route():
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    try:
        account_name = normalize_google_account_name(request.args.get("account", "Drive5"))
        return jsonify(google_drive_test(account_name))
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400
    except Exception:
        app.logger.exception("Falha na rota /google-drive/test")
        return jsonify({"status": "erro", "mensagem": "Falha interna. Consulte os logs do servidor."}), 500

@app.get("/google-drive/health")
def google_drive_health_route():
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    try:
        return jsonify(google_drive_health_check())
    except Exception:
        app.logger.exception("Falha na rota /google-drive/health")
        return jsonify({"status": "erro", "mensagem": "Falha interna. Consulte os logs do servidor."}), 500


@app.get("/google-drive/router")
def google_drive_router_route():
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    try:
        preferred = request.args.get("account")
        return jsonify(google_drive_route_account(preferred))
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400
    except Exception:
        app.logger.exception("Falha na rota /google-drive/router")
        return jsonify({"status": "erro", "mensagem": "Falha interna. Consulte os logs do servidor."}), 500


@app.post("/storage-test")
def storage_test():
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error

    try:
        test_value = "teste-storage-automacao-murici"
        encrypted_value = encrypt_value(test_value)

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO security_test (
                        encrypted_value
                    )
                    VALUES (%s)
                    RETURNING id;
                    """,
                    (encrypted_value,),
                )

                test_id = cur.fetchone()[0]

            conn.commit()

        return jsonify(
            {
                "status": "ok",
                "mensagem": (
                    "Gravacao criptografada no PostgreSQL "
                    "funcionando."
                ),
                "teste_id": test_id,
            }
        )

    except Exception:
        app.logger.exception("Falha no teste de armazenamento")
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Falha no teste de armazenamento.",
            }
        ), 500


@app.get("/linkedin/login")
def linkedin_login():
    session_error = require_session_secret()
    if session_error:
        return session_error
    if not LINKEDIN_CLIENT_ID:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "LINKEDIN_CLIENT_ID nao configurado.",
            }
        ), 500

    state = secrets.token_urlsafe(32)
    session["linkedin_oauth_state"] = state

    params = {
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": LINKEDIN_OAUTH_SCOPE,
    }

    authorization_url = (
        LINKEDIN_AUTH_URL
        + "?"
        + urllib.parse.urlencode(params)
    )

    return redirect(authorization_url)


@app.get("/linkedin/callback")
def linkedin_callback():
    session_error = require_session_secret()
    if session_error:
        return session_error
    error = request.args.get("error")

    if error:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Autorizacao do LinkedIn recusada.",
                "detalhe": error,
            }
        ), 400

    code = request.args.get("code")
    state = request.args.get("state")

    expected_state = session.get("linkedin_oauth_state")

    if not code:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Codigo de autorizacao nao recebido.",
            }
        ), 400

    if not state or not expected_state:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Estado OAuth ausente.",
            }
        ), 400

    if not secrets.compare_digest(state, expected_state):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Estado OAuth invalido.",
            }
        ), 403

    token_payload = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": LINKEDIN_REDIRECT_URI,
            "client_id": LINKEDIN_CLIENT_ID,
            "client_secret": LINKEDIN_CLIENT_SECRET,
        }
    ).encode("utf-8")

    token_request = urllib.request.Request(
        LINKEDIN_TOKEN_URL,
        data=token_payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            token_request,
            timeout=30
        ) as response:
            token_data = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")

        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = body

        return jsonify(
            {
                "status": "erro",
                "mensagem": "Falha ao obter token do LinkedIn.",
                "detalhe": detail,
            }
        ), 400

    access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in")

    if not access_token:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Token do LinkedIn nao recebido.",
            }
        ), 400

    userinfo_headers = {
        "Authorization": f"Bearer {access_token}",
    }

    userinfo_status, userinfo_data, _ = http_json_request(
        LINKEDIN_USERINFO_URL,
        method="GET",
        headers=userinfo_headers,
    )

    if userinfo_status != 200:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Nao foi possivel obter o Member ID.",
                "detalhe": userinfo_data,
            }
        ), 400

    member_id = userinfo_data.get("sub")

    if not member_id:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Member ID nao encontrado.",
            }
        ), 400

    encrypted_token = encrypt_value(access_token)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO linkedin_accounts (
                    account_name,
                    linkedin_member_id,
                    access_token,
                    token_expires_at,
                    updated_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    NOW() + (%s * INTERVAL '1 second'),
                    NOW()
                )
                ON CONFLICT (account_name)
                DO UPDATE SET
                    linkedin_member_id = EXCLUDED.linkedin_member_id,
                    access_token = EXCLUDED.access_token,
                    token_expires_at = EXCLUDED.token_expires_at,
                    updated_at = NOW();
                """,
                (
                    LINKEDIN_ACCOUNT_NAME,
                    member_id,
                    encrypted_token,
                    expires_in or 0,
                ),
            )

        conn.commit()

    session.pop("linkedin_oauth_state", None)

    return jsonify(
        {
            "status": "linkedin_autorizado",
            "projeto": "Automacao Murici",
            "mensagem": (
                "LinkedIn autorizado, Member ID obtido "
                "e token armazenado com criptografia."
            ),
            "token_recebido": True,
            "member_id_obtido": True,
            "expira_em": "armazenado no banco",
        }
    )


@app.get("/google/login")
def google_login():
    session_error = require_session_secret()
    if session_error:
        return session_error
    if not GOOGLE_CLIENT_ID:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "GOOGLE_CLIENT_ID nao configurado.",
            }
        ), 500

    try:
        account_name = normalize_google_account_name(request.args.get("account", "Drive5"))
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400

    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state
    session["google_oauth_account"] = account_name

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    authorization_url = (
        GOOGLE_AUTH_URL
        + "?"
        + urllib.parse.urlencode(params)
    )

    return redirect(authorization_url)


@app.get("/google/callback")
def google_callback():
    session_error = require_session_secret()
    if session_error:
        return session_error
    error = request.args.get("error")

    if error:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Autorizacao do Google recusada.",
                "detalhe": error,
            }
        ), 400

    code = request.args.get("code")
    state = request.args.get("state")

    expected_state = session.get("google_oauth_state")

    if not code:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Codigo de autorizacao do Google nao recebido.",
            }
        ), 400

    if not state or not expected_state:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Estado OAuth do Google ausente.",
            }
        ), 400

    if not secrets.compare_digest(state, expected_state):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Estado OAuth do Google invalido.",
            }
        ), 403

    try:
        account_name = normalize_google_account_name(session.get("google_oauth_account", "Drive5"))
    except ValueError as error:
        return jsonify({"status": "erro", "mensagem": str(error)}), 400

    token_payload = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")

    token_request = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=token_payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            token_request,
            timeout=30
        ) as response:
            token_data = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")

        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = body

        return jsonify(
            {
                "status": "erro",
                "mensagem": "Falha ao obter token do Google.",
                "detalhe": detail,
            }
        ), 400

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    if not access_token:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Token do Google nao recebido.",
            }
        ), 400

    encrypted_access_token = encrypt_value(access_token)

    encrypted_refresh_token = (
        encrypt_value(refresh_token)
        if refresh_token
        else None
    )

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO google_accounts (
                    account_name,
                    provider,
                    access_token,
                    refresh_token,
                    token_expires_at,
                    updated_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW() + (%s * INTERVAL '1 second'),
                    NOW()
                )
                ON CONFLICT (account_name)
                DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = COALESCE(
                        EXCLUDED.refresh_token,
                        google_accounts.refresh_token
                    ),
                    token_expires_at = EXCLUDED.token_expires_at,
                    updated_at = NOW();
                """,
                (
                    account_name,
                    "google",
                    encrypted_access_token,
                    encrypted_refresh_token,
                    expires_in or 0,
                ),
            )

        conn.commit()

    session.pop("google_oauth_state", None)
    session.pop("google_oauth_account", None)

    return jsonify(
        {
            "status": "google_autorizado",
            "projeto": "Automacao Murici",
            "conta": account_name,
            "mensagem": (
                "Google autorizado e token armazenado "
                "com criptografia."
            ),
            "token_recebido": True,
            "refresh_token_recebido": bool(refresh_token),
            "expira_em": "armazenado no banco",
        }
    )


@app.post("/linkedin/publish")
def linkedin_publish():
    auth_error = require_publish_secret()

    if auth_error:
        return auth_error

    if not request.is_json:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "A requisicao deve utilizar JSON.",
            }
        ), 400

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "JSON invalido.",
            }
        ), 400

    commentary = data.get("content")
    title = data.get("title")
    post_number = data.get("post_number")

    if not isinstance(commentary, str) or len(commentary.strip()) < 10:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "O campo content deve conter ao menos 10 caracteres.",
            }
        ), 400

    if title is not None and not isinstance(title, str):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "title deve ser texto ou nulo.",
            }
        ), 400

    if post_number is not None:
        if isinstance(post_number, bool):
            return jsonify({"status": "erro", "mensagem": "post_number deve ser um inteiro positivo."}), 400
        try:
            post_number = int(post_number)
        except (TypeError, ValueError):
            return jsonify({"status": "erro", "mensagem": "post_number deve ser um inteiro positivo."}), 400
        if post_number < 1:
            return jsonify({"status": "erro", "mensagem": "post_number deve ser um inteiro positivo."}), 400

    post_id = None
    try:
        post_id = publish_linkedin_text(commentary)

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO editorial_posts (
                        post_number,
                        title,
                        content,
                        status,
                        published_at,
                        linkedin_post_id,
                        updated_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        NOW(),
                        %s,
                        NOW()
                    )
                    RETURNING id;
                    """,
                    (
                        post_number,
                        title,
                        commentary,
                        "publicado",
                        post_id,
                    ),
                )

                editorial_post_id = cur.fetchone()[0]

            conn.commit()

        return jsonify(
            {
                "status": "publicado",
                "mensagem": "Publicacao realizada no LinkedIn.",
                "linkedin_post_id": post_id,
                "editorial_post_id": editorial_post_id,
            }
        )

    except Exception:
        app.logger.exception(
            "Falha na publicacao direta; linkedin_post_id_retornado=%s",
            bool(post_id),
        )
        if post_id:
            return jsonify({
                "status": "reconciliacao_manual",
                "mensagem": (
                    "O LinkedIn retornou um identificador, mas o registro local falhou. "
                    "Confira a publicacao no LinkedIn antes de tentar novamente."
                ),
                "linkedin_post_id": post_id,
                "reconciliacao_manual": True,
            }), 500
        return safe_error_response(
            "Nao foi possivel confirmar a publicacao. Consulte os logs antes de tentar novamente."
        )


@app.post("/scheduler/queue")
def scheduler_queue():
    """
    Coloca uma publicacao na fila automatica.

    JSON esperado:

    {
        "post_number": 41,
        "title": "Titulo",
        "content": "Texto completo",
        "scheduled_for": "2026-10-10T14:30:00-03:00"
    }
    """

    auth_error = require_publish_secret()

    if auth_error:
        return auth_error

    if not request.is_json:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "A requisicao deve utilizar JSON.",
            }
        ), 400

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "JSON invalido.",
            }
        ), 400

    content = data.get("content")
    title = data.get("title")
    post_number = data.get("post_number")
    scheduled_for = data.get("scheduled_for")

    if title is not None and not isinstance(title, str):
        return jsonify({"status": "erro", "mensagem": "title deve ser texto ou nulo."}), 400

    if post_number is not None:
        if isinstance(post_number, bool):
            return jsonify({"status": "erro", "mensagem": "post_number deve ser um inteiro positivo."}), 400
        try:
            post_number = int(post_number)
        except (TypeError, ValueError):
            return jsonify({"status": "erro", "mensagem": "post_number deve ser um inteiro positivo."}), 400
        if post_number < 1:
            return jsonify({"status": "erro", "mensagem": "post_number deve ser um inteiro positivo."}), 400

    if not content or not isinstance(content, str):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "O campo content e obrigatorio.",
            }
        ), 400

    if len(content.strip()) < 10:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "O campo content nao pode estar vazio.",
            }
        ), 400

    try:
        scheduled_datetime = parse_scheduled_for(
            scheduled_for
        )
    except ValueError as error:
        return jsonify(
            {
                "status": "erro",
                "mensagem": str(error),
            }
        ), 400

    try:
        ensure_scheduler_tables()

        with get_db_connection() as conn:
            with conn.cursor() as cur:

                if post_number is not None:
                    cur.execute(
                        """
                        SELECT id
                        FROM editorial_posts
                        WHERE post_number = %s
                        LIMIT 1;
                        """,
                        (post_number,),
                    )

                    existing_published = cur.fetchone()

                    if existing_published:
                        return jsonify(
                            {
                                "status": "erro",
                                "mensagem": (
                                    "Esse post_number ja possui "
                                    "uma publicacao registrada."
                                ),
                                "post_number": post_number,
                                "editorial_post_id": (
                                    existing_published[0]
                                ),
                            }
                        ), 409

                cur.execute(
                    """
                    INSERT INTO linkedin_publish_queue (
                        post_number,
                        title,
                        content,
                        scheduled_for,
                        status,
                        attempts,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        'agendado',
                        0,
                        NOW(),
                        NOW()
                    )
                    RETURNING id;
                    """,
                    (
                        post_number,
                        title,
                        content,
                        scheduled_datetime,
                    ),
                )

                queue_id = cur.fetchone()[0]

            conn.commit()

        return jsonify(
            {
                "status": "agendado",
                "mensagem": (
                    "Publicacao adicionada a fila automatica."
                ),
                "queue_id": queue_id,
                "post_number": post_number,
                "scheduled_for": scheduled_datetime.isoformat(),
            }
        )

    except psycopg.errors.UniqueViolation:
        return jsonify(
            {
                "status": "erro",
                "mensagem": (
                    "Esse post_number ja possui uma entrada ativa "
                    "na fila."
                ),
            }
        ), 409

    except Exception:
        app.logger.exception("Falha ao enfileirar publicacao")
        return safe_error_response("Falha ao adicionar a publicacao na fila. Consulte os logs do servidor.")


@app.get("/scheduler/diagnostics")
def scheduler_diagnostics():
    """Consulta somente leitura de itens que podem exigir reconciliacao manual."""

    auth_error = require_publish_secret()

    if auth_error:
        return auth_error

    try:
        # Esta rota e estritamente diagnostica: nao cria tabelas, indices,
        # nem executa migracoes implicitas. Se a fila nao existir, falha
        # de forma controlada e o operador deve verificar a instalacao.
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        post_number,
                        status,
                        attempts,
                        scheduled_for,
                        locked_at,
                        updated_at,
                        GREATEST(
                            0,
                            EXTRACT(EPOCH FROM (NOW() - COALESCE(locked_at, updated_at)))
                        )::BIGINT AS age_seconds
                    FROM linkedin_publish_queue
                    WHERE status = 'processando'
                    ORDER BY COALESCE(locked_at, updated_at) ASC, id ASC
                    LIMIT 100;
                    """
                )
                rows = cur.fetchall()

        items = []
        for row in rows:
            (queue_id, post_number, status, attempts, scheduled_for,
             locked_at, updated_at, age_seconds) = row
            items.append({
                "queue_id": queue_id,
                "post_number": post_number,
                "status": status,
                "attempts": attempts,
                "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
                "locked_at": locked_at.isoformat() if locked_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "age_seconds": int(age_seconds or 0),
                "requer_reconciliacao_manual": True,
            })

        return jsonify({
            "status": "ok",
            "somente_leitura": True,
            "quantidade": len(items),
            "limite": 100,
            "itens_processando": items,
            "aviso": (
                "Nao redefina nem repita automaticamente itens processando. "
                "Confirme primeiro se cada publicacao existe no LinkedIn."
            ),
        })

    except Exception:
        app.logger.exception("Falha no diagnostico da fila do scheduler")
        return safe_error_response("Falha ao consultar diagnosticos da fila. Consulte os logs do servidor.")


@app.get("/scheduler/status")
def scheduler_status():
    """
    Consulta o estado atual da fila.
    """

    auth_error = require_publish_secret()

    if auth_error:
        return auth_error

    try:
        ensure_scheduler_tables()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        status,
                        COUNT(*)
                    FROM linkedin_publish_queue
                    GROUP BY status
                    ORDER BY status;
                    """
                )

                counts_rows = cur.fetchall()

                counts = {
                    row[0]: row[1]
                    for row in counts_rows
                }

                cur.execute(
                    """
                    SELECT
                        id,
                        post_number,
                        title,
                        scheduled_for,
                        status,
                        attempts
                    FROM linkedin_publish_queue
                    WHERE status = 'agendado'
                    ORDER BY scheduled_for ASC, id ASC
                    LIMIT 1;
                    """
                )

                next_row = cur.fetchone()

        next_publication = None

        if next_row:
            (
                queue_id,
                post_number,
                title,
                scheduled_for,
                status,
                attempts,
            ) = next_row

            next_publication = {
                "queue_id": queue_id,
                "post_number": post_number,
                "title": title,
                "scheduled_for": scheduled_for.isoformat(),
                "status": status,
                "attempts": attempts,
            }

        return jsonify(
            {
                "status": "ok",
                "mensagem": "Fila automatica funcionando.",
                "quantidades": counts,
                "proxima_publicacao": next_publication,
            }
        )

    except Exception:
        app.logger.exception("Falha ao consultar status do scheduler")
        return safe_error_response("Falha ao consultar a fila. Consulte os logs do servidor.")


@app.post("/scheduler/run")
def scheduler_run():
    """
    Executa uma publicacao vencida da fila.

    O endpoint e protegido pelo PUBLISH_SECRET.
    """

    auth_error = require_publish_secret()

    if auth_error:
        return auth_error

    try:
        result = scheduler_publish_one()

        if result["status"] == "publicado":
            return jsonify(result), 200

        if result["status"] == "idle":
            return jsonify(result), 200

        if result["status"] == "busy":
            return jsonify(result), 409

        return jsonify(result), 500

    except Exception:
        app.logger.exception("Falha na execucao do scheduler")
        return safe_error_response("Falha na execucao do scheduler. Consulte os logs do servidor.")


@app.get("/analytics/prepare")
def analytics_prepare():
    auth_error = require_publish_secret()

    if auth_error:
        return auth_error

    try:
        ensure_analytics_tables()

        return jsonify(
            {
                "status": "ok",
                "mensagem": (
                    "Estrutura de armazenamento de metricas preparada."
                ),
                "tabelas": [
                    "linkedin_post_metrics",
                    "linkedin_metrics_collection_runs",
                ],
            }
        )

    except Exception:
        app.logger.exception("Falha ao preparar tabelas de analytics")
        return safe_error_response("Falha ao preparar as tabelas de analytics. Consulte os logs do servidor.")


@app.post("/analytics/record")
def analytics_record():
    """
    Recebe uma coleta de metricas e grava no PostgreSQL.

    Esta rota nao consulta o LinkedIn.
    """

    auth_error = require_publish_secret()

    if auth_error:
        return auth_error

    if not request.is_json:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "A requisicao deve utilizar JSON.",
            }
        ), 400

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "JSON invalido.",
            }
        ), 400

    linkedin_post_id = data.get("linkedin_post_id")

    if not isinstance(linkedin_post_id, str) or not linkedin_post_id.strip():
        return jsonify(
            {
                "status": "erro",
                "mensagem": "linkedin_post_id deve ser um texto nao vazio.",
            }
        ), 400
    linkedin_post_id = linkedin_post_id.strip()
    if len(linkedin_post_id) > 512:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "linkedin_post_id excede o tamanho permitido.",
            }
        ), 400

    metric_fields = (
        "impressions", "members_reached", "reactions", "comments", "reposts",
        "post_saves", "post_sends", "link_clicks", "premium_cta_clicks",
        "followers_gained_from_content", "profile_views_from_content", "engagement_total",
    )
    for field in metric_fields:
        value = data.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            return jsonify(
                {
                    "status": "erro",
                    "mensagem": f"{field} deve ser um inteiro nao negativo ou nulo.",
                }
            ), 400

    source = data.get("source", "manual")
    if not isinstance(source, str) or source not in {"manual", "linkedin_api"}:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "source deve ser 'manual' ou 'linkedin_api'.",
            }
        ), 400

    try:
        ensure_analytics_tables()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id
                    FROM editorial_posts
                    WHERE linkedin_post_id = %s
                    ORDER BY id DESC
                    LIMIT 1;
                    """,
                    (linkedin_post_id,),
                )

                row = cur.fetchone()
                editorial_post_id = row[0] if row else None

                impressions = data.get("impressions")
                members_reached = data.get("members_reached")
                reactions = data.get("reactions")
                comments = data.get("comments")
                reposts = data.get("reposts")
                post_saves = data.get("post_saves")
                post_sends = data.get("post_sends")
                link_clicks = data.get("link_clicks")
                premium_cta_clicks = data.get(
                    "premium_cta_clicks"
                )

                followers_gained = data.get(
                    "followers_gained_from_content"
                )

                profile_views = data.get(
                    "profile_views_from_content"
                )

                engagement_total = data.get(
                    "engagement_total"
                )

                if engagement_total is None:
                    engagement_total = calculate_engagement_total(
                        {
                            "REACTION": reactions,
                            "COMMENT": comments,
                            "RESHARE": reposts,
                            "POST_SAVE": post_saves,
                            "POST_SEND": post_sends,
                            "LINK_CLICKS": link_clicks,
                            "PREMIUM_CTA_CLICKS": (
                                premium_cta_clicks
                            ),
                        }
                    )

                cur.execute(
                    """
                    INSERT INTO linkedin_post_metrics (
                        editorial_post_id,
                        linkedin_post_id,
                        measured_at,
                        impressions,
                        members_reached,
                        reactions,
                        comments,
                        reposts,
                        post_saves,
                        post_sends,
                        link_clicks,
                        premium_cta_clicks,
                        followers_gained_from_content,
                        profile_views_from_content,
                        engagement_total,
                        source
                    )
                    VALUES (
                        %s,
                        %s,
                        NOW(),
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING id;
                    """,
                    (
                        editorial_post_id,
                        linkedin_post_id,
                        impressions,
                        members_reached,
                        reactions,
                        comments,
                        reposts,
                        post_saves,
                        post_sends,
                        link_clicks,
                        premium_cta_clicks,
                        followers_gained,
                        profile_views,
                        engagement_total,
                        source,
                    ),
                )

                metric_id = cur.fetchone()[0]

            conn.commit()

        return jsonify(
            {
                "status": "ok",
                "mensagem": "Metricas armazenadas no PostgreSQL.",
                "metric_id": metric_id,
                "editorial_post_id": editorial_post_id,
            }
        )

    except Exception:
        app.logger.exception("Falha ao registrar metricas do LinkedIn")
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Nao foi possivel registrar as metricas. Consulte os logs do servidor.",
            }
        ), 500


@app.post("/analytics/collect")
def analytics_collect():
    """
    Coleta automatica opcional. Fica desativada enquanto as metricas
    forem tratadas por relatorios enviados manualmente.
    """

    if not LINKEDIN_ANALYTICS_AUTOMATIC_ENABLED:
        return jsonify(
            {
                "status": "desativado",
                "mensagem": (
                    "A coleta automatica esta desativada. Envie os relatorios "
                    "do LinkedIn manualmente para analise."
                ),
            }
        ), 410

    auth_error = require_publish_secret()

    if auth_error:
        return auth_error

    run_id = None
    posts_found = 0
    posts_updated = 0
    metrics_saved = 0

    try:
        ensure_analytics_tables()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO linkedin_metrics_collection_runs (
                        status
                    )
                    VALUES ('started')
                    RETURNING id;
                    """
                )

                run_id = cur.fetchone()[0]

            conn.commit()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (linkedin_post_id)
                        id,
                        linkedin_post_id
                    FROM editorial_posts
                    WHERE linkedin_post_id IS NOT NULL
                      AND TRIM(linkedin_post_id) <> ''
                    ORDER BY linkedin_post_id, id DESC;
                    """
                )

                posts = cur.fetchall()

        posts_found = len(posts)

        for editorial_post_id, linkedin_post_id in posts:

            try:
                metrics, _raw_payload = linkedin_post_analytics(
                    linkedin_post_id
                )

                impressions = metrics.get("IMPRESSION")
                members_reached = metrics.get(
                    "MEMBERS_REACHED"
                )
                reactions = metrics.get("REACTION")
                comments = metrics.get("COMMENT")
                reposts = metrics.get("RESHARE")
                post_saves = metrics.get("POST_SAVE")
                post_sends = metrics.get("POST_SEND")
                link_clicks = metrics.get("LINK_CLICKS")

                premium_cta_clicks = metrics.get(
                    "PREMIUM_CTA_CLICKS"
                )

                followers_gained = metrics.get(
                    "FOLLOWER_GAINED_FROM_CONTENT"
                )

                profile_views = metrics.get(
                    "PROFILE_VIEW_FROM_CONTENT"
                )

                engagement_total = calculate_engagement_total(
                    metrics
                )

                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO linkedin_post_metrics (
                                editorial_post_id,
                                linkedin_post_id,
                                measured_at,
                                impressions,
                                members_reached,
                                reactions,
                                comments,
                                reposts,
                                post_saves,
                                post_sends,
                                link_clicks,
                                premium_cta_clicks,
                                followers_gained_from_content,
                                profile_views_from_content,
                                engagement_total,
                                source
                            )
                            VALUES (
                                %s,
                                %s,
                                NOW(),
                                %s,
                                %s,
                                %s,
                                %s,
                                %s,
                                %s,
                                %s,
                                %s,
                                %s,
                                %s,
                                %s,
                                %s,
                                'linkedin_api'
                            );
                            """,
                            (
                                editorial_post_id,
                                linkedin_post_id,
                                impressions,
                                members_reached,
                                reactions,
                                comments,
                                reposts,
                                post_saves,
                                post_sends,
                                link_clicks,
                                premium_cta_clicks,
                                followers_gained,
                                profile_views,
                                engagement_total,
                            ),
                        )

                    conn.commit()

                posts_updated += 1
                metrics_saved += 1

            except LinkedInAnalyticsError as error:

                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE linkedin_metrics_collection_runs
                            SET
                                finished_at = NOW(),
                                status = %s,
                                posts_found = %s,
                                posts_updated = %s,
                                metrics_saved = %s,
                                error_message = %s
                            WHERE id = %s;
                            """,
                            (
                                (
                                    "permission_required"
                                    if error.status_code == 403
                                    else "error"
                                ),
                                posts_found,
                                posts_updated,
                                metrics_saved,
                                json.dumps(error.payload),
                                run_id,
                            ),
                        )

                    conn.commit()

                if error.status_code == 403:
                    return jsonify(
                        {
                            "status": "permission_required",
                            "mensagem": (
                                "O LinkedIn recusou a consulta de "
                                "analytics. A aplicacao ainda precisa "
                                "de acesso oficial a "
                                "r_member_postAnalytics / "
                                "Community Management API."
                            ),
                            "http_linkedin": error.status_code,
                            "run_id": run_id,
                            "posts_found": posts_found,
                            "posts_updated": posts_updated,
                        }
                    ), 403

                return jsonify(
                    {
                        "status": "erro",
                        "mensagem": (
                            "Falha ao consultar analytics "
                            "do LinkedIn."
                        ),
                        "http_linkedin": error.status_code,
                        "detalhe": error.payload,
                        "run_id": run_id,
                        "posts_found": posts_found,
                        "posts_updated": posts_updated,
                    }
                ), 502

            except Exception as error:

                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE linkedin_metrics_collection_runs
                            SET
                                finished_at = NOW(),
                                status = 'error',
                                posts_found = %s,
                                posts_updated = %s,
                                metrics_saved = %s,
                                error_message = %s
                            WHERE id = %s;
                            """,
                            (
                                posts_found,
                                posts_updated,
                                metrics_saved,
                                str(error),
                                run_id,
                            ),
                        )

                    conn.commit()

                app.logger.exception("Falha na coleta de analytics do LinkedIn para run_id=%s", run_id)
                return jsonify(
                    {
                        "status": "erro",
                        "mensagem": "Falha na coleta de analytics. Consulte os logs do servidor.",
                        "run_id": run_id,
                        "posts_found": posts_found,
                        "posts_updated": posts_updated,
                    }
                ), 500

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE linkedin_metrics_collection_runs
                    SET
                        finished_at = NOW(),
                        status = 'completed',
                        posts_found = %s,
                        posts_updated = %s,
                        metrics_saved = %s,
                        error_message = NULL
                    WHERE id = %s;
                    """,
                    (
                        posts_found,
                        posts_updated,
                        metrics_saved,
                        run_id,
                    ),
                )

            conn.commit()

        return jsonify(
            {
                "status": "completed",
                "mensagem": (
                    "Coleta de metricas do LinkedIn concluida."
                ),
                "run_id": run_id,
                "posts_found": posts_found,
                "posts_updated": posts_updated,
                "metrics_saved": metrics_saved,
            }
        )

    except Exception as error:

        if run_id is not None:
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE linkedin_metrics_collection_runs
                            SET
                                finished_at = NOW(),
                                status = 'error',
                                posts_found = %s,
                                posts_updated = %s,
                                metrics_saved = %s,
                                error_message = %s
                            WHERE id = %s;
                            """,
                            (
                                posts_found,
                                posts_updated,
                                metrics_saved,
                                str(error),
                                run_id,
                            ),
                        )

                    conn.commit()

            except Exception:
                pass

        app.logger.exception("Falha geral na coleta de analytics do LinkedIn para run_id=%s", run_id)
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Falha na coleta de analytics. Consulte os logs do servidor.",
                "run_id": run_id,
                "posts_found": posts_found,
                "posts_updated": posts_updated,
                "metrics_saved": metrics_saved,
            }
        ), 500


# Google Workspace: endpoints administrativos protegidos por PUBLISH_SECRET.
# Sheets fica em leitura por padrao; escrita exige habilitacao explicita no Render.
GOOGLE_SHEETS_SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
GOOGLE_SHEETS_WRITE_ENABLED = (
    os.environ.get("GOOGLE_SHEETS_WRITE_ENABLED", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
GOOGLE_SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"
GOOGLE_GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def google_workspace_api_request(url, method="GET", payload=None):
    """Chamada autenticada do Workspace usando a conta Google Drive5 autorizada."""
    access_token = google_drive_access_token("Drive5")
    headers = {"Authorization": f"Bearer {access_token}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    status_code, response_data, _ = http_json_request(
        url, method=method, headers=headers, data=payload
    )
    if status_code not in (200, 201, 202, 204):
        # Nao incluir tokens nem dados sensiveis na resposta externa.
        raise RuntimeError(
            f"Google Workspace recusou a requisicao (HTTP {status_code})."
        )
    return response_data


@app.get("/google-workspace/status")
def google_workspace_status():
    """Mostra configuracao sem consultar nem modificar dados Google."""
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    return jsonify({
        "status": "ok",
        "conta_configurada": "Drive5",
        "sheets_spreadsheet_id_configurado": bool(GOOGLE_SHEETS_SPREADSHEET_ID),
        "sheets_escrita_habilitada": GOOGLE_SHEETS_WRITE_ENABLED,
        "gmail_modo": "somente_leitura",
        "apis_consultadas": False,
    })


@app.get("/google-workspace/sheets/metadata")
def google_workspace_sheets_metadata():
    """Le metadados da planilha configurada; nao altera valores."""
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    if not GOOGLE_SHEETS_SPREADSHEET_ID:
        return jsonify({
            "status": "erro",
            "mensagem": "GOOGLE_SHEETS_SPREADSHEET_ID ainda nao configurado no Render."
        }), 503
    try:
        sid = urllib.parse.quote(GOOGLE_SHEETS_SPREADSHEET_ID, safe="")
        fields = urllib.parse.quote("spreadsheetId,properties(title),sheets(properties(sheetId,title,index,gridProperties(rowCount,columnCount)))", safe="")
        data = google_workspace_api_request(
            f"{GOOGLE_SHEETS_API_BASE}/{sid}?fields={fields}"
        )
        return jsonify({
            "status": "ok",
            "spreadsheetId": data.get("spreadsheetId"),
            "properties": data.get("properties", {}),
            "sheets": [
                {
                    "properties": {
                        "sheetId": s.get("properties", {}).get("sheetId"),
                        "title": s.get("properties", {}).get("title"),
                        "index": s.get("properties", {}).get("index"),
                        "gridProperties": s.get("properties", {}).get("gridProperties", {}),
                    }
                }
                for s in data.get("sheets", [])
            ],
            "alterou_dados": False,
        })
    except Exception:
        app.logger.exception("Falha ao ler metadados da planilha Google")
        return safe_error_response("Nao foi possivel ler a planilha. Verifique autorizacao, API e ID configurado.", 502)


@app.get("/google-workspace/sheets/values")
def google_workspace_sheets_values():
    """Le um intervalo explicito da planilha; restringe intervalo e volume."""
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    if not GOOGLE_SHEETS_SPREADSHEET_ID:
        return jsonify({"status": "erro", "mensagem": "Planilha ainda nao configurada."}), 503
    value_range = request.args.get("range", "").strip()
    if not value_range or len(value_range) > 200 or "!" not in value_range:
        return jsonify({
            "status": "erro",
            "mensagem": "Informe range no formato Aba!A1:Z100; o intervalo deve indicar uma aba e limitar o volume."
        }), 400
    if any(ch in value_range for ch in "\r\n"):
        return jsonify({"status": "erro", "mensagem": "Intervalo invalido."}), 400
    try:
        sid = urllib.parse.quote(GOOGLE_SHEETS_SPREADSHEET_ID, safe="")
        encoded_range = urllib.parse.quote(value_range, safe="")
        data = google_workspace_api_request(
            f"{GOOGLE_SHEETS_API_BASE}/{sid}/values/{encoded_range}"
        )
        rows = data.get("values", [])
        if len(rows) > 500:
            return jsonify({"status": "erro", "mensagem": "O intervalo retornou mais de 500 linhas; reduza o intervalo."}), 413
        return jsonify({
            "status": "ok",
            "range": data.get("range", value_range),
            "majorDimension": data.get("majorDimension", "ROWS"),
            "values": rows,
            "row_count": len(rows),
            "alterou_dados": False,
        })
    except Exception:
        app.logger.exception("Falha ao ler intervalo da planilha Google")
        return safe_error_response("Nao foi possivel ler o intervalo. Verifique autorizacao, API e nome da aba.", 502)


@app.put("/google-workspace/sheets/values")
def google_workspace_sheets_update_values():
    """Escrita opt-in; desabilitada por padrao e nunca usada em importacao automatica."""
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    if not GOOGLE_SHEETS_WRITE_ENABLED:
        return jsonify({
            "status": "desativado",
            "mensagem": "A escrita na planilha esta desabilitada. Habilite GOOGLE_SHEETS_WRITE_ENABLED somente depois de validar a planilha e o intervalo."
        }), 423
    if not GOOGLE_SHEETS_SPREADSHEET_ID:
        return jsonify({"status": "erro", "mensagem": "Planilha ainda nao configurada."}), 503
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"status": "erro", "mensagem": "Envie JSON com range e values."}), 400
    value_range = payload.get("range")
    values = payload.get("values")
    if (
        not isinstance(value_range, str) or "!" not in value_range
        or len(value_range) > 200 or "\n" in value_range or "\r" in value_range
        or not isinstance(values, list) or not values or len(values) > 100
        or any(not isinstance(row, list) or len(row) > 52 for row in values)
    ):
        return jsonify({"status": "erro", "mensagem": "Intervalo ou matriz de valores invalida; limite de 100 linhas e 52 colunas."}), 400
    try:
        sid = urllib.parse.quote(GOOGLE_SHEETS_SPREADSHEET_ID, safe="")
        encoded_range = urllib.parse.quote(value_range, safe="")
        data = google_workspace_api_request(
            f"{GOOGLE_SHEETS_API_BASE}/{sid}/values/{encoded_range}?valueInputOption=RAW",
            method="PUT",
            payload={"range": value_range, "majorDimension": "ROWS", "values": values},
        )
        return jsonify({
            "status": "ok",
            "updatedRange": data.get("updatedRange"),
            "updatedRows": data.get("updatedRows"),
            "updatedColumns": data.get("updatedColumns"),
            "updatedCells": data.get("updatedCells"),
        })
    except Exception:
        app.logger.exception("Falha ao atualizar intervalo da planilha Google")
        return safe_error_response("A atualizacao falhou; confira o intervalo e as permissoes da planilha.", 502)


@app.get("/google-workspace/gmail/messages")
def google_workspace_gmail_messages():
    """Pesquisa mensagens Gmail sem modificar, arquivar ou enviar mensagens."""
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    query = request.args.get("q", "newer_than:90d").strip()
    if not query or len(query) > 300:
        return jsonify({"status": "erro", "mensagem": "Consulta Gmail invalida (1 a 300 caracteres)."}), 400
    try:
        params = urllib.parse.urlencode({"q": query, "maxResults": 25})
        data = google_workspace_api_request(f"{GOOGLE_GMAIL_API_BASE}/messages?{params}")
        messages = data.get("messages", [])
        results = []
        for message in messages[:25]:
            mid = message.get("id")
            if not mid:
                continue
            encoded_id = urllib.parse.quote(mid, safe="")
            detail = google_workspace_api_request(
                f"{GOOGLE_GMAIL_API_BASE}/messages/{encoded_id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date"
            )
            headers = {}
            for header in detail.get("payload", {}).get("headers", []):
                if isinstance(header, dict) and header.get("name"):
                    headers[header["name"].lower()] = header.get("value", "")
            results.append({
                "id": mid,
                "threadId": detail.get("threadId"),
                "date": headers.get("date"),
                "from": headers.get("from"),
                "subject": headers.get("subject"),
                "snippet": detail.get("snippet", ""),
                "labels": detail.get("labelIds", []),
            })
        return jsonify({
            "status": "ok",
            "query": query,
            "count": len(results),
            "messages": results,
            "mode": "somente_leitura",
            "alterou_mensagens": False,
        })
    except Exception:
        app.logger.exception("Falha ao pesquisar mensagens Gmail")
        return safe_error_response("Nao foi possivel consultar o Gmail. Verifique o escopo, API e autorizacao.", 502)




@app.get("/__temporary_aulas_probe")
def __temporary_aulas_probe():
    """Temporary fixed-query Drive5 diagnostic; key-protected and read-only."""
    expected = os.environ.get("AULAS_PROBE_KEY", "")
    supplied = request.args.get("k", "")
    if not expected or not secrets.compare_digest(supplied, expected):
        return jsonify({"status": "erro", "mensagem": "Nao autorizado."}), 404
    try:
        q = urllib.parse.urlencode({
            "q": "name = 'aulas' and trashed = false",
            "pageSize": "100",
            "fields": "files(id,name,mimeType,webViewLink,shortcutDetails(targetId,targetMimeType),parents)"
        })
        data, _ = google_drive_api_request("GET", f"{GOOGLE_DRIVE_FILES_URL}?{q}", account_name="Drive5")
        output = []
        for item in data.get("files", []):
            record = {"name": item.get("name"), "mimeType": item.get("mimeType"),
                      "webViewLink": item.get("webViewLink"), "parents": item.get("parents", [])}
            details = item.get("shortcutDetails") or {}
            target_id = details.get("targetId")
            if item.get("mimeType") == "application/vnd.google-apps.shortcut" and target_id:
                tid = urllib.parse.quote(target_id, safe="")
                target, _ = google_drive_api_request(
                    "GET", f"{GOOGLE_DRIVE_FILES_URL}/{tid}?fields=id,name,mimeType,webViewLink,parents",
                    account_name="Drive5")
                record["target"] = target
                if target.get("mimeType") == "application/vnd.google-apps.folder":
                    cq = urllib.parse.urlencode({
                        "q": f"'{target_id}' in parents and trashed = false",
                        "pageSize": "10",
                        "fields": "files(id,name,mimeType,webViewLink)"
                    })
                    children, _ = google_drive_api_request(
                        "GET", f"{GOOGLE_DRIVE_FILES_URL}?{cq}", account_name="Drive5")
                    record["target_children_preview"] = children.get("files", [])
            output.append(record)
        return jsonify({"status": "ok", "account": "Drive5", "matches": len(output),
                        "results": output, "read_only": True})
    except Exception:
        app.logger.exception("Temporary Drive5 aulas shortcut probe failed")
        return safe_error_response("A consulta somente leitura falhou.", 502)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
    )