# Runtime workload roles and capability boundary — homologation

Date: 2026-11-26

## Scope and immutable references

- Repository: `SGMurici/automacao-murici`
- Candidate base: PR #34 HEAD `a7195382132c3f771a5d48c395d16d5a0d221507`
- This work branch: `security/runtime-capability-boundaries-2026-11-26`
- Neon project: `sweet-dust-48417314` (Automação Murici)
- Disposable target branch: `br-delicate-snow-b6qpdscm`, name `kappa-otp-runtime-grants-test-2026-11-25`
- Preserved parent: `br-wild-math-b6o7j6sd`, name `kappa-otp-runtime-baseline-preserved-2026-11-25`
- Target is non-default, non-primary, unprotected, and derived from the preserved baseline. Production/default is `br-young-field-b65u7hwg`; it was not modified.

## Runtime logins provisioned in the disposable branch

Four LOGIN roles were created in one transaction on the disposable branch:

| Role | LOGIN | INHERIT | Superuser / CREATEDB / CREATEROLE / REPLICATION / BYPASSRLS |
|---|---:|---:|---|
| `kappa_web_runtime_login` | true | true | all false |
| `kappa_scheduler_runtime_login` | true | true | all false |
| `kappa_otp_worker_runtime_login` | true | true | all false |
| `kappa_analytics_runtime_login` | true | true | all false |

All four have no direct table privileges, no sequence privileges, no function EXECUTE privileges, and no memberships in executor/capability-owner roles at this checkpoint. Passwords have not been provisioned. They cannot be used by an application until the workload contract is complete and a credential is issued out-of-band. This is intentional fail-closed staging.

The exact provisioning SQL is in `ops/homologation/provision_runtime_login_roles.sql`. It is explicitly homologation-only and must not be treated as a production migration.

## Current executor/capability inventory observed in the target

- `kappa_api_oauth_executor`: EXECUTE on the existing client OAuth state/ticket capabilities.
- `kappa_event_api_enqueue_executor`: EXECUTE on the calendar-sync enqueue capability.
- `kappa_event_worker_executor`: EXECUTE on event delivery claim/ack/retry/recovery capabilities.
- `kappa_otp_outbox_worker_executor`: EXECUTE on the six OTP outbox capabilities.
- Capability owners for OAuth, event and OTP outbox remain NOLOGIN.
- The 23 SECURITY DEFINER functions observed have `search_path=pg_catalog`, no PUBLIC EXECUTE, and executor-specific ACLs.
- No RLS policies were found; RLS/FORCE RLS is disabled on all 40 public tables.
- The new runtime logins intentionally have not been granted these executor roles yet. Memberships will be added only after each workload's function allowlist is reviewed and the application code no longer performs direct DML.

## Capability mapping still required

| Workload | Required capability surface | Current state |
|---|---|---|
| Web/API | bearer/session resolution, OTP request/verify, signup/login completion, tenant membership derivation, OAuth state/ticket, limited event enqueue | Existing OAuth/event enqueue wrappers only partially cover the path. Identity/session/OTP business capabilities are incomplete. |
| Scheduler | publishing queue claim/complete/uncertain/reconcile, pending-signup cleanup, event dispatch only if assigned | Publishing and cleanup still contain direct DML in PR #34. No membership granted. |
| OTP worker | outbox claim, dispatching, sent/failure/uncertain, expiry | Six SQL wrappers exist, but Python worker still contains direct DML. Runtime membership is withheld until Python adapter uses wrappers. |
| Analytics | collection-run lifecycle, snapshot insertion, OAuth connection access with tenant scope | Dedicated analytics capability owner/executor and functions not yet evidenced. No membership granted. |

No workload login may own tables, inherit `neondb_owner`, use BYPASSRLS, execute arbitrary SQL, or receive broad table DML.

## Critical findings before credentials or workload cutover

