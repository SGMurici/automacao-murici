"""Transactional identity onboarding helpers.

These functions do not send messages or commit transactions. The HTTP layer
owns delivery boundaries and commits only after each database state transition.
"""
import ipaddress
import uuid

import otp_core


class IdentityAuthConfigurationError(RuntimeError):
    pass


def required_pepper(name, environ):
    value = environ.get(name, "")
    if not isinstance(value, str) or len(value.encode("utf-8")) < 32:
        raise IdentityAuthConfigurationError(f"{name} ausente ou inválido.")
    return value.encode("utf-8")


def trusted_client_ip(access_route, environ):
    """Resolve the client IP from an explicitly configured trusted proxy chain.

    access_route is Werkzeug's parsed X-Forwarded-For chain. The configured
    count is the number of trusted proxies that append to its right side.
    """
    raw_hops = environ.get("OTP_TRUSTED_PROXY_HOPS", "")
    try:
        hops = int(raw_hops)
    except (TypeError, ValueError):
        raise IdentityAuthConfigurationError(
            "Cadeia de proxies confiáveis não configurada."
        ) from None
    if not 1 <= hops <= 8:
        raise IdentityAuthConfigurationError(
            "Quantidade de proxies confiáveis fora do limite."
        )
    route = list(access_route or [])
    if len(route) < hops:
        raise IdentityAuthConfigurationError(
            "Cadeia de IP encaminhado incompleta."
        )
    candidate = route[-hops]
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        raise IdentityAuthConfigurationError(
            "IP do cliente inválido na cadeia confiável."
        ) from None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.compressed


def reserve_request_limits(
    conn, normalized_identity, client_ip, device_id, purpose, rate_limit_pepper
):
    identity_hash = otp_core.hash_otp_rate_limit_dimension(
        "identity", normalized_identity, rate_limit_pepper
    )
    ip_hash = otp_core.hash_otp_rate_limit_dimension(
        "ip", client_ip, rate_limit_pepper
    )
    if not otp_core.reserve_otp_request_slot(
        conn, "identity", identity_hash, purpose,
        cooldown_seconds=60, window_seconds=3600, max_requests=5,
    ):
        return False
    if not otp_core.reserve_otp_request_slot(
        conn, "ip", ip_hash, purpose,
        cooldown_seconds=1, window_seconds=3600, max_requests=100,
    ):
        return False
    if device_id:
        device_hash = otp_core.hash_otp_rate_limit_dimension(
            "device", device_id, rate_limit_pepper
        )
        if not otp_core.reserve_otp_request_slot(
            conn, "device", device_hash, purpose,
            cooldown_seconds=60, window_seconds=3600, max_requests=10,
        ):
            return False
    return True


def reserve_verification_limits(
    conn, normalized_identity, client_ip, device_id, purpose, rate_limit_pepper
):
    """Use the same quota ledger with domain-separated verification buckets."""
    identity_hash = otp_core.hash_otp_rate_limit_dimension(
        "identity", normalized_identity, rate_limit_pepper, context="verify"
    )
    ip_hash = otp_core.hash_otp_rate_limit_dimension(
        "ip", client_ip, rate_limit_pepper, context="verify"
    )
    if not otp_core.reserve_otp_request_slot(
        conn, "identity", identity_hash, purpose,
        cooldown_seconds=1, window_seconds=3600, max_requests=10,
    ):
        return False
    if not otp_core.reserve_otp_request_slot(
        conn, "ip", ip_hash, purpose,
        cooldown_seconds=1, window_seconds=3600, max_requests=100,
    ):
        return False
    if device_id:
        device_hash = otp_core.hash_otp_rate_limit_dimension(
            "device", device_id, rate_limit_pepper, context="verify"
        )
        if not otp_core.reserve_otp_request_slot(
            conn, "device", device_hash, purpose,
            cooldown_seconds=1, window_seconds=3600, max_requests=20,
        ):
            return False
    return True


def find_email_identity(conn, identity_lookup_hash):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT i.id, i.user_id, i.verified_at, u.status
               FROM user_identities AS i
               JOIN app_users AS u ON u.id = i.user_id
               WHERE i.identity_type = 'email'
                 AND i.identity_lookup_hash = %s
               LIMIT 1""",
            (identity_lookup_hash,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "identity_id": row[0],
        "user_id": row[1],
        "verified_at": row[2],
        "user_status": row[3],
    }


def ensure_pending_email_identity(
    conn, identity_lookup_hash, identity_value_ciphertext
):
    """Create a pending user/identity or return the existing unique identity."""
    existing = find_email_identity(conn, identity_lookup_hash)
    if existing:
        return existing

    user_id = uuid.uuid4()
    identity_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app_users (id, status) VALUES (%s, 'pending')",
            (user_id,),
        )
        cur.execute(
            """INSERT INTO user_identities
               (id, user_id, identity_type, identity_lookup_hash,
                identity_value_ciphertext, is_primary)
               VALUES (%s, %s, 'email', %s, %s, TRUE)
               ON CONFLICT (identity_type, identity_lookup_hash) DO NOTHING
               RETURNING id, user_id""",
            (
                identity_id, user_id, identity_lookup_hash,
                identity_value_ciphertext,
            ),
        )
        inserted = cur.fetchone()
        if not inserted:
            cur.execute("DELETE FROM app_users WHERE id = %s", (user_id,))
    return find_email_identity(conn, identity_lookup_hash)


def latest_sent_challenge(conn, identity_lookup_hash, purpose):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, user_id
               FROM otp_challenges
               WHERE identity_type = 'email'
                 AND identity_lookup_hash = %s
                 AND purpose = %s
                 AND delivery_status = 'sent'
                 AND consumed_at IS NULL
                 AND expires_at > NOW()
               ORDER BY created_at DESC, id DESC
               LIMIT 1
               FOR UPDATE""",
            (identity_lookup_hash, purpose),
        )
        row = cur.fetchone()
    return row if row else None


def activate_verified_signup(
    conn, user_id, identity_lookup_hash, display_name=None
):
    """Activate a pending user and create their personal owner tenant atomically."""
    if display_name is not None:
        if not isinstance(display_name, str):
            raise ValueError("Nome de exibição inválido.")
        display_name = display_name.strip()
        if len(display_name) > 160:
            raise ValueError("Nome de exibição excede o limite.")
        if not display_name:
            display_name = None

    with conn.cursor() as cur:
        cur.execute(
            """UPDATE app_users
               SET status = 'active', updated_at = NOW()
               WHERE id = %s AND status = 'pending'
               RETURNING id""",
            (user_id,),
        )
        if not cur.fetchone():
            return None
        cur.execute(
            """UPDATE user_identities
               SET verified_at = NOW(), is_primary = TRUE
               WHERE user_id = %s
                 AND identity_type = 'email'
                 AND identity_lookup_hash = %s
                 AND verified_at IS NULL
               RETURNING id""",
            (user_id, identity_lookup_hash),
        )
        if not cur.fetchone():
            raise RuntimeError("Identidade pendente não encontrada.")
        tenant_id = uuid.uuid4()
        cur.execute(
            """INSERT INTO tenants (id, tenant_type, display_name)
               VALUES (%s, 'personal', %s)""",
            (tenant_id, display_name),
        )
        cur.execute(
            """INSERT INTO tenant_memberships
               (tenant_id, user_id, role, status)
               VALUES (%s, %s, 'owner', 'active')""",
            (tenant_id, user_id),
        )
    return tenant_id
