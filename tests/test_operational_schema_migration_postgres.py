"""PostgreSQL integration tests for the operational scheduler/analytics schema migration."""
import os
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg import sql


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0015_operational_scheduler_analytics_schema.sql"


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL não configurado")
class OperationalSchemaMigrationTests(unittest.TestCase):
    def setUp(self):
        self.schema = "operational_schema_" + uuid.uuid4().hex
        self.admin = psycopg.connect(DATABASE_URL, autocommit=True)
        self.admin.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema))
        )
        self.conn = psycopg.connect(DATABASE_URL, autocommit=True)
        self.conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema))
        )
        self.conn.execute(
            "CREATE TABLE editorial_posts (id BIGSERIAL PRIMARY KEY)"
        )

    def tearDown(self):
        self.conn.close()
        self.admin.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema))
        )
        self.admin.close()

    def apply_migration(self):
        source = MIGRATION.read_text(encoding="utf-8")
        for statement in source.split(";"):
            if statement.strip():
                self.conn.execute(statement, prepare=False)

    def _columns(self, table_name):
        return {
            row[0]
            for row in self.conn.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_schema = %s AND table_name = %s""",
                (self.schema, table_name),
            ).fetchall()
        }

    def _indexes(self, table_name):
        return {
            row[0]: row[1]
            for row in self.conn.execute(
                """SELECT indexname, indexdef FROM pg_indexes
                   WHERE schemaname = %s AND tablename = %s""",
                (self.schema, table_name),
            ).fetchall()
        }

    def test_fresh_schema_is_created_and_migration_is_idempotent(self):
        self.apply_migration()
        self.apply_migration()

        self.assertTrue({
            "id", "editorial_post_id", "linkedin_post_id", "measured_at",
            "impressions", "engagement_total", "source", "created_at",
        }.issubset(self._columns("linkedin_post_metrics")))
        self.assertTrue({
            "id", "started_at", "finished_at", "status",
            "posts_found", "posts_updated", "metrics_saved", "error_message",
        }.issubset(self._columns("linkedin_metrics_collection_runs")))
        self.assertTrue({
            "id", "post_number", "title", "content", "scheduled_for",
            "status", "attempts", "locked_at", "reconciliation_required_at",
            "published_at", "linkedin_post_id", "editorial_post_id",
            "error_message", "created_at", "updated_at",
        }.issubset(self._columns("linkedin_publish_queue")))

        metrics_indexes = self._indexes("linkedin_post_metrics")
        queue_indexes = self._indexes("linkedin_publish_queue")
        self.assertIn("linkedin_post_metrics_unique_snapshot", metrics_indexes)
        self.assertIn("uq_linkedin_publish_queue_reserved_post_number", queue_indexes)
        self.assertIn("idx_linkedin_publish_queue_expired_processing", queue_indexes)
        self.assertIn("'incerto'", queue_indexes["uq_linkedin_publish_queue_reserved_post_number"])

    def test_existing_queue_gets_missing_column_without_losing_legacy_fields(self):
        self.conn.execute(
            """CREATE TABLE linkedin_publish_queue (
                id BIGSERIAL PRIMARY KEY,
                post_number INTEGER,
                title TEXT,
                content TEXT NOT NULL,
                scheduled_for TIMESTAMPTZ NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'agendado',
                attempts INTEGER NOT NULL DEFAULT 0,
                locked_at TIMESTAMPTZ,
                published_at TIMESTAMPTZ,
                linkedin_post_id TEXT,
                editorial_post_id BIGINT REFERENCES editorial_posts(id) ON DELETE SET NULL,
                error_message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                drive_file_id TEXT
            )"""
        )
        self.conn.execute(
            """CREATE UNIQUE INDEX uq_linkedin_publish_queue_active_post_number
               ON linkedin_publish_queue(post_number)
               WHERE post_number IS NOT NULL
                 AND status IN ('agendado', 'processando', 'publicado')"""
        )

        self.apply_migration()

        columns = self._columns("linkedin_publish_queue")
        self.assertIn("reconciliation_required_at", columns)
        self.assertIn("drive_file_id", columns)
        indexes = self._indexes("linkedin_publish_queue")
        self.assertIn("uq_linkedin_publish_queue_active_post_number", indexes)
        self.assertIn("uq_linkedin_publish_queue_reserved_post_number", indexes)

        self.conn.execute(
            """INSERT INTO linkedin_publish_queue
               (post_number, content, scheduled_for, status)
               VALUES (42, 'uncertain fixture', NOW(), 'incerto')"""
        )
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.conn.execute(
                """INSERT INTO linkedin_publish_queue
                   (post_number, content, scheduled_for, status)
                   VALUES (42, 'duplicate fixture', NOW(), 'agendado')"""
            )


if __name__ == "__main__":
    unittest.main()