1. PR #34 application modules still use `DATABASE_URL` and direct DML for identity, sessions, OTP, outbox, publishing, analytics and signup cleanup. A runtime login without table privileges will fail closed; do not point Render at it yet.
2. Existing SQL OAuth capabilities cover client-specific OAuth state/tickets, not necessarily the legacy `oauth_states` table or operational Google/LinkedIn credential UPSERT/refresh paths.
3. Five existing SECURITY DEFINER functions rely on transaction/session GUCs `app.user_id`, `app.tenant_id`, and `app.actor_role`. These values are not identity proof. A trusted capability must validate the bearer/session and derive membership before setting transaction-local context. No client-provided GUC may be trusted.
4. RLS/FORCE RLS is absent on 40/40 tables. Capability-only isolation must be demonstrated end-to-end; RLS is an additional defense, not a substitute for secure capabilities.
5. `kappa_schema_migrations` contains 17 records (0017–0019, 0021–0034). 0017–0029 are marked `reconciled/manual_equivalent_sql`; 0030–0034 are marked `applied/segmented_sql_transaction`. Migration 0020 is absent. The current PR #34 tree contains migrations 0001–0015 but no source files 0017–0034. Their ledger hashes therefore cannot currently be reproduced from the PR source tree.
6. The target branch is PostgreSQL 18.7, while PR CI is PostgreSQL 16. CI results are useful regression evidence but do not establish compatibility or effective privilege behavior on this branch.
7. Passwords and Render environment variables have not been read, rotated, or changed. No credentials have been issued for the four new logins.

## Next implementation order

1. Recover and verify the exact SQL sources/hashes for migrations 0017–0034; reconcile ledger, current catalog, and baseline migrations. Do not invent replacement hashes.
2. Build one transaction-local trusted principal context from a validated bearer/session; prove reset on pooled connection reuse and reject spoofed GUC.
3. Implement complete business capabilities for auth/session/OTP, not generic table wrappers. Reuse existing outbox functions and remove duplicate Python DML.
4. Add capabilities for legacy OAuth state, operational credential link/refresh, publishing, analytics and pending-signup cleanup.
5. Assign each login only its required executor membership. Then issue ephemeral homologation credentials and run positive/negative tests as actual login roles.
6. Chat 3 independently tests DML denial, function allowlists, GUC spoofing, pool reuse, tenant A/B isolation, OTP/outbox concurrency, OAuth replay, publishing ambiguity and analytics isolation.
7. Only after QA evidence and separate authorization: prepare production migration and credential/Render transition plan. No merge, deployment, secret rotation, cron changes or worker scheduling are part of this PR.

## Changes performed

- Created the four LOGIN roles only in `br-delicate-snow-b6qpdscm`.
- Verified LOGIN=true and all administrative flags false.
- Verified no table SELECT/INSERT/UPDATE privileges and no sampled OAuth/OTP function EXECUTE privileges for the new logins.
- Created a GitHub work branch from PR #34 HEAD and added the homologation-only SQL script and this audit record.
- No production/default Neon branch, Render service, secret, cron, customer data, PR #33/#34, or Windows/KAPPA environment was changed.
- No tests were executed as part of this checkpoint. QA remains BLOCKED/NOT RUN pending complete capabilities and credentials.


## Clarification — owner column-level grants verified (26/11/2026)

A second catalog query included `information_schema.column_privileges`; the earlier table-level query alone did not expose these grants. The target branch has **150 effective column-level grants** across the three existing capability owners:

| Capability owner | Grants | Tables | Distinct columns | Operations |
|---|---:|---:|---:|---|
| `kappa_event_capability_owner` | 39 | 4 | 25 | INSERT, SELECT, UPDATE |
| `kappa_oauth_capability_owner` | 82 | 10 | 55 | INSERT, SELECT, UPDATE |
| `kappa_otp_outbox_capability_owner` | 29 | 2 | 20 | SELECT, UPDATE |

