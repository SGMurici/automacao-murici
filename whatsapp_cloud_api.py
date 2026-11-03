"""Isolated, allowlisted WhatsApp Cloud API test sender.

This module does not run automatically and is not wired to Flask routes or schedulers.
It can only send an approved test template when explicit test-mode environment
flags are enabled and the recipient is on the configured Meta test allowlist.
"""
import json
import os
import re
import urllib.error
import urllib.request


class WhatsAppConfigurationError(RuntimeError):
    pass


class WhatsAppSendError(RuntimeError):
    pass


def _enabled(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_number(value):
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if not 8 <= len(digits) <= 15:
        raise ValueError("Destinatário inválido: informe número internacional em formato E.164.")
    return digits


def _test_recipients(env):
    raw = env.get("WHATSAPP_TEST_RECIPIENTS", "")
    return {
        _normalize_number(item)
        for item in raw.split(",")
        if item.strip()
    }


def build_email_summary_message(summary):
    """Create a short preview using aggregate Gmail metrics only."""
    if not isinstance(summary, dict):
        raise ValueError("Resumo inválido.")
    total = summary.get("total", 0)
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError("Total agregado inválido.")

    categories = summary.get("categories", {})
    priorities = summary.get("priorities", {})
    if not isinstance(categories, dict) or not isinstance(priorities, dict):
        raise ValueError("Métricas agregadas inválidas.")

    lines = ["Resumo de e-mails — Automação Murici", f"Mensagens analisadas: {total}"]
    for label, values in (("Categorias", categories), ("Prioridades", priorities)):
        safe_values = []
        for key, count in sorted(values.items()):
            if (not isinstance(key, str) or isinstance(count, bool)
                    or not isinstance(count, int) or count < 0):
                continue
            safe_key = re.sub(r"[^a-zA-Z0-9_À-ÿ -]", "", key)[:48]
            if safe_key:
                safe_values.append(f"{safe_key}: {count}")
        if safe_values:
            lines.append(label + ": " + "; ".join(safe_values))
    # Never include message subjects, senders, snippets, bodies, or identifiers.
    return "\n".join(lines)[:3000]


def send_test_template(recipient, *, env=None, opener=None):
    """Send only a template through Meta's test sender to an allowlisted recipient."""
    env = os.environ if env is None else env
    if not _enabled(env.get("WHATSAPP_TEST_MODE")):
        raise WhatsAppConfigurationError("Ambiente de testes do WhatsApp não está habilitado.")
    if not _enabled(env.get("WHATSAPP_TEST_SEND_ENABLED")):
        raise WhatsAppConfigurationError("Envio de teste está desabilitado por padrão.")

    normalized_recipient = _normalize_number(recipient)
    if normalized_recipient not in _test_recipients(env):
        raise WhatsAppConfigurationError("Destinatário não consta na lista autorizada de testes.")

    token = env.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_number_id = env.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    api_version = env.get("WHATSAPP_GRAPH_API_VERSION", "").strip()
    if not token or not phone_number_id:
        raise WhatsAppConfigurationError("Credenciais do remetente de teste não configuradas.")
    if not re.fullmatch(r"v[0-9]+\\.[0-9]+", api_version):
        raise WhatsAppConfigurationError("Versão Graph API ausente ou inválida.")

    template_name = env.get("WHATSAPP_TEST_TEMPLATE", "hello_world").strip()
    if not re.fullmatch(r"[a-zA-Z0-9_]+", template_name):
        raise WhatsAppConfigurationError("Nome do template de teste inválido.")
    language = env.get("WHATSAPP_TEST_TEMPLATE_LANGUAGE", "en_US").strip()
    if not re.fullmatch(r"[a-zA-Z_]+", language):
        raise WhatsAppConfigurationError("Idioma do template de teste inválido.")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": normalized_recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
        },
    }
    request = urllib.request.Request(
        f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    send = opener or urllib.request.urlopen
    try:
        with send(request, timeout=20) as response:
            status = getattr(response, "status", 200)
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise WhatsAppSendError(f"Meta Graph API retornou HTTP {error.code}.") from None
    except (urllib.error.URLError, TimeoutError):
        raise WhatsAppSendError("Falha de conexão com a Meta Graph API.") from None
    except (ValueError, json.JSONDecodeError):
        raise WhatsAppSendError("Resposta inválida da Meta Graph API.") from None

    if status not in (200, 201):
        raise WhatsAppSendError(f"Meta Graph API retornou HTTP {status}.")
    messages = response_data.get("messages", [])
    if not messages or not isinstance(messages, list):
        raise WhatsAppSendError("A Meta não confirmou a aceitação da mensagem.")
    # Do not return recipient, token, message IDs, or provider response body.
    return {"status": "accepted", "provider": "meta", "message_count": 1}
