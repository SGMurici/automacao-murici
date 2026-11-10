"""PostgreSQL integration tests for stale scheduler lease recovery."""
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql

import app as application


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0008_scheduler_lease_recovery.sql"


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL não configurado")
class SchedulerLeaseRecoveryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "scheduler_recovery_" + uuid.uuid4().hex
        cls.admin_conn = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.admin_conn.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema))
        )
        cls.conn = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema))
        )
        cls.conn.execute(
            """CREATE TABLE linkedin_publish_queue (
                id BIGSERIAL PRIMARY KEY,
                status VARCHAR(30) NOT NULL,
                post_number INTEGER,
                locked_at TIMESTAMPTZ,
                linkedin_post_id TEXT,
                reconciliation_required_at TIMESTAMPTZ,
                error_message TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""
        )
        source = MIGRATION.read_text(encoding="utf-8")
        for statement in source.split(";"):
            if statement.strip():
                cls.conn.execute(statement, prepare=False)
        cls.conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.admin_conn.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(cls.schema))
        )
        cls.admin_conn.close()

    def setUp(self):
        self.conn = psycopg.connect(DATABASE_URL)
        self.conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema))
        )
        self.conn.execute("TRUNCATE linkedin_publish_queue RESTART IDENTITY")
        self.conn.commit()

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def _application_db_connection(self):
        connection = psycopg.connect(DATABASE_URL)
        connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema))
        )
        return connection

    def test_expired_processing_rows_become_uncertain_not_retryable(self):
        stale_id = self.conn.execute(
            """INSERT INTO linkedin_publish_queue
               (status, locked_at, linkedin_post_id)
               VALUES ('processando', NOW() - INTERVAL '20 minutes', 'urn:li:share:known')
               RETURNING id"""
        ).fetchone()[0]
        fresh_id = self.conn.execute(
            """INSERT INTO linkedin_publish_queue (status, locked_at)
               VALUES ('processando', NOW() - INTERVAL '2 minutes') RETURNING id"""
        ).fetchone()[0]
        unlocked_id = self.conn.execute(
            "INSERT INTO linkedin_publish_queue (status) VALUES ('processando') RETURNING id"
        ).fetchone()[0]
        scheduled_id = self.conn.execute(
            "INSERT INTO linkedin_publish_queue (status) VALUES ('agendado') RETURNING id"
        ).fetchone()[0]
        self.conn.commit()

        with patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        ):
            recovered = application.scheduler_recover_expired_processing(lease_minutes=15)

        self.assertEqual(recovered, 1)
        stale = self.conn.execute(
            """SELECT status, linkedin_post_id, reconciliation_required_at,
                      locked_at, error_message
               FROM linkedin_publish_queue WHERE id = %s""",
            (stale_id,),
        ).fetchone()
        self.assertEqual(stale[0], "incerto")
        self.assertEqual(stale[1], "urn:li:share:known")
        self.assertIsNotNone(stale[2])
        self.assertIsNone(stale[3])
        self.assertIn("RECONCILIACAO NECESSARIA", stale[4])

        statuses = self.conn.execute(
            "SELECT id, status FROM linkedin_publish_queue ORDER BY id"
        ).fetchall()
        self.assertEqual(
            dict(statuses),
            {
                stale_id: "incerto",
                fresh_id: "processando",
                unlocked_id: "processando",
                scheduled_id: "agendado",
            },
        )

    def test_uncertain_state_keeps_editorial_number_reserved(self):
        self.conn.execute(
            "INSERT INTO linkedin_publish_queue (post_number, status) VALUES (42, 'incerto')"
        )
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.conn.execute(
                "INSERT INTO linkedin_publish_queue (post_number, status) VALUES (42, 'agendado')"
            )
        self.conn.rollback()

    def test_recovery_rejects_invalid_lease_duration(self):
        for value in (0, -1, True, 1.5, "15"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    application.scheduler_recover_expired_processing(value)


if __name__ == "__main__":
    unittest.main()