The sampled `has_column_privilege` checks returned true for these grants. This is distinct from table-level grants, which remain absent. The earlier audit statement “zero table grants” must not be read as “zero privileges”: column-level grants are present and effective for the capability owners. Executors and the four newly created runtime logins still have no direct table/column grants. This confirms the owners' current minimum column-level grants exist, but does not prove every function succeeds or that the grant set is minimal; runtime positive/negative tests are still required.


## Runtime membership refinement and smoke-test boundary (26/11/2026)

The initial blanket statement that all four runtime logins had no memberships was superseded by a narrowly scoped grant:

- `kappa_otp_worker_runtime_login` is a member of `kappa_otp_outbox_worker_executor` with INHERIT and SET enabled. Effective checks show EXECUTE on `kappa_otp_outbox_claim_one()`, while direct UPDATE on `otp_email_outbox` and direct DML on `app_users` remain false.
- `kappa_web_runtime_login` has no executor membership. Temporary grants to OAuth and event enqueue executors were revoked after confirming that the OAuth create functions rely on caller-set `app.user_id`, `app.tenant_id`, and `app.actor_role` GUCs. Do not grant these until a trusted bearer/session capability derives the principal and tenant inside the database.
- `kappa_scheduler_runtime_login` and `kappa_analytics_runtime_login` remain without memberships or direct privileges.
- Earlier notes stated that no passwords had been provisioned and Neon password reset was unavailable for these SQL-created roles. A subsequent read-only catalog check found a non-null password verifier for all four roles. The origin is unresolved; do not authenticate with them or configure them in Render until reconciled.
- A smoke-test attempt to `SET LOCAL ROLE kappa_api_oauth_executor` from `neondb_owner` was denied because Neon role membership has SET disabled. The transaction rolled back; synthetic user, tenant and OAuth state collision checks confirm zero residual fixture rows. This is NOT a function failure and is NOT a successful runtime test.

The OTP runtime membership is a limited preparation step, not a runtime cutover. The Python worker still uses direct DML and `DATABASE_URL` in PR #34; refactor it to the six SQL wrappers and require a separate `OTP_WORKER_DATABASE_URL` before the role can be used. No worker code or Render environment was changed in this checkpoint.


## CI regression and fixture correction (26/11/2026)

The first PR #35 CI run failed one of 280 tests: `test_verified_user_can_request_login_and_receive_second_session`. The test's SMTP mock had no call because its client IP fixture selected from only 255 possible addresses, allowing collision with the shared OTP rate-limit window in the class schema. The test fixture was changed to generate a synthetic client IP with 20 random bits in `172.16.0.0/12`, outside the configured trusted-proxy CIDRs. On HEAD `083919e3b987c7908cb81404c484e4fffa4b8f20`, GitHub Actions `python-tests` completed successfully: **280 tests passed** on PostgreSQL 16. This is regression evidence for the current PR, not QA of Neon runtime roles, RLS, or tenant isolation.


## OTP worker integration and runtime credential reconciliation (26/11/2026)

The six SQL wrappers have been verified in the disposable branch. Their signatures are listed in the PR description. The current Python worker still uses direct DML in `otp_email_outbox.py`; the worker CLI reads `DATABASE_URL`, and the live scheduler path calls `run_once(get_db_connection)`, where `get_db_connection` also uses `DATABASE_URL`. The wrappers already update the related `otp_challenges` row atomically, so the Python adapter must pass the attempts value and remove duplicate calls to `otp_core.mark_otp_delivery` after finalization.

The scheduler runs inside the Flask/web process. Merely adding `OTP_WORKER_DATABASE_URL` to that same process does not isolate the credential from the web workload. A separate worker process/service is the stronger isolation boundary but may add cost; no new service or cron is authorized by this record. Keep the existing scheduler unchanged until an architecture decision.

A read-only catalog query also returned `rolpassword IS NOT NULL` for each of the four runtime login roles. No password hash was read and no authentication was attempted. This conflicts with earlier notes and must be reconciled before any use of these roles. No secrets, Render settings, cron, production or persistent migrations were changed.
