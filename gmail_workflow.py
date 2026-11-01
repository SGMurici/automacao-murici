"""Pure helpers for extracting and triaging Gmail API messages.

This module deliberately does not send mail or create calendar events. Every
suggested response/decision must be reviewed by a person before an external
action is taken.
"""
import base64
import re
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._hidden:
            self._hidden -= 1

    def handle_data(self, data):
        if not self._hidden and data.strip():
            self.parts.append(data.strip())


def _decode_data(value):
    if not value:
        return ""
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return raw.decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def _walk_parts(payload):
    if not isinstance(payload, dict):
        return
    body = payload.get("body") or {}
    if body.get("data"):
        yield payload.get("mimeType", ""), _decode_data(body["data"])
    for part in payload.get("parts") or []:
        yield from _walk_parts(part)


def extract_message_text(message):
    """Extract readable text from a Gmail API message resource."""
    payload = message.get("payload") or {}
    chunks = list(_walk_parts(payload))
    plain = [text for mime, text in chunks if mime == "text/plain" and text.strip()]
    if plain:
        return "\n\n".join(plain)[:30000]
    html = [text for mime, text in chunks if mime == "text/html" and text.strip()]
    if html:
        parser = _TextExtractor()
        parser.feed("\n".join(html))
        return "\n".join(parser.parts)[:30000]
    return (message.get("snippet") or "").strip()[:30000]


def _header_map(message):
    headers = (message.get("payload") or {}).get("headers") or []
    return {
        str(item.get("name", "")).lower(): str(item.get("value", ""))
        for item in headers if isinstance(item, dict) and item.get("name")
    }


def _redact_one_time_codes(text):
    """Hide short-lived numeric login codes before returning message bodies."""
    value = text or ""
    code_context = re.compile(r"(?:c[oó]digo|code|login|verification|senha)", re.IGNORECASE)
    number = re.compile(r"(?<!\\d)\\d{6,8}(?!\\d)")

    def replace_if_sensitive(match):
        start, end = match.span()
        context = value[max(0, start - 100):min(len(value), end + 100)]
        return "[CÓDIGO TEMPORÁRIO OCULTO]" if code_context.search(context) else match.group(0)

    return number.sub(replace_if_sensitive, value)

_RULES = (
    ("entrevista", ("entrevista", "interview", "agendar conversa", "marcar conversa", "meet with")),
    ("teste_seletivo", ("teste técnico", "teste tecnico", "avaliação técnica", "avaliacao tecnica", "case", "desafio técnico", "desafio tecnico")),
    ("proxima_etapa", ("próxima etapa", "proxima etapa", "next step", "avançou", "avancou", "parabéns", "parabens")),
    ("rejeicao", ("não seguiremos", "nao seguiremos", "não foi selecionado", "nao foi selecionado", "encerramos o processo", "not moving forward")),
    ("oferta", ("proposta salarial", "carta oferta", "offer letter", "oferta de emprego", "remuneração", "remuneracao")),
    ("documentos", ("documentação", "documentacao", "documentos", "cpf", "rg", "comprovante")),
    ("contato_recrutador", ("recrutamento", "recruiter", "talent acquisition", "recursos humanos")),
)


def classify_message(subject="", sender="", body=""):
    """Prioritize security and infrastructure alerts over broad job keywords."""
    sender_text = (sender or "").lower()
    subject_text = (subject or "").lower()
    body_text = (body or "").lower()
    text = " ".join((subject_text, sender_text, body_text))

    security_markers = (
        "código para continuar entrando sem uma senha",
        "código de login",
        "one-time passcode",
        "verification code",
        "security alert",
        "atividade suspeita",
        "atividade de segurança",
        "você compartilhou alguns dados da sua conta do google",
    )
    if any(term in text for term in security_markers) or (
        "noreply-accounts@google.com" in sender_text
        and ("conta do google" in subject_text or "sign-in" in subject_text)
    ):
        return {
            "categories": ["seguranca_conta"],
            "priority": "alta",
            "requires_human_review": True,
            "external_action_allowed": False,
        }

    operational_markers = (
        "cron job failure", "cron job failed", "exited with status",
        "deploy failed", "deployment failed", "service unavailable",
        "falha no cron", "falha no serviço", "erro no deploy",
    )
    if any(term in text for term in operational_markers) or (
        "render" in sender_text and ("failure" in subject_text or "failed" in subject_text)
    ):
        return {
            "categories": ["alerta_operacional"],
            "priority": "alta",
            "requires_human_review": True,
            "external_action_allowed": False,
        }

    matches = []
    for category, terms in _RULES:
        if any(term in text for term in terms):
            matches.append(category)

    if "oferta" in matches:
        priority = "alta"
    elif any(item in matches for item in ("entrevista", "teste_seletivo", "proxima_etapa", "documentos")):
        priority = "alta"
    elif matches:
        priority = "media"
    else:
        priority = "normal"
    return {
        "categories": matches or ["nao_classificado"],
        "priority": priority,
        "requires_human_review": True,
        "external_action_allowed": False,
    }


def build_triage_item(message, account):
    headers = _header_map(message)
    body = extract_message_text(message)
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    return {
        "account": account,
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "date": headers.get("date", ""),
        "from": sender,
        "subject": subject,
        "snippet": _redact_one_time_codes(message.get("snippet", "")),
        "body_text": _redact_one_time_codes(body),
        "triage": classify_message(subject, sender, body),
    }
