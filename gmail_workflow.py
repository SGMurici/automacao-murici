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
    code_context = re.compile(
        r"(?:c[oó]digo|code|login|verification|verifica[cç][aã]o|"
        r"seguran[cç]a|tempor[aá]rio|one[- ]time|passcode|otp|senha)",
        re.IGNORECASE,
    )
    number = re.compile(r"(?<!\d)\d{4,8}(?!\d)")

    def replace_if_sensitive(match):
        start, end = match.span()
        context = value[max(0, start - 100):min(len(value), end + 100)]
        return "[CÓDIGO TEMPORÁRIO OCULTO]" if code_context.search(context) else match.group(0)

    return number.sub(replace_if_sensitive, value)


_RULES = (
    ("entrevista", ("entrevista", "interview", "agendar conversa", "marcar conversa", "meet with")),
    ("teste_seletivo", ("teste técnico", "teste tecnico", "testes online", "teste online", "aprovação testes online", "aprovacao testes online", "avaliação técnica", "avaliacao tecnica", "estudo de caso", "desafio técnico", "desafio tecnico", "aprovação nos testes", "aprovacao nos testes", "aprovado nos testes", "aprovada nos testes")),
    ("proxima_etapa", ("próxima etapa", "proxima etapa", "next step", "avançou para a próxima etapa", "avancou para a proxima etapa", "parabéns, você avançou", "parabens voce avancou", "convidamos para a próxima etapa", "convidamos para próxima etapa", "convidamos para a proxima etapa", "foi aprovado para a próxima etapa", "foi aprovada para a próxima etapa")),
    ("rejeicao", ("não seguiremos", "nao seguiremos", "não foi selecionado", "nao foi selecionado", "encerramos o processo", "not moving forward")),
    ("oferta", ("proposta salarial", "carta oferta", "offer letter", "oferta de emprego", "remuneração", "remuneracao")),
    ("contato_recrutador", ("recrutamento", "recruiter", "talent acquisition", "recursos humanos")),
)

# Recognize explicit online assessment wording; keep next-stage detection phrase-specific to avoid generic congratulation matches.
# Career-process classifications belong in the personal (SG) and
# professional (Drive1) mailboxes. Drive2 is primarily for website accounts;
# Drive5 is reserved for automation operations.
_CAREER_MAILBOXES = {"sg", "drive1"}
_CAREER_ONLY_CATEGORIES = {
    "entrevista", "teste_seletivo", "proxima_etapa", "rejeicao",
    "oferta", "contato_recrutador",
}


_DOCUMENT_CONTEXT_MARKERS = (
    "envie os documentos", "enviar os documentos", "anexe os documentos",
    "anexar os documentos", "encaminhe os documentos", "encaminhar os documentos",
    "documentação necessária", "documentacao necessaria", "documentos pendentes",
    "documentos para admissão", "documentos para admissao", "required documents",
    "submit your documents", "upload documents", "your documents are ready",
    "documento disponível", "documento disponivel", "documentos recebidos",
    "comprovante disponível", "comprovante disponivel", "download your document",
    "documento de identidade", "cópia do rg", "copia do rg",
    "número do cpf", "numero do cpf",
)


def _has_explicit_document_context(text):
    return any(marker in text for marker in _DOCUMENT_CONTEXT_MARKERS)


def classify_message(subject="", sender="", body="", account=None):
    """Classify messages; career-process categories are allowed for SG and Drive1."""
    sender_text = (sender or "").lower()
    subject_text = (subject or "").lower()
    body_text = (body or "").lower()
    text = " ".join((subject_text, sender_text, body_text))
    account_key = (account or "").strip().casefold()
    is_career_mailbox = account_key in _CAREER_MAILBOXES

    security_markers = (
        "código para continuar entrando sem uma senha",
        "código de login",
        "one-time passcode",
        "verification code",
        "security alert",
        "alerta de segurança",
        "alerta de seguranca",
        "novo login no spotify",
        "new login to spotify",
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

    # Account lifecycle and service messages are distinct from recruiting and marketing.
    signup_markers = (
        "confirme seu e-mail", "confirmar seu email", "verify your email",
        "verifique seu endereço de e-mail", "verifique seu endereco de email",
        "ative sua conta", "ativar sua conta", "activate your account",
        "confirm your account", "email address confirmation",
    )
    if any(term in text for term in signup_markers):
        return {"categories": ["cadastro_validacao"], "priority": "media",
                "requires_human_review": True, "external_action_allowed": False}

    recovery_markers = (
        "redefinir sua senha", "redefinição de senha", "redefinicao de senha",
        "recuperar sua senha", "recuperação de conta", "recuperacao de conta",
        "password reset", "reset your password", "recover your account",
        "account recovery",
    )
    if any(term in text for term in recovery_markers):
        return {"categories": ["recuperacao_acesso"], "priority": "alta",
                "requires_human_review": True, "external_action_allowed": False}

    marketing_markers = (
        "newsletter", "boletim informativo", "ofertas exclusivas",
        "promoções para você", "promocoes para voce", "novidades do mês",
        "novidades do mes", "dicas e novidades",
    )
    if any(term in text for term in marketing_markers):
        return {"categories": ["marketing_newsletter"], "priority": "normal",
                "requires_human_review": True, "external_action_allowed": False}

    service_markers = (
        "sua assinatura foi renovada", "your subscription has been renewed",
        "fatura disponível", "fatura disponivel", "invoice available",
        "pagamento aprovado", "payment successful", "pedido confirmado",
        "order confirmed", "recibo da sua compra", "your receipt",
        "atualização da sua conta", "atualizacao da sua conta",
        "your account has been updated",
    )
    if any(term in text for term in service_markers):
        return {"categories": ["notificacao_servico"], "priority": "media",
                "requires_human_review": True, "external_action_allowed": False}

    vacancy_markers = ("alerta de vaga", "vagas que combinam", "novas vagas", "job alert", "jobs for you", "vaga recomendada")
    if is_career_mailbox and "indeed" in sender_text and any(term in text for term in vacancy_markers):
        return {"categories": ["alerta_vaga"], "priority": "media", "requires_human_review": True, "external_action_allowed": False}

    matches = []
    if _has_explicit_document_context(text):
        matches.append("documentos")
    for category, terms in _RULES:
        if category in _CAREER_ONLY_CATEGORIES and not is_career_mailbox:
            continue
        if any(term in text for term in terms):
            matches.append(category)

    if "oferta" in matches:
        priority = "alta"
    elif any(item in matches for item in ("entrevista", "teste_seletivo", "proxima_etapa")):
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
        "date": _redact_one_time_codes(headers.get("date", "")),
        "from": _redact_one_time_codes(sender),
        "subject": _redact_one_time_codes(subject),
        "snippet": _redact_one_time_codes(message.get("snippet", "")),
        "body_text": _redact_one_time_codes(body),
        "triage": classify_message(subject, sender, body, account=account),
    }


