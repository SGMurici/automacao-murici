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
11. `0014_identity_hash_format_constraints.sql`

The explicit list in `tests/test_identity_migrations_postgres.py` is the test harness source of truth for this subset. This is not blanket authorization to apply the migrations to any shared database.

## Operational scheduler and analytics schema

- `0015_operational_scheduler_analytics_schema.sql` creates the LinkedIn publishing queue, analytics snapshots, collection-run ledger, and required indexes. It requires the existing `editorial_posts` table.
- The migration is additive and idempotent. On an existing queue it adds `reconciliation_required_at` when missing and preserves legacy columns such as historical Drive/media metadata.
- The active backend validates the required schema at runtime but performs no DDL in HTTP or scheduler requests. Apply this migration in a disposable environment and verify it before deploying that code.
- When `0015` is applied, the older `0008_scheduler_lease_recovery.sql` is redundant. Keep `0008` only as a targeted upgrade for legacy databases that already have the queue table and are not applying `0015`.

## Conditional legacy application migrations

- `0007_observation_editorial_post_fk.sql` requires the existing editorial tables and a preflight for orphan observations. Validate independently against a disposable copy of the editorial schema.
- `0008_scheduler_lease_recovery.sql` requires the existing LinkedIn scheduler queue schema. Validate independently against a disposable copy of the scheduler schema when `0015` is not being applied.
- Neither migration is part of the isolated identity-only test subset above.

## Archived / excluded migration

- `legacy/0004_customer_drive_oauth.sql` is preserved for historical traceability only. Customer Google Drive backup is out of product scope. Do not apply this migration to new or existing environments as part of the approved product path.
- The corresponding customer Drive backup modules and tests have been removed from the active integration branch. The historical design note is under `docs/archive/`.

## Recovered KAPPA / OTP source files 0016–0035 — versioned, execution gate open

The 20 recovered SQL sources are now present in this canonical directory, byte-for-byte, with SHA-256 values recorded in `SHA256SUMS.kappa-otp-0016-0035`. Each destination Git blob ID was compared with the corresponding source blob ID in the verified recovery repository; all 20 are identical.

This confirms source-byte identity during transfer; it does **not** prove historical execution or that every file should be applied to every environment.

### Provenance and observed homologation ledger

- 0017–0019 and 0021–0029: source SHA-256 matches the ledger on the queried Neon homologation branch; ledger status `reconciled`, mode `manual_equivalent_sql`.
- 0030–0034: source SHA-256 matches the ledger; status `applied`, mode `segmented_sql_transaction`.
- 0016, 0020 and 0035: no row in the queried ledger table on that branch; execution/provenance remains unconfirmed.
- A missing ledger row is not proof that a migration was never applied. Inspect actual schema and data before any attempt to apply.

### Execution constraints

- Do not apply all SQL files by glob.
- 0030 requires the OAuth capability owner/executor roles and protected tables described in the security role plan.
- 0031 requires the event worker capability roles and matching event schema.
- 0032 requires the OTP outbox capability roles and OTP outbox schema.
- 0033 depends on the event capability owner/executor created by the earlier capability setup.
- 0034 depends on the OAuth capability roles and state tables.
- 0035 changes the external-connection capability surface and depends on the provider/tenant schema plus capability-role prerequisites.
- The role/bootstrap scripts are separate from these migrations. Do not infer that the migration principal can safely provision or own runtime roles.
- 0016 and 0020 have no matching row in the queried ledger; inspect their exact effects against the target catalog before deciding whether to apply.
- 0027–0029 validate composite foreign keys and can fail if existing rows violate tenant/provider ownership.
- The historical ledger records 0030–0034 as segmented SQL transactions, not checksum-aware runner executions.

This directory is now the canonical source location. It is **not yet a blanket approval to apply 0016–0035**. The exact target branch, existing schema, role memberships, ownership, ACLs, RLS/context model, and rollback plan must be validated first.

## Mandatory preflight before any database write

1. Confirm the target project and branch by ID and name.
2. Confirm the migration has not already been applied; inspect schema and data first.
3. Take/verify a restorable snapshot and test restoration.
4. Inspect dependencies, constraints, row counts, locks, and orphan records.
5. Run the migration in an isolated disposable PostgreSQL database and the relevant integration tests.
6. Prepare rollback/recovery steps and expected downtime/lock impact.
7. Obtain explicit authorization for the exact target branch. Production always requires a separate explicit authorization.
