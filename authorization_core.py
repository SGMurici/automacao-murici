"""Tenant authorization and append-only consent/audit primitives.

All resource queries must still include tenant_id in their own WHERE clauses;
this module centralizes the membership check but is not a substitute for
resource-level ownership constraints.
"""
import json
import uuid


VALID_ROLES = {"owner", "admin", "member"}
VALID_CONSENT_DECISIONS = {"granted", "denied", "revoked"}
VALID_AUDIT_RESULTS = {"success", "denied", "failure"}


def active_tenant_role(conn, user_id, tenant_id, allowed_roles=None):
    if not user_id or not tenant_id:
        return None
    if allowed_roles is not None:
        roles = set(allowed_roles)
        if not roles or not roles.issubset(VALID_ROLES):
            raise ValueError("Papéis permitidos inválidos.")
    else:
        roles = None

    with conn.cursor() as cur:
        cur.execute(
            """SELECT role
               FROM tenant_memberships
               WHERE tenant_id = %s
                 AND user_id = %s
                 AND status = 'active'
               LIMIT 1""",
            (tenant_id, user_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    role = row[0]
    if role not in VALID_ROLES or (roles is not None and role not in roles):
        return None
    return role


def record_consent_event(
    conn, user_id, purpose, policy_version, decision, source,
    tenant_id=None, metadata=None,
):
    if not user_id or not purpose or not policy_version or not source:
        raise ValueError("Dados obrigatórios do consentimento ausentes.")
    if decision not in VALID_CONSENT_DECISIONS:
        raise ValueError("Decisão de consentimento inválida.")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("Metadados do consentimento devem ser um objeto.")
    event_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO consent_events
               (id, user_id, tenant_id, purpose, policy_version,
                decision, source, decided_at, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s::jsonb)
               RETURNING id""",
            (
                event_id, user_id, tenant_id, purpose, policy_version,
                decision, source, json.dumps(metadata or {}, separators=(",", ":")),
            ),
        )
        row = cur.fetchone()
    return row[0] if row else None


def record_audit_event(
    conn, action, result, actor_user_id=None, tenant_id=None,
    resource_type=None, resource_id=None, metadata=None,
):
    if not action or result not in VALID_AUDIT_RESULTS:
        raise ValueError("Evento de auditoria inválido.")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("Metadados de auditoria devem ser um objeto.")
    event_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO audit_events
               (id, actor_user_id, tenant_id, action, resource_type,
                resource_id, result, occurred_at, metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s::jsonb)
               RETURNING id""",
            (
                event_id, actor_user_id, tenant_id, action, resource_type,
                resource_id, result,
                json.dumps(metadata or {}, separators=(",", ":")),
            ),
        )
        row = cur.fetchone()
    return row[0] if row else None
