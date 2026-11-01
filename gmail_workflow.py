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


_RULES = (
    ("entrevista", ("entrevista", "interview", "agendar conversa", "marcar conversa", "meet with")),
    ("teste_seletivo", ("teste técnico", "teste tecnico", "avaliação técnica", "avaliacao tecnica", "case", "desafio técnico", "desafio tecnico")),
    ("proxima_etapa", ("próxima etapa", "proxima etapa", "next step", "avançou", "avancou", "parabéns", "parabens")),
    ("rejeicao", ("não seguiremos", "nao seguiremos", "não foi selecionado", "nao foi selecionado", "encerramos o processo", "not moving forward")),
    ("oferta", ("proposta salarial", "carta oferta", "offer letter", "oferta de emprego", "remuneração", "remuneracao")),
    ("documentos", ("documentação", "documentacao", "documentos", "cpf", "rg", "comprovante")),
    ("contato_recrutador", ("recrutamento", "recruiter", "talent acquisition", "rh", "recursos humanos")),
)


def classify_message(subject="", sender="", body=""):
    """Conservative keyword triage; never treats a heuristic as a decision."""
    text = " ".join((subject or "", sender or "", body or "")).lower()
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
        "snippet": message.get("snippet", ""),
        "body_text": body,
        "triage": classify_message(subject, sender, body),
    }
