import os
import json
import secrets
import urllib.parse
import urllib.request
import urllib.error

from flask import Flask, jsonify, redirect, request, session
import psycopg
from cryptography.fernet import Fernet


app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY")

DATABASE_URL = os.environ.get("DATABASE_URL")

LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY")

PUBLISH_SECRET = os.environ.get("PUBLISH_SECRET")


LINKEDIN_REDIRECT_URI = (
    "https://automacao-murici.onrender.com/linkedin/callback"
)

GOOGLE_REDIRECT_URI = (
    "https://automacao-murici.onrender.com/google/callback"
)


LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"

LINKEDIN_PUBLISH_URL = "https://api.linkedin.com/v2/ugcPosts"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL nao configurado.")

    return psycopg.connect(DATABASE_URL)


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


def ensure_analytics_table():
    """
    Cria a estrutura de armazenamento das métricas do LinkedIn.

    Esta tabela fica preparada para receber os dados quando
    o acesso oficial ao Community Management API estiver disponível.
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS linkedin_post_metrics (
                    id BIGSERIAL PRIMARY KEY,

                    editorial_post_id BIGINT
                        REFERENCES editorial_posts(id),

                    linkedin_post_id TEXT NOT NULL,

                    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                    impressions BIGINT,
                    members_reached BIGINT,
                    reactions BIGINT,
                    comments BIGINT,
                    reposts BIGINT,
                    saves BIGINT,
                    clicks BIGINT,
                    follows BIGINT,

                    raw_payload JSONB,

                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
                ("Drive5",),
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
                ("Drive5",),
            )

            row = cur.fetchone()

            if not row:
                return None

            return row[0]


def google_tokens_from_database():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT access_token, refresh_token
                FROM google_accounts
                WHERE account_name = %s
                LIMIT 1
                """,
                ("Drive5",),
            )

            row = cur.fetchone()

            if not row:
                return None, None

            access_token = decrypt_value(row[0]) if row[0] else None
            refresh_token = decrypt_value(row[1]) if row[1] else None

            return access_token, refresh_token


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
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": commentary
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
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

    except Exception as error:
        return jsonify(
            {
                "status": "erro",
                "mensagem": str(error),
            }
        ), 500


@app.get("/crypto-test")
def crypto_test():
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

    except Exception as error:
        return jsonify(
            {
                "status": "erro",
                "mensagem": str(error),
            }
        ), 500


@app.get("/storage-test")
def storage_test():
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

    except Exception as error:
        return jsonify(
            {
                "status": "erro",
                "mensagem": str(error),
            }
        ), 500


@app.get("/linkedin/login")
def linkedin_login():
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
        "scope": "openid profile email w_member_social",
    }

    authorization_url = (
        LINKEDIN_AUTH_URL
        + "?"
        + urllib.parse.urlencode(params)
    )

    return redirect(authorization_url)


@app.get("/linkedin/callback")
def linkedin_callback():
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
                    "Drive5",
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
    if not GOOGLE_CLIENT_ID:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "GOOGLE_CLIENT_ID nao configurado.",
            }
        ), 500

    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state

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
                    "Drive5",
                    "google",
                    encrypted_access_token,
                    encrypted_refresh_token,
                    expires_in or 0,
                ),
            )

        conn.commit()

    session.pop("google_oauth_state", None)

    return jsonify(
        {
            "status": "google_autorizado",
            "projeto": "Automacao Murici",
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
    if not PUBLISH_SECRET:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "PUBLISH_SECRET nao configurado.",
            }
        ), 500

    provided_secret = request.headers.get(
        "X-Publish-Secret"
    )

    if not provided_secret:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Chave de publicacao nao informada.",
            }
        ), 401

    if not secrets.compare_digest(
        provided_secret,
        PUBLISH_SECRET
    ):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Chave de publicacao invalida.",
            }
        ), 403

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

    if not commentary or not isinstance(commentary, str):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "O campo content e obrigatorio.",
            }
        ), 400

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
                "mensagem": (
                    "Publicacao realizada no LinkedIn."
                ),
                "linkedin_post_id": post_id,
                "editorial_post_id": editorial_post_id,
            }
        )

    except Exception as error:
        return jsonify(
            {
                "status": "erro",
                "mensagem": str(error),
            }
        ), 500


@app.get("/analytics/prepare")
def analytics_prepare():
    """
    Rota protegida para preparar/verificar a estrutura
    de armazenamento das futuras metricas.
    """

    if not PUBLISH_SECRET:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "PUBLISH_SECRET nao configurado.",
            }
        ), 500

    provided_secret = request.headers.get(
        "X-Publish-Secret"
    )

    if not provided_secret:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Chave de publicacao nao informada.",
            }
        ), 401

    if not secrets.compare_digest(
        provided_secret,
        PUBLISH_SECRET
    ):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Chave de publicacao invalida.",
            }
        ), 403

    try:
        ensure_analytics_table()

        return jsonify(
            {
                "status": "ok",
                "mensagem": (
                    "Estrutura de armazenamento de "
                    "metricas preparada."
                ),
                "tabela": "linkedin_post_metrics",
            }
        )

    except Exception as error:
        return jsonify(
            {
                "status": "erro",
                "mensagem": str(error),
            }
        ), 500


@app.post("/analytics/record")
def analytics_record():
    """
    Recebe uma coleta de metricas e grava no PostgreSQL.

    Esta rota nao consulta o LinkedIn.
    Ela somente prepara o backend para receber dados
    provenientes de uma futura integracao oficial.
    """

    if not PUBLISH_SECRET:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "PUBLISH_SECRET nao configurado.",
            }
        ), 500

    provided_secret = request.headers.get(
        "X-Publish-Secret"
    )

    if not provided_secret:
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Chave de publicacao nao informada.",
            }
        ), 401

    if not secrets.compare_digest(
        provided_secret,
        PUBLISH_SECRET
    ):
        return jsonify(
            {
                "status": "erro",
                "mensagem": "Chave de publicacao invalida.",
            }
        ), 403

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

    if not linkedin_post_id:
        return jsonify(
            {
                "status": "erro",
                "mensagem": (
                    "linkedin_post_id e obrigatorio."
                ),
            }
        ), 400

    try:
        ensure_analytics_table()

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

                editorial_post_id = (
                    row[0] if row else None
                )

                cur.execute(
                    """
                    INSERT INTO linkedin_post_metrics (
                        editorial_post_id,
                        linkedin_post_id,
                        impressions,
                        members_reached,
                        reactions,
                        comments,
                        reposts,
                        saves,
                        clicks,
                        follows,
                        raw_payload
                    )
                    VALUES (
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
                        data.get("impressions"),
                        data.get("members_reached"),
                        data.get("reactions"),
                        data.get("comments"),
                        data.get("reposts"),
                        data.get("saves"),
                        data.get("clicks"),
                        data.get("follows"),
                        json.dumps(data),
                    ),
                )

                metric_id = cur.fetchone()[0]

            conn.commit()

        return jsonify(
            {
                "status": "ok",
                "mensagem": (
                    "Metricas armazenadas no PostgreSQL."
                ),
                "metric_id": metric_id,
                "editorial_post_id": editorial_post_id,
            }
        )

    except Exception as error:
        return jsonify(
            {
                "status": "erro",
                "mensagem": str(error),
            }
        ), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
    )
