"""Conservative worker for deletion requests whose external gates are complete.

This worker only performs the final PostgreSQL identity purge. Provider, device,
object-store and backup deletion adapters must independently complete their
steps before a request becomes eligible.
"""
import logging

import account_deletion_core


logger = logging.getLogger(__name__)
WORKER_ADVISORY_LOCK_KEY = 83746292
EXTERNAL_DELETION_STEP_COUNT = 4
DEFAULT_BATCH_SIZE = 20
MAX_BATCH_SIZE = 100


def run_ready_deletions(connection_factory, batch_size=DEFAULT_BATCH_SIZE):
    """Process up to batch_size requests with all four external gates satisfied.

    connection_factory must return a psycopg connection. The session-level
    advisory lock prevents overlapping worker instances. Each purge runs in its
    own transaction so one failed request does not roll back another request.
    """
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise ValueError("batch_size deve ser um inteiro.")
    if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
        raise ValueError("batch_size fora do intervalo permitido.")

    conn = connection_factory()
    lock_acquired = False
    processed = 0
    failed = 0
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (WORKER_ADVISORY_LOCK_KEY,))
            row = cur.fetchone()
            lock_acquired = bool(row and row[0])
        conn.commit()

        if not lock_acquired:
            return {"status": "busy", "processed": 0, "failed": 0}

        with conn.cursor() as cur:
            cur.execute(
                """SELECT r.id
                   FROM account_deletion_requests AS r
                   WHERE r.status IN ('requested', 'processing')
                     AND (
                       SELECT COUNT(*)
                       FROM account_deletion_steps AS s
                       WHERE s.request_id = r.id
                         AND s.system_key <> 'primary_database'
                         AND s.status IN ('completed', 'not_applicable')
                     ) = %s
                   ORDER BY r.requested_at ASC
                   LIMIT %s""",
                (EXTERNAL_DELETION_STEP_COUNT, batch_size),
            )
            request_ids = [row[0] for row in cur.fetchall()]
        conn.commit()

        for request_id in request_ids:
            try:
                with conn.transaction():
                    completed = account_deletion_core.process_primary_database_deletion(
                        conn, request_id
                    )
                if completed:
                    processed += 1
            except Exception:
                failed += 1
                logger.exception("Falha ao processar solicitação de exclusão %s", request_id)

        return {
            "status": "completed" if failed == 0 else "completed_with_errors",
            "processed": processed,
            "failed": failed,
        }
    finally:
        if lock_acquired:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_advisory_unlock(%s)",
                        (WORKER_ADVISORY_LOCK_KEY,),
                    )
                conn.commit()
            except Exception:
                logger.exception("Falha ao liberar advisory lock do worker de exclusão")
        conn.close()
