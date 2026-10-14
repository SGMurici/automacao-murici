import os
import json
import secrets
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
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
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

GOOGLE_REDIRECT_URI = (
    "https://automacao-murici.onrender.com/google/callback"
)


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

# As metricas do LinkedIn sao tratadas exclusivamente a partir de relatorios
# fornecidos manualmente. Uma variavel de ambiente nao pode reativar a coleta.
LINKEDIN_ANALYTICS_AUTOMATIC_ENABLED = False

LINKEDIN_OAUTH_SCOPE = os.environ.get(
    "LINKEDIN_OAUTH_SCOPE",
    "openid profile email w_member_social",
)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

GOOGLE_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"



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
    """Restringe toda operacao Google Drive a conta primaria Drive5."""
    if account_name is None or not str(account_name).strip():
        return "Drive5"
    account_name = str(account_name).strip()
    if account_name != "Drive5":
        raise ValueError("Esta automacao utiliza exclusivamente a conta Drive5.")
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
    """Retorna somente metadados da conta Google autorizada: Drive5."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT account_name, provider, token_expires_at, updated_at
                FROM google_accounts
                WHERE account_name = %s
                LIMIT 1;
                """,
                ("Drive5",),
            )
            row = cur.fetchone()

    if not row:
        return []

    return [
        {
            "account_name": row[0],
            "provider": row[1],
            "token_expires_at": row[2].isoformat() if row[2] else None,
            "updated_at": row[3].isoformat() if row[3] else None,
        }
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
    if status_code not in (200, 201):
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
        "mensagem": "Acesso somente leitura à Google Drive API confirmado para a conta autorizada.",
        "conta": account_name,
        "arquivos_acessiveis": len(files),
        "teste": "somente_leitura",
    }

def google_drive_health_check():
    """Verifica exclusivamente Drive5, sem modificar arquivos no Drive."""
    try:
        teste = google_drive_readonly_check("Drive5")
        return {
            "status": "ok",
            "total_contas": 1,
            "contas_ok": 1,
            "contas_com_erro": 0,
            "contas": [{
                "conta": "Drive5",
                "status": "ok",
                "arquivos_acessiveis": teste.get("arquivos_acessiveis", 0),
                "teste": "somente_leitura",
            }],
        }
    except Exception:
        app.logger.exception("Falha na verificacao somente leitura do Google Drive para Drive5")
        return {
            "status": "erro",
            "total_contas": 1,
            "contas_ok": 0,
            "contas_com_erro": 1,
            "contas": [{
                "conta": "Drive5",
                "status": "erro",
                "mensagem": "Falha na verificacao; consulte os logs do servidor.",
            }],
        }


def google_drive_route_account(preferred_account=None):
    """Usa exclusivamente Drive5; nunca consulta contas alternativas."""
    if preferred_account:
        normalize_google_account_name(preferred_account)
    teste = google_drive_readonly_check("Drive5")
    return {
        "status": "ok",
        "conta_selecionada": "Drive5",
        "preferida": "Drive5",
        "arquivos_acessiveis": teste.get("arquivos_acessiveis", 0),
        "mensagem": "Conta Drive5 validada por leitura; nenhuma outra conta foi consultada.",
    }


def google_drive_test(account_name="Drive5"):
    """Compatibilidade com rota antiga: executa apenas verificacao de leitura."""
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

    if status_code not in (200, 201):
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
            500,
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
        "scope": "https://www.googleapis.com/auth/drive.file",
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



