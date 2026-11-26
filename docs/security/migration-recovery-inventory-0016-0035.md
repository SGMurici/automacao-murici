# KAPPA / OTP migration recovery inventory — 0016–0035

Snapshot date: 2026-11-26  
Repository target: `SGMurici/automacao-murici`  
Canonical directory: `migrations/`  
Recovery branch: `recovery/kappa-migrations-0016-0035-2026-11-26`

## Important status

This document records the local inventory reported by the read-only Desktop Commander investigation and establishes the intended canonical location. **The SQL source files 0016–0035 have not yet been committed to this repository.** The GitHub connector used for this update cannot read files from the Windows working tree; only names, sizes, local paths and SHA-256 values were available from the Notion investigation record. Do not treat this inventory as the migration files themselves and do not execute SQL from this register.

The local files were reported under:

`C:/Users/Pichau/Documents/AutomacaoMurici/automacao-murici-backend-review/migrations/`

Additional copies of 0016–0020 were reported under:

- `C:/Users/Pichau/Documents/AutomacaoMurici/automacao-murici-backend-combined-review-2026-11-16/migrations/`
- `C:/Users/Pichau/Documents/AutomacaoMurici/automacao-murici-backend-release-review-2026-11-16/migrations/`

## Inventory and provenance

SHA-256 values below are the values reported by the local read-only scan. For 0017–0019 and 0021–0034, they match the corresponding `source_sha256` values in the disposable Neon homologation ledger. This is a byte-level hash match to the recorded source hash, not proof that a migration runner executed those exact files.

| Migration | Bytes | SHA-256 | Local copies | Ledger status / provenance |
|---|---:|---|---:|---|
| `0016_kappa_central_event_bus.sql` | 2,782 | `1a06bc75fff2f5f359a1f3761da657c8a57b52e85f293700091204171c31c2ab` | 3 | No ledger row; source provenance pending |
| `0017_scope_connection_purpose_to_gmail.sql` | 1,128 | `c2ae3881a81974297c3697784953a78e066cd8ad5ec31ebc9f137ae5222bab2c` | 3 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0018_bind_gmail_oauth_tickets_to_connection.sql` | 518 | `f7092ea88420607ae1f85c11443fbecdea26407cd83043703055440cd5be9449` | 3 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0019_expand_external_connection_status.sql` | 152 | `7eae2f61362929e89ab5c20330a12bb69ac47202c2be0df0fea1fce32fa25119` | 3 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0020_consent_acknowledgement.sql` | 335 | `85cb76219b47a422d3213de11596ed7d4f6343c2f5e4c2c4cf2741cd31d839db` | 3 | No ledger row; source provenance pending |
| `0021_client_microsoft_oauth.sql` | 1,896 | `ce0cccd8a03aee260a75fb5bb2627354b18a23cab1de45e850acd37082594066` | 1 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0022_linkedin_tenant_queue.sql` | 1,526 | `728fb338ff136f435da49b9fe0d4c6f8040599b526c7de86324dbed720be19c3` | 1 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0023_client_linkedin_oauth.sql` | 1,744 | `1e203e27c361b4e22714f411e30d39b106efcba699e4213e056737a088dfc6b3` | 1 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0024_linkedin_tenant_publication_result.sql` | 428 | `38d07e0019b54e6f85fa464c511d83a57ca3594ea203c24706c9a1d4b92f2f6a` | 1 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0025_linkedin_post_analytics.sql` | 631 | `baf7449ae5a1778f71fc87b18a566044a3d814f9c6fb19b12040f2614dc1b92e` | 1 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0026_linkedin_analytics_oauth.sql` | 2,944 | `4f904f15dfcd94fbbbe03b50040399ba664880741f6b4fa7072621876c89ae945` | 1 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0027_linkedin_analytics_composite_tenant_fks.sql` | 1,939 | `e0a6514165c337fffe88cafe043289aa72ef211b915900ce4668f0ac805be63b` | 1 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0028_oauth_ticket_tenant_provider_fks.sql` | 2,954 | `29343abcd874e78464a3a3238b3b427ce76f5dabba2e360f09090be6d1fd83ab` | 1 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0029_linkedin_queue_snapshot_tenant_fks.sql` | 1,964 | `7b976415eafabb862b20efa6289282a2e6074e4341128cfb4f9e4f2551e788bf` | 1 | Hash matches ledger; `reconciled / manual_equivalent_sql` |
| `0030_oauth_one_time_capabilities.sql` | 15,659 | `77cb5fb04b46fd40b0d3a4be04c29d37673faa2ea7be6bca97bcae4dda3ffd58` | 1 | Hash matches ledger; `applied / segmented_sql_transaction` |
| `0031_event_bus_worker_capabilities.sql` | 12,413 | `08b0addaf4e8ec2c351674942a0d97e4c1db920c50e574c30c906bf5dda3d8d3` | 1 | Hash matches ledger; `applied / segmented_sql_transaction` |
| `0032_otp_outbox_worker_capabilities.sql` | 18,053 | `8283699515b0a718516557eb6881323f1ee1be4431855f8af7c8ae789441501e` | 1 | Hash matches ledger; `applied / segmented_sql_transaction` |
| `0033_calendar_sync_enqueue_capability.sql` | 6,834 | `1c5b266a2b741f2b93b4dfc3a0960b221afddb0b51957dc01f2418969c042473` | 1 | Hash matches ledger; `applied / segmented_sql_transaction` |
| `0034_oauth_state_creation_capabilities.sql` | 10,106 | `d102ed2d566aa99c8bc45b48f2f3ef0bafb7d27fc13ee5f1dd35570ba7b67951` | 1 | Hash matches ledger; `applied / segmented_sql_transaction` |
| `0035_external_connection_capabilities.sql` | 27,107 | `7af3bd23d416f5e7499c61834668080fc1c8dd5666fe27c286dc3454e06e574c` | 1 | No ledger row; source provenance pending |

## Ledger interpretation

- 0017–0029: ledger status `reconciled`, execution mode `manual_equivalent_sql`; the source hash matches, but the record does not prove byte-for-byte execution by a migration runner.
- 0030–0034: ledger status `applied`, execution mode `segmented_sql_transaction`; the recorded source hash matches the local file hash, while execution was recorded as segmented SQL in a transaction, not as a checksum-aware migration-runner application.
- 0016, 0020 and 0035: no row was found in the queried homologation ledger. Do not infer that they were applied.
- The ledger is from a disposable Neon homologation branch, not production/default.

## Import gate

Before committing the SQL files into this canonical directory:

1. Obtain the actual file bytes from the local source (for example, by attaching a ZIP containing only the `migrations/` directory to the conversation).
2. Recompute SHA-256 on the received bytes and compare every file with this register.
3. Preserve exact source bytes; do not normalize line endings or regenerate SQL.
4. Review the 0016, 0020 and 0035 provenance separately.
5. Check naming collisions and existing files before adding anything.
6. Update this inventory from “pending import” to “versioned” only after the SQL files are actually present in GitHub.

## Safety

This register is documentation only. No SQL was executed, no Neon ledger was modified, no schema/role/grant/RLS change was made, and no Render or Vercel service was changed.