def merge_triage_summaries(summaries):
    """Merge account summaries using aggregate counts only."""
    merged = {
        "total": 0,
        "categories": {},
        "priorities": {},
        "unclassified_signals": {},
    }
    for summary in summaries or []:
        if not isinstance(summary, dict):
            continue
        total = summary.get("total", 0)
        if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
            merged["total"] += total
        for field in ("categories", "priorities", "unclassified_signals"):
            counts = summary.get(field, {})
            if not isinstance(counts, dict):
                continue
            for name, count in counts.items():
                if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                    merged[field][name] = merged[field].get(name, 0) + count
    for field in ("categories", "priorities", "unclassified_signals"):
        merged[field] = dict(sorted(merged[field].items()))
    return merged


def summary_only_requested(value=None):
    """Default to privacy-safe aggregate output; details require explicit opt-in."""
    if value is None:
        return True
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


_UNCLASSIFIED_DIAGNOSTIC_SIGNALS = {
    "cadastro_validacao": (
        "confirme seu e-mail", "confirmar seu email", "verify your email",
        "verifique seu endereço de e-mail", "verifique seu endereco de email",
        "ative sua conta", "ativar sua conta", "activate your account",
        "confirm your account", "email address confirmation",
    ),
    "recuperacao_acesso": (
        "redefinir sua senha", "redefinição de senha", "redefinicao de senha",
        "recuperar sua senha", "recuperação de conta", "recuperacao de conta",
        "password reset", "reset your password", "recover your account",
        "account recovery",
    ),
    "marketing_newsletter": (
        "newsletter", "boletim informativo", "ofertas exclusivas",
        "promoções para você", "promocoes para voce", "novidades do mês",
        "novidades do mes", "dicas e novidades",
    ),
    "notificacao_servico": (
        "sua assinatura foi renovada", "your subscription has been renewed",
        "fatura disponível", "fatura disponivel", "invoice available",
        "pagamento aprovado", "payment successful", "pedido confirmado",
        "order confirmed", "recibo da sua compra", "your receipt",
        "atualização da sua conta", "atualizacao da sua conta",
        "your account has been updated",
    ),
}


def summarize_triage_items(items):
    """Return aggregate counts only; never include message content or identifiers."""
    category_counts = {}
    priority_counts = {}
    diagnostic_counts = {key: 0 for key in _UNCLASSIFIED_DIAGNOSTIC_SIGNALS}
    for item in items or []:
        triage = item.get("triage") or {}
        categories = triage.get("categories") or ["nao_classificado"]
        for category in categories:
            category_counts[category] = category_counts.get(category, 0) + 1
        priority = triage.get("priority", "normal")
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
        if "nao_classificado" in categories:
            text = " ".join((
                str(item.get("subject") or ""),
                str(item.get("from") or ""),
                str(item.get("snippet") or ""),
                str(item.get("body_text") or ""),
            )).casefold()
            for signal, terms in _UNCLASSIFIED_DIAGNOSTIC_SIGNALS.items():
                if any(term in text for term in terms):
                    diagnostic_counts[signal] += 1
    return {
        "total": len(items or []),
        "categories": dict(sorted(category_counts.items())),
        "priorities": dict(sorted(priority_counts.items())),
        "unclassified_signals": {
            key: count for key, count in sorted(diagnostic_counts.items()) if count
        },
    }
