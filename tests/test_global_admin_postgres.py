"""PostgreSQL integration tests for platform-admin separation from tenant RBAC."""
import os
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg import sql

import global_admin_core


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL não configurado")
class GlobalAdministratorPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "global_admin_" + uuid.uuid4().hex
        cls.admin = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.admin.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema))
        )
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema))
        )
        try:
            for migration_name in (
                "0002_identity_core.sql",
                "0012_global_administrators.sql",
            ):
                source = (ROOT / "migrations" / migration_name).read_text(
                    encoding="utf-8"
                )
                for statement in source.split(";"):
                    if statement.strip():
                        conn.execute(statement, prepare=False)
        except Exception:
            cls.admin.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema))
            )
            raise
        finally:
            conn.close()

    @classmethod
    def tearDownClass(cls):
        cls.admin.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(cls.schema))
        )
        cls.admin.close()

    def setUp(self):
        self.conn = psycopg.connect(DATABASE_URL)
        self.conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema))
        )
        self.user_id = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO app_users (id, status) VALUES (%s, 'active')",
            (self.user_id,),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def test_tenant_admin_does_not_become_global_admin(self):
        tenant_id = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO tenants (id, tenant_type) VALUES (%s, 'personal')",
            (tenant_id,),
        )
        self.conn.execute(
            """INSERT INTO tenant_memberships (tenant_id, user_id, role, status)
               VALUES (%s, %s, 'admin', 'active')""",
            (tenant_id, self.user_id),
        )
        self.conn.commit()
        self.assertFalse(global_admin_core.is_active_global_admin(self.conn, self.user_id))

    def test_active_global_grant_is_recognized_only_for_active_user(self):
        self.conn.execute(
            """INSERT INTO global_administrators (user_id, grant_reason)
               VALUES (%s, 'controlled bootstrap test')""",
            (self.user_id,),
        )
        self.conn.commit()
        self.assertTrue(global_admin_core.is_active_global_admin(self.conn, self.user_id))
        self.conn.execute(
            "UPDATE app_users SET status = 'suspended' WHERE id = %s",
            (self.user_id,),
        )
        self.conn.commit()
        self.assertFalse(global_admin_core.is_active_global_admin(self.conn, self.user_id))

    def test_revoked_grant_is_not_authorized(self):
        self.conn.execute(
            """INSERT INTO global_administrators
               (user_id, status, grant_reason, revoked_at)
               VALUES (%s, 'revoked', 'revocation test', NOW())""",
            (self.user_id,),
        )
        self.conn.commit()
        self.assertFalse(global_admin_core.is_active_global_admin(self.conn, self.user_id))


if __name__ == "__main__":
    unittest.main()
