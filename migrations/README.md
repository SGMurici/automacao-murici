# Migration inventory and execution policy

Do not apply every SQL file by glob. The project contains migrations for different subsystems and a preserved legacy migration.

## Identity / OTP baseline used by the isolated PostgreSQL integration suite

Apply in this order to a disposable PostgreSQL schema:

1. `0001_oauth_states.sql`
2. `0002_identity_core.sql`
3. `0003_account_deletion.sql`
4. `0005_otp_request_limits.sql`
5. `0006_session_authentication_freshness.sql`
6. `0009_identity_otp_hardening.sql`
7. `0010_otp_signup_policy_versions.sql`
8. `0011_otp_email_transactional_outbox.sql`
9. `0012_global_administrators.sql`
10. `0013_otp_delivery_uncertainty.sql`

The explicit list in `tests/test_identity_migrations_postgres.py` is the test harness source of truth for this subset. This is not blanket authorization to apply the migrations to any shared database.

## Conditional legacy application migrations

- `0007_observation_editorial_post_fk.sql` requires the existing editorial tables and a preflight for orphan observations. Validate independently against a disposable copy of the editorial schema.
- `0008_scheduler_lease_recovery.sql` requires the existing LinkedIn scheduler queue schema. Validate independently against a disposable copy of the scheduler schema.
- Neither migration is part of the isolated identity-only test subset above.

## Archived / excluded migration

- `legacy/0004_customer_drive_oauth.sql` is preserved for historical traceability only. Customer Google Drive backup is out of product scope. Do not apply this migration to new or existing environments as part of the approved product path.
- The corresponding customer Drive backup modules and tests have been removed from the active integration branch. The historical design note is under `docs/archive/`.

## Mandatory preflight before any database write

1. Confirm the target project and branch by ID and name.
2. Confirm the migration has not already been applied; inspect schema and data first.
3. Take/verify a restorable snapshot and test restoration.
4. Inspect dependencies, constraints, row counts, locks, and orphan records.
5. Run the migration in an isolated disposable PostgreSQL database and the relevant integration tests.
6. Prepare rollback/recovery steps and expected downtime/lock impact.
7. Obtain explicit authorization for the exact target branch. Production always requires a separate explicit authorization.
