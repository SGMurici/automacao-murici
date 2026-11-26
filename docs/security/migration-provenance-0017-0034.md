# Migration provenance register — KAPPA / Neon homologation

Snapshot date: 2026-11-26  
Neon project: `sweet-dust-48417314`  
Disposable branch: `br-delicate-snow-b6qpdscm` (`kappa-otp-runtime-grants-test-2026-11-25`)  
Database: `neondb`, PostgreSQL 18.7

## Source of truth and limitations

The register below was read from `public.kappa_schema_migrations` on the disposable branch. The ledger has 17 rows: 0017–0019, 0021–0034. Migration 0020 is absent. Migration 0016 is also absent from the ledger. The repository tree at PR #34 HEAD `a7195382132c3f771a5d48c395d16d5a0d221507` contains baseline migrations 0001–0015 but not the 0017–0034 files.

For 0017–0029, status `reconciled` and execution mode `manual_equivalent_sql` mean equivalent SQL was applied manually and catalog-verified; the recorded hash identifies the reviewed source, not a byte-for-byte migration-runner execution. For 0030–0034, status is `applied` and execution mode `segmented_sql_transaction`; notes say the local source hash was verified before applying complete SQL statements in Neon. The source files are not currently present in the PR #34 Git tree. Do not reconstruct original files and claim identical provenance; recover the local originals and verify SHA-256 against this register.

## Ledger

| Migration | SHA-256 | Status | Execution mode | Verification |
|---|---|---|---|---|
| 0017_scope_connection_purpose_to_gmail.sql | `C2AE3881A81974297C3697784953A78E066CD8AD5EC31EBC9F137AE5222BAB2C` | reconciled | manual_equivalent_sql | catalog_verified |
| 0018_bind_gmail_oauth_tickets_to_connection.sql | `F7092EA88420607AE1F85C11443FBECDEA26407CD83043703055440CD5BE9449` | reconciled | manual_equivalent_sql | catalog_verified |
| 0019_expand_external_connection_status.sql | `7EAE2F61362929E89AB5C20330A12BB69AC47202C2BE0DF0FEA1FCE32FA25119` | reconciled | manual_equivalent_sql | catalog_verified |
| 0021_client_microsoft_oauth.sql | `CE0CCCD8A03AEE260A75FB5BB2627354B18A23CAB1DE45E850ACD37082594066` | reconciled | manual_equivalent_sql | catalog_verified |
| 0022_linkedin_tenant_queue.sql | `728FB338FF136F435DA49B9FE0D4C6F8040599B526C7DE86324DBED720BE19C3` | reconciled | manual_equivalent_sql | catalog_verified |
| 0023_client_linkedin_oauth.sql | `1E203E27C361B4E22714F411E30D39B106EFCBA699E4213E056737A088DFC6B3` | reconciled | manual_equivalent_sql | catalog_verified |
| 0024_linkedin_tenant_publication_result.sql | `38D07E0019B54E6F85FA464C511D83A57CA3594EA203C24706C9A1D4B92F2F6A` | reconciled | manual_equivalent_sql | catalog_verified |
| 0025_linkedin_post_analytics.sql | `BAF7449AE5A1778F71FC87B18A566044A3D814F9C6FB19B12040F2614DC1B92E` | reconciled | manual_equivalent_sql | catalog_verified |
| 0026_linkedin_analytics_oauth.sql | `4F904F15DFCD94FBBE03B50040399BA664880741F6B4FA7072621876C89AE945` | reconciled | manual_equivalent_sql | catalog_verified |
| 0027_linkedin_analytics_composite_tenant_fks.sql | `E0A6514165C337FFFE88CAFE043289AA72EF211B915900CE4668F0AC805BE63B` | reconciled | manual_equivalent_sql | catalog_verified |
| 0028_oauth_ticket_tenant_provider_fks.sql | `29343ABCD874E78464A3A3238B3B427CE76F5DABBA2E360F09090BE6D1FD83AB` | reconciled | manual_equivalent_sql | catalog_verified |
| 0029_linkedin_queue_snapshot_tenant_fks.sql | `7B976415EAFABB862B20EFA6289282A2E6074E4341128CFB4F9E4F2551E788BF` | reconciled | manual_equivalent_sql | catalog_verified |
| 0030_oauth_one_time_capabilities.sql | `77CB5FB04B46FD40B0D3A4BE04C29D37673FAA2EA7BE6BCA97BCAE4DDA3FFD58` | applied | segmented_sql_transaction | catalog_verified |
| 0031_event_bus_worker_capabilities.sql | `08B0ADDAF4E8EC2C351674942A0D97E4C1DB920C50E574C30C906BF5DDA3D8D3` | applied | segmented_sql_transaction | catalog_verified |
| 0032_otp_outbox_worker_capabilities.sql | `8283699515B0A718516557EB6881323F1EE1BE4431855F8AF7C8AE789441501E` | applied | segmented_sql_transaction | catalog_verified |
| 0033_calendar_sync_enqueue_capability.sql | `1C5B266A2B741F2B93B4DFC3A0960B221AFDDB0B51957DC01F2418969C042473` | applied | segmented_sql_transaction | catalog_verified |
| 0034_oauth_state_creation_capabilities.sql | `D102ED2D566AA99C8BC45B48F2F3EF0BAFB7D27FC13EE5F1DD35570BA7B67951` | applied | segmented_sql_transaction | catalog_verified |

## Additional verified notes

- 0030 defines 8 one-time OAuth capability functions.
- 0031 defines 4 event-bus worker capability functions.
- 0032 defines 6 OTP outbox worker capability functions.
- 0033 adds calendar-sync enqueue capability. Ledger notes claim active user and tenant membership are rechecked in the database, with temporary NOLOGIN wrapper tests for EXECUTE-only access, no direct DML, successful enqueue/idempotent replay, mismatched tenant and forged/non-member context rejection.
- 0034 adds four OAuth state creation functions. Ledger notes claim synthetic active tenant-member smoke succeeded, mismatched tenant, forged user GUC and invalid TTL were rejected, direct INSERT denied, and synthetic data plus temporary role membership were cleaned in the same transaction. No HTTP end-to-end test was recorded.
- The 0033/0034 GUC tests do not prove resistance to a caller setting GUCs to another *valid* user's ID and tenant. Add explicit user-A → valid user-B spoof tests before granting these executors to web runtime.
- Migration 0014 is in PR #33 but is not in this branch ledger; 0015 is in PR #34 and is not applied to Neon. Neither should be applied before the legacy-data and ledger preflight.
- The branch schema has baseline structures corresponding to 0001–0013 even though those IDs are not in this ledger. The production/default branch has no KAPPA ledger and must remain untouched.
- CI runs PostgreSQL 16; this Neon branch runs PostgreSQL 18.7. Both need explicit compatibility evidence.

## Next steps

1. Recover the local original files 0017–0034 and verify each SHA-256; do not regenerate historical hashes.
2. Reconcile the missing 0020/0016 IDs and baseline 0001–0015 against actual source, schema and ledger.
3. Only after reconciliation, prepare a reproducible forward migration plan; no migration is applied by this document.
4. Add Chat 3 cases for valid-member GUC impersonation, tenant A/B isolation, executor membership SET/INHERIT, and all six OTP wrapper transitions.

No migration, table, role, grant, secret, branch, Render service, or production data was changed to create this register.
