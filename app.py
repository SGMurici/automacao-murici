import os
import secrets
import urllib.parse
import urllib.request

from flask import Flask, jsonify, redirect, request, session

app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY")

LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

LINKEDIN_REDIRECT_URI = (
    "https://automacao-murici.onrender.com/linkedin/callback"
)

GOOGLE_REDIRECT_URI = (
    "https://automacao-murici.onrender.com/google/callback"
)

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

LINKEDIN_SCOPE = "openid profile email w_member_social"

GOOGLE_SCOPE = "https://www.googleapis.com/auth/drive.file"


@app.get("/")
def inicio():
    return jsonify({
        "projeto": "Automacao Murici",
        "status": "online",
        "mensagem": "Aplicacao inicial criada com sucesso."
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
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        return jsonify({
            "status": "erro",
            "mensagem": "DATABASE_URL nao configurada."
        }), 500

    try:
        import psycopg

        with psycopg.connect(
            database_url,
            connect_timeout=10
        ) as conn:
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
# LINKEDIN
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
            response.read().decode("utf-8")

        return jsonify({
            "projeto": "Automacao Murici",
            "status": "linkedin_autorizado",
            "mensagem": "Autorizacao do LinkedIn recebida com sucesso.",
            "resposta_linkedin": (
                "Token recebido e nao exibido por seguranca."
            )
        })

    except Exception:
        return jsonify({
            "erro": "Nao foi possivel concluir a autorizacao do LinkedIn."
        }), 502


# =========================================================
# GOOGLE DRIVE
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
            response.read().decode("utf-8")

        return jsonify({
            "projeto": "Automacao Murici",
            "status": "google_autorizado",
            "mensagem": "Autorizacao do Google recebida com sucesso.",
            "resposta_google": (
                "Token recebido e nao exibido por seguranca."
            )
        })

    except Exception:
        return jsonify({
            "erro": "Nao foi possivel concluir a autorizacao do Google."
        }), 502


# =========================================================
# EXECUCAO LOCAL
# =========================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )
