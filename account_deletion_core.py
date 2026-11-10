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
        cur.execute(
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
