"""PostgreSQL integration tests for the identity migrations.

The suite uses an isolated schema and never touches the configured public schema.
Set TEST_DATABASE_URL to enable it; local runs without PostgreSQL skip cleanly.
"""
import hashlib
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from unittest.mock import patch

import app as application
import identity_core
import authorization_core
import account_deletion_core
import drive_backup_oauth
import drive_backup_connections
import otp_core


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = (
    ROOT / "migrations" / "0001_oauth_states.sql",
    ROOT / "migrations" / "0002_identity_core.sql",
    ROOT / "migrations" / "0003_account_deletion.sql",
    ROOT / "migrations" / "0004_customer_drive_oauth.sql",
    ROOT / "migrations" / "0005_otp_request_limits.sql",
    ROOT / "migrations" / "0006_session_authentication_freshness.sql",
    ROOT / "migrations" / "0012_global_administrators.sql",
)


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL não configurado")
class IdentityMigrationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "identity_test_" + uuid.uuid4().hex
        cls.admin_conn = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.admin_conn.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema))
        )
        cls.conn = psycopg.connect(DATABASE_URL, autocommit=True)
        cls.conn.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema))
        )
        try:
            for migration in MIGRATIONS:
                source = migration.read_text(encoding="utf-8")
                for statement in source.split(";"):
                    if statement.strip():
                        cls.conn.execute(statement, prepare=False)
        except Exception:
            cls.conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema))
            )
            cls.conn.close()
            cls.admin_conn.close()
            raise
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
        self.user_id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()
        self.conn.execute(
            "INSERT INTO app_users (id, status) VALUES (%s, 'active')",
            (self.user_id,),
        )
        self.conn.execute(
            "INSERT INTO tenants (id, tenant_type) VALUES (%s, 'personal')",
            (self.tenant_id,),
        )
        self.conn.execute(
            """INSERT INTO tenant_memberships
               (tenant_id, user_id, role, status)
               VALUES (%s, %s, 'owner', 'active')""",
            (self.tenant_id, self.user_id),
        )

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def _application_db_connection(self):
        connection = psycopg.connect(DATABASE_URL)
        connection.execute(
            sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema))
        )
        return connection

    def test_oauth_state_is_hashed_and_consumed_only_once(self):
        raw_state = "integration-oauth-state-" + uuid.uuid4().hex
        browser_id = "browser-" + uuid.uuid4().hex

        with patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        ):
            application.create_server_oauth_state("google", raw_state, browser_id)

            stored_hash = self.conn.execute(
                "SELECT state_hash FROM oauth_states WHERE browser_session_id = %s",
                (browser_id,),
            ).fetchone()[0]
            self.assertEqual(stored_hash.strip(), hashlib.sha256(raw_state.encode()).hexdigest())
            self.assertNotEqual(stored_hash.strip(), raw_state)

            first = application.consume_server_oauth_state("google", raw_state, browser_id)
            second = application.consume_server_oauth_state("google", raw_state, browser_id)

        self.assertEqual(first, {"provider": "google", "account_name": None})
        self.assertIsNone(second)

    def test_oauth_state_is_bound_to_provider_and_browser(self):
        raw_state = "bound-oauth-state-" + uuid.uuid4().hex
        browser_id = "browser-" + uuid.uuid4().hex

        with patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        ):
            application.create_server_oauth_state("linkedin", raw_state, browser_id)
            self.assertIsNone(
                application.consume_server_oauth_state("google", raw_state, browser_id)
            )
            self.assertIsNone(
                application.consume_server_oauth_state("linkedin", raw_state, "other-browser")
            )
            valid = application.consume_server_oauth_state("linkedin", raw_state, browser_id)

        self.assertEqual(valid, {"provider": "linkedin", "account_name": None})

    def test_expired_oauth_state_cannot_be_consumed(self):
        raw_state = "expired-oauth-state-" + uuid.uuid4().hex
        state_hash = hashlib.sha256(raw_state.encode()).hexdigest()
        browser_id = "browser-" + uuid.uuid4().hex
        self.conn.execute(
            """INSERT INTO oauth_states
               (state_hash, provider, browser_session_id, created_at, expires_at)
               VALUES (%s, 'google', %s, NOW() - INTERVAL '20 minutes',
                       NOW() - INTERVAL '10 minutes')""",
            (state_hash, browser_id),
        )
        self.conn.commit()

        with patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        ):
            result = application.consume_server_oauth_state("google", raw_state, browser_id)

        self.assertIsNone(result)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM oauth_states WHERE state_hash = %s",
                (state_hash,),
            ).fetchone()[0],
            1,
        )

    def test_valid_identity_session_consent_and_audit_rows(self):
        identity_id = uuid.uuid4()
        self.conn.execute(
            """INSERT INTO user_identities
               (id, user_id, identity_type, identity_lookup_hash,
                identity_value_ciphertext, verified_at, is_primary)
               VALUES (%s, %s, 'email', %s, %s, NOW(), TRUE)""",
            (identity_id, self.user_id, b"lookup-hash", b"ciphertext"),
        )
        self.conn.execute(
            """INSERT INTO auth_sessions
               (token_hash, user_id, expires_at)
               VALUES (%s, %s, NOW() + INTERVAL '1 day')""",
            ("a" * 64, self.user_id),
        )
        self.conn.execute(
            """INSERT INTO consent_events
               (id, user_id, tenant_id, purpose, policy_version, decision, source)
               VALUES (%s, %s, %s, 'career_data', 'v1', 'granted', 'android')""",
            (uuid.uuid4(), self.user_id, self.tenant_id),
        )
        self.conn.execute(
            """INSERT INTO audit_events
               (id, actor_user_id, tenant_id, action, result)
               VALUES (%s, %s, %s, 'session.created', 'success')""",
            (uuid.uuid4(), self.user_id, self.tenant_id),
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM user_identities WHERE user_id = %s",
                (self.user_id,),
            ).fetchone()[0], 1
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM auth_sessions WHERE user_id = %s",
                (self.user_id,),
            ).fetchone()[0],
            1
        )

    def test_authenticated_identity_and_logout_routes_against_postgres(self):
        token = identity_core.issue_session(
            self.conn, self.user_id, ttl_seconds=600, device_label="integration-test"
        )
        self.conn.commit()
        client = application.app.test_client()

        with patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        ):
            profile = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + token}
            )
            self.assertEqual(profile.status_code, 200)
            payload = profile.get_json()
            self.assertEqual(payload["usuario"]["id"], str(self.user_id))
            self.assertEqual(len(payload["tenants"]), 1)
            self.assertEqual(payload["tenants"][0]["id"], str(self.tenant_id))

            rotation = client.post(
                "/api/v1/session/rotate",
                headers={"Authorization": "Bearer " + token},
            )
            self.assertEqual(rotation.status_code, 200)
            new_token = rotation.get_json()["access_token"]
            self.assertNotEqual(new_token, token)

            old_session = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + token}
            )
            self.assertEqual(old_session.status_code, 401)

            renewed_profile = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + new_token}
            )
            self.assertEqual(renewed_profile.status_code, 200)

            logout = client.post(
                "/api/v1/logout", headers={"Authorization": "Bearer " + new_token}
            )
            self.assertEqual(logout.status_code, 200)

            after_logout = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + new_token}
            )
            self.assertEqual(after_logout.status_code, 401)

    def test_session_rotation_preserves_authentication_age_for_deletion_gate(self):
        token = identity_core.issue_session(
            self.conn, self.user_id, ttl_seconds=600, device_label="rotation-age-test"
        )
        old_hash = identity_core.hash_session_token(token)
        self.conn.execute(
            """UPDATE auth_sessions
               SET authenticated_at = NOW() - INTERVAL '20 minutes'
               WHERE token_hash = %s""",
            (old_hash,),
        )
        self.conn.commit()
        client = application.app.test_client()

        with patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        ):
            rotation = client.post(
                "/api/v1/session/rotate",
                headers={"Authorization": "Bearer " + token},
            )
            self.assertEqual(rotation.status_code, 200)
            new_token = rotation.get_json()["access_token"]

            deletion = client.post(
                "/api/v1/account/deletion-request",
                headers={"Authorization": "Bearer " + new_token},
                json={"confirmacao": "EXCLUIR MINHA CONTA"},
            )
            self.assertEqual(deletion.status_code, 401)

        new_hash = identity_core.hash_session_token(new_token)
        created_at, authenticated_at = self.conn.execute(
            """SELECT created_at, authenticated_at
               FROM auth_sessions WHERE token_hash = %s""",
            (new_hash,),
        ).fetchone()
        self.assertGreater(created_at, authenticated_at)
        self.assertFalse(identity_core.is_recent_session(self.conn, new_token, 900))
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM app_users WHERE id = %s", (self.user_id,)
            ).fetchone()[0],
            "active",
        )

    def test_concurrent_session_rotation_only_issues_one_replacement(self):
        token = identity_core.issue_session(
            self.conn, self.user_id, ttl_seconds=600, device_label="concurrent-rotation-test"
        )
        self.conn.commit()

        def rotate_once(_):
            with self._application_db_connection() as connection:
                return identity_core.rotate_session(connection, token)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(rotate_once, range(2)))

        replacements = [value for value in results if value]
        self.assertEqual(len(replacements), 1)
        self.assertIsNone(identity_core.validate_session(self.conn, token))
        self.assertEqual(
            self.conn.execute(
                """SELECT COUNT(*) FROM auth_sessions
                   WHERE user_id = %s AND revoked_at IS NULL AND expires_at > NOW()""",
                (self.user_id,),
            ).fetchone()[0],
            1,
        )
        self.assertTrue(
            identity_core.is_recent_session(self.conn, replacements[0], 900)
        )

    def test_suspended_user_cannot_use_active_tenant_membership(self):
        self.conn.execute(
            "UPDATE app_users SET status = 'suspended' WHERE id = %s",
            (self.user_id,),
        )
        role = authorization_core.active_tenant_role(
            self.conn, self.user_id, self.tenant_id
        )
        self.assertIsNone(role)

    def test_account_deletion_request_locks_account_and_tracks_all_systems(self):
        token = identity_core.issue_session(
            self.conn, self.user_id, ttl_seconds=600, device_label="deletion-test"
        )
        self.conn.commit()
        client = application.app.test_client()

        with patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        ):
            response = client.post(
                "/api/v1/account/deletion-request",
                headers={"Authorization": "Bearer " + token},
                json={"confirmacao": "EXCLUIR MINHA CONTA"},
            )
            self.assertEqual(response.status_code, 202)
            payload = response.get_json()
            receipt = payload["comprovante_exclusao"]
            self.assertTrue(receipt)
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")

            # Account access is revoked immediately after the request is committed.
            profile = client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + token}
            )
            self.assertEqual(profile.status_code, 401)

            status = client.get(
                "/api/v1/account/deletion-status",
                headers={"X-Deletion-Receipt": receipt},
            )
            self.assertEqual(status.status_code, 200)
            status_payload = status.get_json()
            self.assertEqual(status_payload["status"], "requested")
            self.assertEqual(len(status_payload["steps"]), 5)
            self.assertTrue(all(step["status"] == "pending" for step in status_payload["steps"]))

        user_status = self.conn.execute(
            "SELECT status FROM app_users WHERE id = %s", (self.user_id,)
        ).fetchone()[0]
        self.assertEqual(user_status, "deletion_pending")
        stored_hash = self.conn.execute(
            "SELECT receipt_hash FROM account_deletion_requests WHERE id = %s",
            (payload["request_id"],),
        ).fetchone()[0]
        self.assertNotEqual(stored_hash.strip(), receipt)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM account_deletion_steps WHERE request_id = %s",
                (payload["request_id"],),
            ).fetchone()[0],
            5,
        )

    def test_primary_database_purge_waits_for_other_systems_and_is_auditable(self):
        identity_hash = b"deletion-identity-hash"
        self.conn.execute(
            """INSERT INTO user_identities
               (id, user_id, identity_type, identity_lookup_hash,
                identity_value_ciphertext, verified_at, is_primary)
               VALUES (%s, %s, 'email', %s, %s, NOW(), TRUE)""",
            (uuid.uuid4(), self.user_id, identity_hash, b"encrypted-email"),
        )
        self.conn.execute(
            """INSERT INTO otp_challenges
               (id, identity_type, identity_lookup_hash, purpose, code_hash, expires_at)
               VALUES (%s, 'email', %s, 'recovery', %s, NOW() + INTERVAL '5 minutes')""",
            (uuid.uuid4(), identity_hash, b"otp-hash"),
        )
        self.conn.execute(
            """INSERT INTO consent_events
               (id, user_id, tenant_id, purpose, policy_version, decision, source)
               VALUES (%s, %s, %s, 'profile', 'v1', 'granted', 'android')""",
            (uuid.uuid4(), self.user_id, self.tenant_id),
        )
        self.conn.execute(
            """INSERT INTO audit_events (id, actor_user_id, action, result)
               VALUES (%s, %s, 'profile.updated', 'success')""",
            (uuid.uuid4(), self.user_id),
        )
        identity_core.issue_session(self.conn, self.user_id, ttl_seconds=600)
        self.conn.commit()

        deletion = account_deletion_core.request_account_deletion(self.conn, self.user_id)
        request_id = deletion["request_id"]
        receipt = deletion["receipt"]
        self.conn.commit()

        self.assertFalse(
            account_deletion_core.process_primary_database_deletion(self.conn, request_id)
        )
        self.assertIsNotNone(
            self.conn.execute("SELECT id FROM app_users WHERE id = %s", (self.user_id,)).fetchone()
        )

        for system in (
            "connected_providers",
            "app_storage",
            "backups",
            "legal_retention",
        ):
            account_deletion_core.complete_deletion_step(
                self.conn,
                request_id,
                system,
                evidence_reference=str(f"test-{system}-review-{request_id}"),
                not_applicable=True,
            )

        self.assertTrue(
            account_deletion_core.process_primary_database_deletion(self.conn, request_id)
        )
        self.conn.commit()

        self.assertIsNone(
            self.conn.execute("SELECT id FROM app_users WHERE id = %s", (self.user_id,)).fetchone()
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM user_identities WHERE user_id = %s", (self.user_id,)
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM auth_sessions WHERE user_id = %s", (self.user_id,)
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM consent_events WHERE user_id = %s", (self.user_id,)
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM otp_challenges WHERE identity_lookup_hash = %s",
                (identity_hash,),
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM audit_events WHERE actor_user_id = %s", (self.user_id,)
            ).fetchone()[0],
            0,
        )
        self.assertIsNone(
            self.conn.execute("SELECT id FROM tenants WHERE id = %s", (self.tenant_id,)).fetchone()
        )
        status = account_deletion_core.get_deletion_status(self.conn, receipt)
        self.assertEqual(status["status"], "completed")
        self.assertTrue(all(
            step["status"] in {"completed", "not_applicable"}
            for step in status["steps"]
        ))

    def test_account_deletion_rejects_wrong_confirmation(self):
        token = identity_core.issue_session(
            self.conn, self.user_id, ttl_seconds=600, device_label="deletion-test"
        )
        self.conn.commit()
        client = application.app.test_client()
        with patch.object(
            application, "get_db_connection", side_effect=self._application_db_connection
        ):
            response = client.post(
                "/api/v1/account/deletion-request",
                headers={"Authorization": "Bearer " + token},
                json={"confirmacao": "DELETE"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM app_users WHERE id = %s", (self.user_id,)
            ).fetchone()[0],
            "active",
        )

    def test_duplicate_identity_lookup_is_rejected(self):
        values = (self.user_id, b"same-hash", b"ciphertext")
        statement = """INSERT INTO user_identities
            (id, user_id, identity_type, identity_lookup_hash, identity_value_ciphertext)
            VALUES (%s, %s, 'email', %s, %s)"""
        self.conn.execute(statement, (uuid.uuid4(), *values))
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.conn.execute(statement, (uuid.uuid4(), *values))

    def test_invalid_membership_role_is_rejected(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute(
                """INSERT INTO tenant_memberships (tenant_id, user_id, role)
                   VALUES (%s, %s, 'superuser')""",
                (uuid.uuid4(), self.user_id),
            )

    def test_external_connection_requires_real_tenant_membership(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.conn.execute(
                """INSERT INTO external_connections
                   (id, user_id, tenant_id, provider, external_account_id)
                   VALUES (%s, %s, %s, 'google', 'account-1')""",
                (uuid.uuid4(), self.user_id, uuid.uuid4()),
            )


    def test_customer_drive_oauth_flow_is_bound_to_real_tenant_and_single_use(self):
        vault = {}
        def encrypt(value):
            ciphertext = b"cipher:" + hashlib.sha256(value.encode("utf-8")).digest()
            vault[ciphertext] = value
            return ciphertext
        decrypt = lambda value: vault[value]
        result = drive_backup_oauth.create_flow(
            self.conn,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            redirect_uri="https://api.example.test/api/v1/integrations/google-drive/callback",
            client_id="test-client-id",
            encrypt=encrypt,
        )
        self.conn.commit()

        stored = self.conn.execute(
            """SELECT state_hash, user_id, tenant_id, code_verifier_ciphertext,
                      purpose, expires_at
               FROM oauth_states WHERE purpose = 'drive_backup'"""
        ).fetchone()
        self.assertEqual(stored[0].strip(), hashlib.sha256(result["state"].encode()).hexdigest())
        self.assertEqual(stored[1], self.user_id)
        self.assertEqual(stored[2], self.tenant_id)
        self.assertTrue(bytes(stored[3]).startswith(b"cipher:"))
        self.assertNotIn(result["state"].encode(), bytes(stored[3]))
        self.assertEqual(stored[4], "drive_backup")

        context = drive_backup_oauth.consume_flow(
            self.conn, state=result["state"], decrypt=decrypt
        )
        self.conn.commit()
        self.assertEqual(context["user_id"], self.user_id)
        self.assertEqual(context["tenant_id"], self.tenant_id)
        self.assertTrue(context["code_verifier"])
        self.assertIsNone(
            drive_backup_oauth.consume_flow(
                self.conn, state=result["state"], decrypt=decrypt
            )
        )

    def test_customer_drive_connection_persists_encrypted_tokens_per_owner(self):
        vault = {}
        def encrypt(value):
            ciphertext = b"cipher:" + hashlib.sha256(value.encode("utf-8")).digest()
            vault[ciphertext] = value
            return ciphertext
        decrypt = lambda value: vault[value]
        connection_id = drive_backup_connections.save_connection(
            self.conn,
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            google_subject="google-subject-integration",
            account_label="backup@example.test",
            granted_scopes=[drive_backup_connections.REQUIRED_SCOPE, "openid", "email"],
            access_token="access-secret-integration",
            refresh_token="refresh-secret-integration",
            token_expires_at=None,
            encrypt=encrypt,
        )
        self.conn.commit()

        stored = self.conn.execute(
            """SELECT provider, user_id, tenant_id, access_token_ciphertext,
                      refresh_token_ciphertext, status
               FROM external_connections WHERE id = %s""",
            (connection_id,),
        ).fetchone()
        self.assertEqual(stored[0], drive_backup_connections.PROVIDER)
        self.assertEqual(stored[1], self.user_id)
        self.assertEqual(stored[2], self.tenant_id)
        self.assertNotEqual(bytes(stored[3]), b"access-secret-integration")
        self.assertNotEqual(bytes(stored[4]), b"refresh-secret-integration")
        self.assertTrue(bytes(stored[3]).startswith(b"cipher:"))
        self.assertTrue(bytes(stored[4]).startswith(b"cipher:"))
        self.assertEqual(stored[5], "active")

        connection = drive_backup_connections.get_connection(
            self.conn, user_id=self.user_id, tenant_id=self.tenant_id,
            connection_id=connection_id, decrypt=decrypt,
        )
        self.assertEqual(connection["access_token"], "access-secret-integration")
        self.assertEqual(connection["refresh_token"], "refresh-secret-integration")
        self.assertIsNone(
            drive_backup_connections.get_connection(
                self.conn, user_id=uuid.uuid4(), tenant_id=self.tenant_id,
                connection_id=connection_id, decrypt=decrypt,
            )
        )

        self.assertTrue(
            drive_backup_connections.revoke_connection(
                self.conn, user_id=self.user_id, tenant_id=self.tenant_id,
                connection_id=connection_id,
            )
        )
        self.conn.commit()
        revoked = self.conn.execute(
            """SELECT status, access_token_ciphertext, refresh_token_ciphertext
               FROM external_connections WHERE id = %s""",
            (connection_id,),
        ).fetchone()
        self.assertEqual(revoked, ("revoked", None, None))


    def test_otp_rate_limits_are_atomic_and_scoped_to_pseudonymous_dimensions(self):
        digest = hashlib.sha256(b"identity-rate-limit-fixture").digest()
        self.assertTrue(
            otp_core.reserve_otp_request_slot(
                self.conn, "identity", digest, "login",
                cooldown_seconds=60, window_seconds=3600, max_requests=2,
            )
        )
        self.assertFalse(
            otp_core.reserve_otp_request_slot(
                self.conn, "identity", digest, "login",
                cooldown_seconds=60, window_seconds=3600, max_requests=2,
            )
        )
        self.conn.execute(
            """UPDATE otp_request_limits
               SET last_requested_at = NOW() - INTERVAL '61 seconds'
               WHERE dimension_type = 'identity' AND dimension_hash = %s
                 AND purpose = 'login'""",
            (digest,),
        )
        self.conn.commit()
        self.assertTrue(
            otp_core.reserve_otp_request_slot(
                self.conn, "identity", digest, "login",
                cooldown_seconds=60, window_seconds=3600, max_requests=2,
            )
        )
        self.conn.execute(
            """UPDATE otp_request_limits
               SET last_requested_at = NOW() - INTERVAL '61 seconds'
               WHERE dimension_type = 'identity' AND dimension_hash = %s
                 AND purpose = 'login'""",
            (digest,),
        )
        self.conn.commit()
        self.assertFalse(
            otp_core.reserve_otp_request_slot(
                self.conn, "identity", digest, "login",
                cooldown_seconds=60, window_seconds=3600, max_requests=2,
            )
        )
        self.assertTrue(
            otp_core.reserve_otp_request_slot(
                self.conn, "identity", digest, "recovery",
                cooldown_seconds=60, window_seconds=3600, max_requests=2,
            )
        )
        self.assertTrue(
            otp_core.reserve_otp_request_slot(
                self.conn, "ip", digest, "login",
                cooldown_seconds=60, window_seconds=3600, max_requests=2,
            )
        )

    def test_concurrent_otp_rate_limit_reservations_never_exceed_window_quota(self):
        digest = hashlib.sha256(uuid.uuid4().bytes).digest()
        self.conn.execute(
            """INSERT INTO otp_request_limits (
                   dimension_type, dimension_hash, purpose,
                   window_started_at, request_count, last_requested_at
               )
               VALUES ('identity', %s, 'signup', NOW(), 1,
                       NOW() - INTERVAL '2 seconds')""",
            (digest,),
        )
        self.conn.commit()

        def reserve_slot():
            connection = self._application_db_connection()
            try:
                allowed = otp_core.reserve_otp_request_slot(
                    connection, "identity", digest, "signup",
                    cooldown_seconds=1, window_seconds=3600, max_requests=3,
                )
                connection.commit()
                return allowed
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(lambda _: reserve_slot(), range(12)))

        accepted = sum(results)
        self.assertLessEqual(accepted, 2)
        final_count = self.conn.execute(
            """SELECT request_count FROM otp_request_limits
               WHERE dimension_type = 'identity' AND dimension_hash = %s
                 AND purpose = 'signup'""",
            (digest,),
        ).fetchone()[0]
        self.assertEqual(final_count, 1 + accepted)

    def test_invalid_otp_attempt_limits_and_audit_result_are_rejected(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.conn.transaction():
                self.conn.execute(
                    """INSERT INTO otp_challenges
                       (id, identity_type, identity_lookup_hash, purpose, code_hash,
                        expires_at, max_attempts)
                       VALUES (%s, 'email', %s, 'login', %s,
                               NOW() + INTERVAL '5 minutes', 11)""",
                    (uuid.uuid4(), b"lookup", b"code-hash"),
                )
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.conn.transaction():
                self.conn.execute(
                    """INSERT INTO audit_events (id, action, result)
                       VALUES (%s, 'profile.read', 'maybe')""",
                    (uuid.uuid4(),),
                )


if __name__ == "__main__":
    unittest.main()