@app.post("/scheduler/queue/batch")
def scheduler_queue_batch():
    """
    Adiciona várias publicações à fila em uma única requisição.
    Não publica imediatamente: cada item fica apenas agendado.
    JSON: {"items": [{"post_number": 41, "title": "...", "content": "...",
      "scheduled_for": "2026-11-08T09:00:00-03:00"}]}
    """
    auth_error = require_publish_secret()
    if auth_error:
        return auth_error
    if not request.is_json:
        return jsonify({"status": "erro", "mensagem": "A requisicao deve utilizar JSON."}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return jsonify({"status": "erro", "mensagem": "Envie um objeto JSON com uma lista 'items'."}), 400

    items = data["items"]
    if not items:
        return jsonify({"status": "erro", "mensagem": "A lista items nao pode estar vazia."}), 400
    if len(items) > 100:
        return jsonify({"status": "erro", "mensagem": "Limite de 100 itens por requisicao."}), 400

    normalized, seen_numbers = [], set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return jsonify({"status": "erro", "item": index, "mensagem": "Cada item deve ser um objeto."}), 400
        content, title = item.get("content"), item.get("title")
        post_number, scheduled_for = item.get("post_number"), item.get("scheduled_for")
        if not isinstance(content, str) or len(content.strip()) < 10:
            return jsonify({"status": "erro", "item": index, "mensagem": "content deve conter ao menos 10 caracteres."}), 400
        if title is not None and not isinstance(title, str):
            return jsonify({"status": "erro", "item": index, "mensagem": "title deve ser texto ou nulo."}), 400
        if post_number is not None:
            if isinstance(post_number, bool):
                return jsonify({"status": "erro", "item": index, "mensagem": "post_number deve ser um inteiro positivo."}), 400
            try:
                post_number = int(post_number)
            except (TypeError, ValueError):
                return jsonify({"status": "erro", "item": index, "mensagem": "post_number deve ser um inteiro positivo."}), 400
            if post_number < 1:
                return jsonify({"status": "erro", "item": index, "mensagem": "post_number deve ser um inteiro positivo."}), 400
            if post_number in seen_numbers:
                return jsonify({"status": "erro", "item": index, "mensagem": "Há post_number repetido dentro do lote.", "post_number": post_number}), 409
            seen_numbers.add(post_number)
        try:
            scheduled_datetime = parse_scheduled_for(scheduled_for)
        except ValueError as error:
            return jsonify({"status": "erro", "item": index, "mensagem": str(error)}), 400
        normalized.append({
            "post_number": post_number,
            "title": title.strip() if isinstance(title, str) and title.strip() else None,
            "content": content.strip(),
            "scheduled_for": scheduled_datetime,
        })

    try:
        ensure_scheduler_tables()
        inserted = []
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Confere conflitos antes de inserir qualquer item do lote.
                for item in normalized:
                    number = item["post_number"]
                    if number is None:
                        continue
                    cur.execute("SELECT id FROM editorial_posts WHERE post_number = %s LIMIT 1;", (number,))
                    published = cur.fetchone()
                    if published:
                        return jsonify({
                            "status": "erro",
                            "mensagem": "Esse post_number ja possui uma publicacao registrada.",
                            "post_number": number,
                            "editorial_post_id": published[0],
                        }), 409
                    cur.execute("""
                        SELECT id FROM linkedin_publish_queue
                        WHERE post_number = %s AND status IN ('agendado', 'publicando')
                        LIMIT 1;
                    """, (number,))
                    queued = cur.fetchone()
                    if queued:
                        return jsonify({
                            "status": "erro",
                            "mensagem": "Esse post_number ja esta na fila ativa.",
                            "post_number": number,
                            "queue_id": queued[0],
                        }), 409
                for item in normalized:
                    cur.execute("""
                        INSERT INTO linkedin_publish_queue (
                            post_number, title, content, scheduled_for,
                            status, attempts, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, 'agendado', 0, NOW(), NOW())
                        RETURNING id;
                    """, (item["post_number"], item["title"], item["content"], item["scheduled_for"]))
                    inserted.append({
                        "queue_id": cur.fetchone()[0],
                        "post_number": item["post_number"],
                        "title": item["title"],
                        "scheduled_for": item["scheduled_for"].isoformat(),
                        "status": "agendado",
                    })
        return jsonify({
            "status": "ok",
            "mensagem": "Lote adicionado à fila. Nenhuma publicação foi enviada imediatamente.",
            "quantidade": len(inserted),
            "itens": inserted,
        }), 201
    except Exception:
        app.logger.exception("Falha ao adicionar lote à fila de publicacao")
        return safe_error_response("Falha ao adicionar o lote à fila. Consulte os logs do servidor.")


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
    """Endpoint legado permanentemente desativado: metricas sao manuais."""
    return jsonify(
        {
            "status": "desativado",
            "mensagem": (
                "A coleta automatica de metricas esta permanentemente desativada. "
                "Envie os relatorios do LinkedIn manualmente para analise."
            ),
        }
    ), 410

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
    )
