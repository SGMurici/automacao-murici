"""Privacy-preserving account-deletion request and receipt primitives.

This module queues deletion; it deliberately does not claim that data has been
purged until every configured system has independently confirmed completion.
"""
import hashlib
import secrets
import uuid


CONFIRMATION_PHRASE = "EXCLUIR MINHA CONTA"
RECEIPT_BYTES = 32
RECEIPT_TTL_DAYS = 90
DELETION_SYSTEMS = (
    "primary_database",
    "connected_providers",
    "app_storage",
    "backups",
    "legal_retention",
)


class DeletionAlreadyRequested(Exception):
    """An open deletion request already exists for this account."""


class AccountNotEligibleForDeletion(Exception):
    """The account is not active and cannot start a new deletion request."""


def hash_deletion_receipt(receipt):
    if not isinstance(receipt, str) or len(receipt) < 32:
        raise ValueError("Comprovante de exclusão inválido.")
    return hashlib.sha256(receipt.encode("utf-8")).hexdigest()


def request_account_deletion(conn, user_id):
    """Lock account access, revoke all sessions and enqueue a deletion request.

    The raw receipt is returned once. Only its SHA-256 digest is persisted.
    The caller owns and commits the database transaction.
    """
    request_id = str(uuid.uuid4())
    receipt = secrets.token_urlsafe(RECEIPT_BYTES)
    receipt_hash = hash_deletion_receipt(receipt)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM app_users WHERE id = %s FOR UPDATE",
            (user_id,),
        )
        user = cur.fetchone()
        if not user or user[0] != "active":
            if user and user[0] == "deletion_pending":
                raise DeletionAlreadyRequested()
            raise AccountNotEligibleForDeletion()

        cur.execute(
            """INSERT INTO account_deletion_requests
               (id, user_id, receipt_hash, status, requested_at,
                receipt_expires_at)
               VALUES (%s, %s, %s, 'requested', NOW(),
                       NOW() + (%s * INTERVAL '1 day'))""",
            (request_id, user_id, receipt_hash, RECEIPT_TTL_DAYS),
        )
        cur.executemany(
            """INSERT INTO account_deletion_steps (request_id, system_key)
               VALUES (%s, %s)""",
            [(request_id, system) for system in DELETION_SYSTEMS],
        )
        cur.execute(
            """UPDATE app_users
               SET status = 'deletion_pending', updated_at = NOW()
               WHERE id = %s AND status = 'active'""",
            (user_id,),
        )
        if cur.rowcount != 1:
            raise AccountNotEligibleForDeletion()

    # Revocation is part of the same transaction as the deletion request.
    import identity_core
    identity_core.revoke_all_sessions(conn, user_id)
    return {"request_id": request_id, "receipt": receipt}


def get_deletion_status(conn, receipt):
    """Return a minimal status view using the one-time deletion receipt."""
    try:
        receipt_hash = hash_deletion_receipt(receipt)
    except ValueError:
        return None

    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, status, requested_at, started_at, completed_at
               FROM account_deletion_requests
               WHERE receipt_hash = %s
                 AND receipt_expires_at > NOW()""",
            (receipt_hash,),
        )
        request_row = cur.fetchone()
        if not request_row:
            return None
        cur.execute(
            """SELECT system_key, status, started_at, completed_at
               FROM account_deletion_steps
               WHERE request_id = %s
               ORDER BY system_key""",
            (request_row[0],),
        )
        steps = cur.fetchall()

    def iso(value):
        return value.isoformat() if value else None

    return {
        "request_id": str(request_row[0]),
        "status": request_row[1],
        "requested_at": iso(request_row[2]),
        "started_at": iso(request_row[3]),
        "completed_at": iso(request_row[4]),
        "steps": [
            {
                "system": row[0],
                "status": row[1],
                "started_at": iso(row[2]),
                "completed_at": iso(row[3]),
            }
            for row in steps
        ],
    }


def complete_deletion_step(
    conn, request_id, system_key, evidence_reference=None, not_applicable=False
):
    """Record an independently verified external deletion step.

    This is an internal worker primitive, not a public client endpoint.
    Evidence references must be opaque IDs, never personal data or credentials.
    """
    if system_key not in DELETION_SYSTEMS or system_key == "primary_database":
        raise ValueError("Etapa de exclusão inválida para confirmação externa.")
    if evidence_reference is not None and (
        not isinstance(evidence_reference, str) or len(evidence_reference) > 160
    ):
        raise ValueError("Referência de evidência inválida.")
    status = "not_applicable" if not_applicable else "completed"
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE account_deletion_steps
               SET status = %s, completed_at = NOW(),
                   evidence_reference = %s, failure_code = NULL
               WHERE request_id = %s AND system_key = %s
               RETURNING id""",
            (status, evidence_reference, request_id, system_key),
        )
        if not cur.fetchone():
            raise ValueError("Solicitação ou etapa de exclusão não encontrada.")
        cur.execute(
            """UPDATE account_deletion_requests
               SET status = 'processing', started_at = COALESCE(started_at, NOW())
               WHERE id = %s AND status IN ('requested', 'blocked')""",
            (request_id,),
        )
    return True


