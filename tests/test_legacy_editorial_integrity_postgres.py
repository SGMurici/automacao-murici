"""PostgreSQL integration tests for the legacy editorial observation FK."""
import os
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg import sql


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0007_observation_editorial_post_fk.sql"


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL não configurado")
class EditorialObservationForeignKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "editorial_fk_test_" + uuid.uuid4().hex
        cls.admin_conn = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.admin_conn.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema))
        )
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema))
        )
        conn.execute("CREATE TABLE editorial_posts (id BIGINT PRIMARY KEY)")
        conn.execute(
            """CREATE TABLE engagement_post_observations (
                   id BIGINT PRIMARY KEY,
                   editorial_post_id BIGINT NULL
               )"""
        )
        for statement in MIGRATION.read_text(encoding="utf-8").split(";"):
            if statement.strip():
                conn.execute(statement, prepare=False)
        conn.close()

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
        self.conn.commit()

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def test_orphan_observation_reference_is_rejected(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with self.conn.transaction():
                self.conn.execute(
                    "INSERT INTO engagement_post_observations (id, editorial_post_id) VALUES (1, 999)"
                )

    def test_deleting_editorial_post_preserves_observation_and_nulls_reference(self):
        self.conn.execute("INSERT INTO editorial_posts (id) VALUES (10)")
        self.conn.execute(
            "INSERT INTO engagement_post_observations (id, editorial_post_id) VALUES (20, 10)"
        )
        self.conn.commit()

        self.conn.execute("DELETE FROM editorial_posts WHERE id = 10")
        self.conn.commit()

        row = self.conn.execute(
            "SELECT editorial_post_id FROM engagement_post_observations WHERE id = 20"
        ).fetchone()
        self.assertEqual(row, (None,))


if __name__ == "__main__":
    unittest.main()
