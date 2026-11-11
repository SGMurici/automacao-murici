"""Provider-neutral transactional email adapter using authenticated SMTP.

This module never sends mail at import time. It requires explicit SMTP
configuration and enforces transport encryption. Exceptions are sanitized so
provider responses and credentials are not exposed to API callers or logs.
"""
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

from identity_lookup import normalize_identity


def normalize_email_address(value):
    return normalize_identity("email", value)


PURPOSE_SUBJECTS = {
    "signup": "Confirme seu e-mail",
    "login": "Seu código de acesso",
    "verify_identity": "Confirme sua identidade",
    "recovery": "Código de recuperação da conta",
}


class EmailDeliveryError(RuntimeError):
    """Sanitized delivery/configuration failure."""


def _required_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise EmailDeliveryError("Serviço de e-mail não configurado.")
    return value


def _bool_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _smtp_config():
    host = _required_env("SMTP_HOST")
    try:
        sender = normalize_email_address(_required_env("SMTP_FROM"))
        port = int(os.getenv("SMTP_PORT", "587"))
        timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
    except (TypeError, ValueError):
        raise EmailDeliveryError("Configuração SMTP inválida.") from None
    if not 1 <= port <= 65535 or not 1 <= timeout <= 30:
        raise EmailDeliveryError("Configuração SMTP inválida.")
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    if bool(username) != bool(password):
        raise EmailDeliveryError("Credenciais SMTP incompletas.")
    use_ssl = _bool_env("SMTP_USE_SSL", False)
    use_tls = _bool_env("SMTP_USE_TLS", True)
    if use_ssl and use_tls:
        raise EmailDeliveryError("Configuração de transporte SMTP inválida.")
    if not use_ssl and not use_tls:
        raise EmailDeliveryError("SMTP exige transporte TLS.")
    return {
        "host": host,
        "port": port,
        "timeout": timeout,
        "sender": sender,
        "username": username,
        "password": password,
        "use_ssl": use_ssl,
        "use_tls": use_tls,
    }


def validate_email_config():
    """Validate required SMTP settings without opening a network connection."""
    _smtp_config()
    return True


def build_otp_message(to_email, code, purpose, expires_minutes=10, sender=None):
    """Build a plain-text operational message without opening a network connection."""
    recipient = normalize_email_address(to_email)
    sender = normalize_email_address(sender or _required_env("SMTP_FROM"))
    if purpose not in PURPOSE_SUBJECTS:
        raise ValueError("Finalidade de e-mail inválida.")
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{8}", code, flags=re.ASCII):
        raise ValueError("Código de verificação inválido.")
    if isinstance(expires_minutes, bool) or not isinstance(expires_minutes, int) or not 1 <= expires_minutes <= 15:
        raise ValueError("Validade do código inválida.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"KAPPA — {PURPOSE_SUBJECTS[purpose]}"
    message["Message-ID"] = make_msgid()
    message.set_content(
        "Olá,\n\n"
        f"Seu código de verificação do KAPPA é: {code}\n\n"
        f"Ele expira em {expires_minutes} minutos. Se você não solicitou este código, "
        "ignore esta mensagem. Não compartilhe o código com ninguém.\n\n"
        "Esta mensagem é exclusivamente operacional e não contém publicidade.\n"
        "KAPPA"
    )
    return message


def send_otp_email(to_email, code, purpose, expires_minutes=10):
    """Send one OTP email over mandatory TLS; return a non-secret message ID."""
    config = _smtp_config()
    recipient = normalize_email_address(to_email)
    message = build_otp_message(
        recipient, code, purpose, expires_minutes, sender=config["sender"]
    )

    client = None
    try:
        context = ssl.create_default_context()
        if config["use_ssl"]:
            client = smtplib.SMTP_SSL(
                config["host"], config["port"], timeout=config["timeout"], context=context
            )
        else:
            client = smtplib.SMTP(config["host"], config["port"], timeout=config["timeout"])
            client.ehlo()
            client.starttls(context=context)
            client.ehlo()
        if config["username"]:
            client.login(config["username"], config["password"])
        refused = client.send_message(message, from_addr=config["sender"], to_addrs=[recipient])
        if refused:
            raise EmailDeliveryError("Provedor recusou o destinatário.")
        return {"message_id": message["Message-ID"]}
    except EmailDeliveryError:
        raise
    except (smtplib.SMTPException, OSError, ssl.SSLError, TimeoutError):
        raise EmailDeliveryError("Não foi possível entregar o e-mail de verificação.") from None
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                pass
