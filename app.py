import os
import secrets
import urllib.parse
import urllib.request
import urllib.error
import json

from flask import Flask, jsonify, redirect, request, session
from cryptography.fernet import Fernet

app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY")

LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

DATABASE_URL = os.environ.get("DATABASE_URL")
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
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

LINKEDIN_SCOPE = "openid profile email w_member_social"

GOOGLE_SCOPE = "https://www.googleapis.com/auth/drive.file"

LINKEDIN_VERSION = "202606"


# =========================================================
# CRIPTOGRAFIA
# =========================================================

def encrypt_token(value):
    if not value:
        return None

    if not TOKEN_ENCRYPTION_KEY:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY nao configurada."
        )

    cipher = Fernet(
        TOKEN_ENCRYPTION_KEY.encode("utf-8")
    )

    return cipher.encrypt(
        value.encode("utf-8")
    ).decode("utf-8")


def decrypt_token(value):
    if not value:
        return None

    if not TOKEN_ENCRYPTION_KEY:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY nao configurada."
        )

    cipher = Fernet(
        TOKEN_ENCRYPTION_KEY.encode("utf-8")
    )

    return cipher.decrypt(
        value.encode("utf-8")
    ).decode("utf-8")


# =========================================================
# BANCO DE DADOS
# =========================================================

def get_database_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL nao configurada."
        )

    import psycopg

    return psycopg.connect(
        DATABASE_URL,
        connect_timeout=10
    )


# =========================================================
# PAGINA INICIAL
# =========================================================

@app.get("/")
def inicio():
    return jsonify({
        "projeto": "Automacao Murici",
        "status": "online",
        "mensagem": "Aplicacao funcionando."
    })


@app.get("/health")
def health():
    return jsonify({
        "status": "ok"
    }), 200


# =========================================================
# TESTE DO POSTGRESQL
# =========================================================

@app.get("/db-test")
def db_test():
    try:
        with get_database_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

        return jsonify({
            "status": "ok",
            "mensagem": "Conexao com PostgreSQL funcionando."
        })

    except Exception:
        return jsonify({
            "status": "erro",
            "mensagem": "Nao foi possivel conectar ao PostgreSQL."
        }), 500


# =========================================================
# TESTE DA CRIPTOGRAFIA
# =========================================================

@app.get("/crypto-test")
def crypto_test():
    if not TOKEN_ENCRYPTION_KEY:
        return jsonify({
            "status": "erro",
            "mensagem": "TOKEN_ENCRYPTION_KEY nao configurada."
        }), 500

    try:
        original = "teste-interno"

        encrypted = encrypt_token(original)
        decrypted = decrypt_token(encrypted)

        if decrypted != original:
            return jsonify({
                "status": "erro",
                "mensagem": "Teste de criptografia falhou."
            }), 500

        return jsonify({
            "status": "ok",
            "mensagem": "Criptografia funcionando corretamente."
        })

    except Exception:
        return jsonify({
            "status": "erro",
            "mensagem": "Nao foi possivel testar a criptografia."
        }), 500


# =========================================================
# TESTE DE GRAVACAO SEGURA NO BANCO
# =========================================================

@app.get("/storage-test")
def storage_test():
    try:
        encrypted_value = encrypt_token(
            "teste-interno-de-armazenamento"
        )

        with get_database_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS security_test (
                        id BIGSERIAL PRIMARY KEY,
                        encrypted_value TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)

                cur.execute("""
                    INSERT INTO security_test (
                        encrypted_value
                    )
                    VALUES (%s)
                    RETURNING id
                """, (encrypted_value,))

                row = cur.fetchone()

            conn.commit()

        if not row:
            return jsonify({
                "status": "erro",
                "mensagem": "Nao foi possivel gravar o teste."
            }), 500

        return jsonify({
            "status": "ok",
            "mensagem": "Gravacao criptografada no PostgreSQL funcionando.",
            "teste_id": row[0]
        })

    except Exception:
        return jsonify({
            "status": "erro",
            "mensagem": "Nao foi possivel executar o teste de armazenamento."
        }), 500


# =========================================================
# LINKEDIN - LOGIN
# =========================================================

@app.get("/linkedin/login")
def linkedin_login():
    if not app.secret_key:
        return jsonify({
            "erro": "FLASK_SECRET_KEY nao configurada."
        }), 500

    if not LINKEDIN_CLIENT_ID:
        return jsonify({
            "erro": "LINKEDIN_CLIENT_ID nao configurada."
        }), 500

    state = secrets.token_urlsafe(32)

    session["linkedin_state"] = state

    params = {
        "response_type": "code",
        "client_id": LINKEDIN_CLIENT_ID,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "state": state,
        "scope": LINKEDIN_SCOPE
    }

    authorization_url = (
        LINKEDIN_AUTH_URL
        + "?"
        + urllib.parse.urlencode(params)
    )

    return redirect(authorization_url)


# =========================================================
# LINKEDIN - CALLBACK
# =========================================================

@app.get("/linkedin/callback")
def linkedin_callback():
    returned_state = request.args.get("state")
    saved_state = session.pop("linkedin_state", None)

    if not returned_state or returned_state != saved_state:
        return jsonify({
            "erro": "Falha de seguranca: state invalido."
        }), 400

    if request.args.get("error"):
        return jsonify({
            "erro": request.args.get("error"),
            "descricao": request.args.get("error_description")
        }), 400

    code = request.args.get("code")

    if not code:
        return jsonify({
            "erro": "Codigo de autorizacao nao recebido."
        }), 400

    if not LINKEDIN_CLIENT_ID or not LINKEDIN_CLIENT_SECRET:
        return jsonify({
            "erro": "Credenciais do LinkedIn nao configuradas."
        }), 500

    token_data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": LINKEDIN_REDIRECT_URI,
        "client_id": LINKEDIN_CLIENT_ID,
        "client_secret": LINKEDIN_CLIENT_SECRET
    }).encode("utf-8")

    token_request = urllib.request.Request(
        LINKEDIN_TOKEN_URL,
        data=token_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            token_request,
            timeout=20
        ) as response:
            token_response = response.read().decode("utf-8")

        token_json = json.loads(token_response)

        access_token = token_json.get("access_token")
        expires_in = token_json.get("expires_in")

        if not access_token:
            return jsonify({
                "erro": "LinkedIn nao retornou access_token."
            }), 502

        # -------------------------------------------------
        # OBTEM O MEMBER ID PELO OPENID CONNECT
        # -------------------------------------------------

        userinfo_request = urllib.request.Request(
            LINKEDIN_USERINFO_URL,
            headers={
                "Authorization": "Bearer " + access_token
            },
            method="GET"
        )

        with urllib.request.urlopen(
            userinfo_request,
            timeout=20
        ) as response:
            userinfo_response = response.read().decode("utf-8")

        userinfo_json = json.loads(userinfo_response)

        linkedin_member_id = userinfo_json.get("sub")

        if not linkedin_member_id:
            return jsonify({
                "erro": "LinkedIn nao retornou o identificador do membro."
            }), 502

        # -------------------------------------------------
        # CRIPTOGRAFA O TOKEN
        # -------------------------------------------------

        encrypted_access_token = encrypt_token(
            access_token
        )

        # -------------------------------------------------
        # ARMAZENA TOKEN + MEMBER ID
        # -------------------------------------------------

        with get_database_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    INSERT INTO linkedin_accounts (
                        account_name,
                        linkedin_member_id,
                        access_token,
                        token_expires_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        NOW() + (%s * INTERVAL '1 second')
                    )
                    ON CONFLICT (account_name)
                    DO UPDATE SET
                        linkedin_member_id =
                            EXCLUDED.linkedin_member_id,
                        access_token =
                            EXCLUDED.access_token,
                        token_expires_at =
                            EXCLUDED.token_expires_at,
                        updated_at =
                            NOW()
                """, (
                    "LinkedIn Principal",
                    linkedin_member_id,
                    encrypted_access_token,
                    expires_in or 0
                ))

            conn.commit()

        return jsonify({
            "projeto": "Automacao Murici",
            "status": "linkedin_autorizado",
            "mensagem": "LinkedIn autorizado, Member ID obtido e token armazenado com criptografia.",
            "token_recebido": True,
            "member_id_obtido": True,
            "expira_em": expires_in
        })

    except Exception:
        return jsonify({
            "erro": "Nao foi possivel concluir a autorizacao do LinkedIn."
        }), 502


# =========================================================
# LINKEDIN - DADOS DA CONTA
# =========================================================

def get_linkedin_account():
    with get_database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    linkedin_member_id,
                    access_token
                FROM linkedin_accounts
                WHERE account_name = %s
                LIMIT 1
            """, (
                "LinkedIn Principal",
            ))

            row = cur.fetchone()

    if not row:
        raise RuntimeError(
            "Conta LinkedIn Principal nao encontrada."
        )

    linkedin_member_id = row[0]
    encrypted_access_token = row[1]

    if not linkedin_member_id:
        raise RuntimeError(
            "LinkedIn Member ID nao encontrado."
        )

    if not encrypted_access_token:
        raise RuntimeError(
            "Token do LinkedIn nao encontrado."
        )

    access_token = decrypt_token(
        encrypted_access_token
    )

    return linkedin_member_id, access_token


