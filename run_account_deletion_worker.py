"""CLI entry point for the gated account-deletion worker.

Configure DATABASE_URL and run:
    python run_account_deletion_worker.py

This is a deployable command, not an active production schedule. Configure a
dedicated Render Cron/worker only after the external deletion adapters are live.
"""
import json
import os
import sys

import psycopg

from account_deletion_worker import run_ready_deletions


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL não configurado.", file=sys.stderr)
        return 2

    result = run_ready_deletions(
        lambda: psycopg.connect(database_url, connect_timeout=10)
    )
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get("failed", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