def process_primary_database_deletion(conn, request_id):
    """Purge known user-linked PostgreSQL identity data after external steps finish.

    The request receipt and minimal progress record remain as a non-identifying
    proof of execution. Shared tenants are preserved for their other members.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT user_id, status
               FROM account_deletion_requests
               WHERE id = %s
               FOR UPDATE""",
            (request_id,),
        )
        request_row = cur.fetchone()
        if not request_row:
            raise ValueError("Solicitação de exclusão não encontrada.")
        user_id, request_status = request_row
        if request_status == "completed":
            return True
        if not user_id:
            raise ValueError("Solicitação sem vínculo de usuário antes da conclusão.")

        cur.execute(
            """SELECT system_key, status
               FROM account_deletion_steps
               WHERE request_id = %s""",
            (request_id,),
        )
        step_statuses = {row[0]: row[1] for row in cur.fetchall()}
        required_external = set(DELETION_SYSTEMS) - {"primary_database"}
        if any(
            step_statuses.get(system) not in {"completed", "not_applicable"}
            for system in required_external
        ):
            return False

        cur.execute(
            """SELECT identity_type, identity_lookup_hash
               FROM user_identities
               WHERE user_id = %s""",
            (user_id,),
        )
        identities = cur.fetchall()
        if identities:
            cur.executemany(
                """DELETE FROM otp_challenges
                   WHERE identity_type = %s AND identity_lookup_hash = %s""",
                identities,
            )

        cur.execute(
            "SELECT id FROM tenants WHERE tenant_type = 'personal' AND id IN "
            "(SELECT tenant_id FROM tenant_memberships WHERE user_id = %s)",
            (user_id,),
        )
        personal_tenant_ids = [row[0] for row in cur.fetchall()]

        # Remove user-attributed audit records rather than retaining metadata
        # that could identify the deleted account.
        cur.execute("DELETE FROM audit_events WHERE actor_user_id = %s", (user_id,))
        cur.execute("DELETE FROM app_users WHERE id = %s", (user_id,))
        if cur.rowcount != 1:
            raise ValueError("Registro de usuário não encontrado durante a exclusão.")

        if personal_tenant_ids:
            cur.execute(
                """DELETE FROM tenants AS t
                   WHERE t.id = ANY(%s)
                     AND t.tenant_type = 'personal'
                     AND NOT EXISTS (
                         SELECT 1 FROM tenant_memberships AS m
                         WHERE m.tenant_id = t.id
                     )""",
                (personal_tenant_ids,),
            )

        cur.execute(
            """UPDATE account_deletion_steps
               SET status = 'completed', completed_at = NOW(), failure_code = NULL
               WHERE request_id = %s AND system_key = 'primary_database'""",
            (request_id,),
        )
        cur.execute(
            """UPDATE account_deletion_requests
               SET status = 'completed', completed_at = NOW(), user_id = NULL,
                   failure_code = NULL
               WHERE id = %s""",
            (request_id,),
        )
    return True