# =========================================================
# LINKEDIN - PUBLICACAO INTERNA
# =========================================================

def publish_linkedin_text(commentary):
    if not commentary:
        raise RuntimeError(
            "Texto da publicacao nao informado."
        )

    if len(commentary) > 3000:
        raise RuntimeError(
            "O texto excede o limite de 3000 caracteres."
        )

    linkedin_member_id, access_token = (
        get_linkedin_account()
    )

    author_urn = (
        "urn:li:person:"
        + linkedin_member_id
    )

    payload = {
        "author": author_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False
    }

    request_data = json.dumps(
        payload
    ).encode("utf-8")

    post_request = urllib.request.Request(
        LINKEDIN_POSTS_URL,
        data=request_data,
        headers={
            "Authorization": "Bearer " + access_token,
            "X-Restli-Protocol-Version": "2.0.0",
            "Linkedin-Version": LINKEDIN_VERSION,
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            post_request,
            timeout=30
        ) as response:

            response_body = (
                response.read()
                .decode("utf-8")
            )

            post_id = response.headers.get(
                "x-restli-id"
            )

            return {
                "status_code": response.status,
                "post_id": post_id,
                "response_body": response_body
            }

    except urllib.error.HTTPError as error:
        error_body = (
            error.read()
            .decode("utf-8")
        )

        raise RuntimeError(
            "LinkedIn retornou erro HTTP "
            + str(error.code)
            + ": "
            + error_body
        )


# =========================================================
# LINKEDIN - PUBLICACAO PROTEGIDA
# =========================================================

@app.post("/linkedin/publish")
def linkedin_publish():
    if not PUBLISH_SECRET:
        return jsonify({
            "status": "erro",
            "mensagem": "PUBLISH_SECRET nao configurado."
        }), 500

    provided_secret = request.headers.get(
        "X-Publish-Secret"
    )

    if not provided_secret:
        return jsonify({
            "status": "erro",
            "mensagem": "Chave de publicacao nao informada."
        }), 401

    if not secrets.compare_digest(
        provided_secret,
        PUBLISH_SECRET
    ):
        return jsonify({
            "status": "erro",
            "mensagem": "Chave de publicacao invalida."
        }), 403

    if not request.is_json:
        return jsonify({
            "status": "erro",
            "mensagem": "A requisicao deve utilizar JSON."
        }), 400

    data = request.get_json(
        silent=True
    )

    if not isinstance(data, dict):
        return jsonify({
            "status": "erro",
            "mensagem": "JSON invalido."
        }), 400

    commentary = data.get(
        "content"
    )

    if not commentary or not isinstance(
        commentary,
        str
    ):
        return jsonify({
            "status": "erro",
            "mensagem": "O campo 'content' e obrigatorio."
        }), 400

    commentary = commentary.strip()

    if not commentary:
        return jsonify({
            "status": "erro",
            "mensagem": "O campo 'content' nao pode estar vazio."
        }), 400

    if len(commentary) > 3000:
        return jsonify({
            "status": "erro",
            "mensagem": "O texto excede o limite de 3000 caracteres."
        }), 400

    post_title = data.get(
        "title"
    )

    post_number = data.get(
        "post_number"
    )

    try:
        publication = publish_linkedin_text(
            commentary
        )

        linkedin_post_id = publication.get(
            "post_id"
        )

        with get_database_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    INSERT INTO editorial_posts (
                        post_number,
                        title,
                        content,
                        status,
                        published_at,
                        linkedin_post_id
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        NOW(),
                        %s
                    )
                    RETURNING id
                """, (
                    post_number,
                    post_title,
                    commentary,
                    "publicado",
                    linkedin_post_id
                ))

                row = cur.fetchone()

            conn.commit()

        return jsonify({
            "projeto": "Automacao Murici",
            "status": "publicado",
            "mensagem": "Publicacao realizada no LinkedIn e registrada no banco.",
            "editorial_post_id": row[0],
            "linkedin_post_id": linkedin_post_id
        }), 201

    except Exception as error:
        return jsonify({
            "projeto": "Automacao Murici",
            "status": "erro",
            "mensagem": "Nao foi possivel publicar no LinkedIn.",
            "detalhe": str(error)
        }), 502


# =========================================================
# GOOGLE DRIVE - LOGIN
# =========================================================

@app.get("/google/login")
def google_login():
    if not app.secret_key:
        return jsonify({
            "erro": "FLASK_SECRET_KEY nao configurada."
        }), 500

    if not GOOGLE_CLIENT_ID:
        return jsonify({
            "erro": "GOOGLE_CLIENT_ID nao configurada."
        }), 500

    state = secrets.token_urlsafe(32)

    session["google_state"] = state

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }

    authorization_url = (
        GOOGLE_AUTH_URL
        + "?"
        + urllib.parse.urlencode(params)
    )

    return redirect(authorization_url)


# =========================================================
# GOOGLE DRIVE - CALLBACK
# =========================================================

@app.get("/google/callback")
def google_callback():
    returned_state = request.args.get("state")
    saved_state = session.pop("google_state", None)

    if not returned_state or returned_state != saved_state:
        return jsonify({
            "erro": "Falha de seguranca: state Google invalido."
        }), 400

    if request.args.get("error"):
        return jsonify({
            "erro": request.args.get("error"),
            "descricao": request.args.get("error_description")
        }), 400

    code = request.args.get("code")

    if not code:
        return jsonify({
            "erro": "Codigo de autorizacao Google nao recebido."
        }), 400

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({
            "erro": "Credenciais Google nao configuradas."
        }), 500

    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }).encode("utf-8")

    token_request = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=token_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            token_request,
            timeout=20
        ) as response:
            token_response = response.read().decode("utf-8")

        token_json = json.loads(token_response)

        access_token = token_json.get("access_token")
        refresh_token = token_json.get("refresh_token")
        expires_in = token_json.get("expires_in")

        if not access_token:
            return jsonify({
                "erro": "Google nao retornou access_token."
            }), 502

        encrypted_access_token = encrypt_token(
            access_token
        )

        encrypted_refresh_token = None

        if refresh_token:
            encrypted_refresh_token = encrypt_token(
                refresh_token
            )

        with get_database_connection() as conn:
            with conn.cursor() as cur:

                cur.execute("""
                    INSERT INTO google_accounts (
                        account_name,
                        access_token,
                        refresh_token,
                        token_expires_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        NOW() + (%s * INTERVAL '1 second')
                    )
                    ON CONFLICT (account_name)
                    DO UPDATE SET
                        access_token =
                            EXCLUDED.access_token,
                        refresh_token =
                            COALESCE(
                                EXCLUDED.refresh_token,
                                google_accounts.refresh_token
                            ),
                        token_expires_at =
                            EXCLUDED.token_expires_at,
                        updated_at =
                            NOW()
                """, (
                    "Drive5",
                    encrypted_access_token,
                    encrypted_refresh_token,
                    expires_in or 0
                ))

            conn.commit()

        return jsonify({
            "projeto": "Automacao Murici",
            "status": "google_autorizado",
            "mensagem": "Google autorizado e token armazenado com criptografia.",
            "token_recebido": True,
            "refresh_token_recebido": bool(refresh_token),
            "expira_em": expires_in
        })

    except Exception:
        return jsonify({
            "erro": "Nao foi possivel concluir a autorizacao do Google."
        }), 502


# =========================================================
# EXECUCAO
# =========================================================

if __name__ == "__main__":
    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
