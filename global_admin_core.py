"""Platform-wide administrator checks, separate from tenant RBAC.

This module intentionally exposes no self-service grant or bootstrap operation.
Provisioning the first platform administrator is an out-of-band, audited operation.
"""


def is_active_global_admin(conn, user_id):
    """Return True only for an active user with an active global-admin grant."""
    if not user_id:
        return False

    with conn.cursor() as cur:
        cur.execute(
            """SELECT EXISTS (
                   SELECT 1
                   FROM global_administrators AS g
                   JOIN app_users AS u ON u.id = g.user_id
                   WHERE g.user_id = %s
                     AND g.status = 'active'
                     AND g.revoked_at IS NULL
                     AND u.status = 'active'
               )""",
            (user_id,),
        )
        row = cur.fetchone()

    return bool(row and row[0])


def require_global_admin(conn, user_id):
    """Raise PermissionError unless the user has an active platform grant."""
    if not is_active_global_admin(conn, user_id):
        raise PermissionError("Administrador global ativo obrigatório.")
    return True
