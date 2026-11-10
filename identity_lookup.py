"""Canonicalize customer identities and derive privacy-preserving lookup digests.

The caller must keep the lookup pepper in the backend secret manager and share
the same key across all application instances.
"""
import hashlib
import hmac
import re
import unicodedata


VALID_IDENTITY_TYPES = {"email", "phone"}
MIN_PEPPER_BYTES = 32
_EMAIL_LOCAL_FORBIDDEN = set("<>(),;:\"[]\\\\")
_EMAIL_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_PHONE_E164 = re.compile(r"\+[1-9][0-9]{7,14}\Z")


def normalize_identity(identity_type, value):
    """Return a deterministic email or E.164 phone representation.

    Email local-parts are NFC-normalized and case-folded. Domains are converted
    to IDNA ASCII and lower-case. Phone numbers must include an explicit
    international country code; formatting separators are removed.
    """
    if identity_type not in VALID_IDENTITY_TYPES:
        raise ValueError("Tipo de identidade inválido.")
    if not isinstance(value, str):
        raise ValueError("Identidade deve ser texto.")
    value = value.strip()
    if not value:
        raise ValueError("Identidade vazia.")

    if identity_type == "email":
        if value.count("@") != 1 or any(char.isspace() for char in value):
            raise ValueError("E-mail inválido.")
        local, domain = value.rsplit("@", 1)
        local = unicodedata.normalize("NFC", local).casefold()
        if (
            not local
            or len(local.encode("utf-8")) > 64
            or local.startswith(".")
            or local.endswith(".")
            or ".." in local
            or any(ord(char) < 33 or ord(char) == 127 for char in local)
            or any(char in _EMAIL_LOCAL_FORBIDDEN for char in local)
        ):
            raise ValueError("Parte local do e-mail inválida.")
        try:
            domain = domain.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as error:
            raise ValueError("Domínio de e-mail inválido.") from error
        labels = domain.split(".")
        if (
            not domain
            or len(domain) > 253
            or len(labels) < 2
            or any(not _EMAIL_DOMAIN_LABEL.fullmatch(label) for label in labels)
        ):
            raise ValueError("Domínio de e-mail inválido.")
        normalized = f"{local}@{domain}"
        if len(normalized.encode("utf-8")) > 254:
            raise ValueError("E-mail excede o tamanho permitido.")
        return normalized

    # Validate display syntax before stripping separators. Without this check,
    # malformed strings can collapse into a valid-looking E.164 number.
    if not re.fullmatch(r"\+[1-9][0-9]*(?: ?\([0-9]+\))?(?:[ .-]?[0-9]+)*", value):
        raise ValueError("Formatação de telefone inválida.")
    compact = re.sub(r"[ .()-]", "", value)
    if not _PHONE_E164.fullmatch(compact):
        raise ValueError("Telefone deve estar em formato internacional E.164.")
    return compact


def hash_identity_lookup(identity_type, value, pepper):
    """Return a 32-byte HMAC-SHA256 digest of the normalized identity."""
    if not isinstance(pepper, bytes) or len(pepper) < MIN_PEPPER_BYTES:
        raise ValueError("Identity lookup pepper deve conter ao menos 32 bytes.")
    normalized = normalize_identity(identity_type, value)
    message = (
        b"kappa:identity-lookup:v1\x00"
        + identity_type.encode("ascii")
        + b"\x00"
        + normalized.encode("utf-8")
    )
    return hmac.new(pepper, message, hashlib.sha256).digest()
