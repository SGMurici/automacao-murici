# KAPPA — account deletion lifecycle

## User experience

The customer can initiate account deletion from Account / Privacy / Delete account. The action must be available inside the app and through a public web deletion page for customers who have uninstalled the app.

The confirmation screen explains:
- the account and associated personal data are intended to be permanently deleted;
- the action immediately blocks account access and revokes every active session;
- the customer must reauthenticate within the previous 15 minutes and type `EXCLUIR MINHA CONTA`;
- a one-time deletion receipt is displayed once and must be saved;
- the receipt can be used to check progress without signing in;
- completion is not reported until every applicable system has confirmed deletion;
- data that must be retained under a specific legal/regulatory basis is isolated, access-restricted, minimized and disclosed to the customer.

Do not use account suspension/deactivation as the final deletion outcome.

## API foundation

- `POST /api/v1/account/deletion-request`: authenticated, requires a session created within 15 minutes and exact confirmation phrase. It changes `app_users.status` to `deletion_pending`, revokes all sessions, creates a request and five system steps, and returns a one-time receipt.
- `GET /api/v1/account/deletion-status`: accepts `X-Deletion-Receipt` and returns only request status and system-step status. Receipt is stored only as SHA-256 and expires after 90 days.
- `account_deletion_core.complete_deletion_step`: internal worker primitive for recording independently verified external steps. Never expose it as a customer endpoint.
- `account_deletion_core.process_primary_database_deletion`: refuses to purge PostgreSQL identity records until all external/system steps are `completed` or `not_applicable`. It deletes the user-linked identity, sessions, consent events, OTP challenges and user-attributed audit events; removes orphaned personal tenants; preserves shared tenants for remaining members; and retains only the minimal deletion receipt/progress record.

## Required system gates

1. `connected_providers`: revoke user-specific OAuth grants with each provider, then delete locally stored provider credentials. Never delete KAPPA's own operational Google/LinkedIn integration accounts as if they belonged to a customer.
2. `app_storage`: delete user-owned objects from every remote object store. Android private local data is removed by the client app; server-side confirmation must not pretend to remotely erase a device that is offline.
3. `backups`: ensure deleted data is not restored from backups. Track the actual backup retention/expiry policy and ensure restored snapshots reapply deletion tombstones before becoming available.
4. `legal_retention`: identify any record that has a documented legal/regulatory retention basis. Keep only the minimum required fields, segregate and restrict access, record the basis and expiry, and disclose the exception. Otherwise mark not applicable.
5. `primary_database`: only after the four gates above are confirmed, perform the final PostgreSQL purge.

## Operational safety

- The API/schema and PostgreSQL purge primitive are foundations, not proof that the entire end-to-end deletion service is live.
- Do not mark external steps complete without provider/storage/backup evidence.
- Do not mark a request completed while any applicable step is pending, blocked or failed.
- Do not delete shared tenant data when other active members still own it.
- Do not delete project-wide operational credentials, editorial content or analytics rows that are not linked to the requesting customer.
- A worker/scheduler, provider revocation adapters, Android local purge handshake, object-store inventory, backup tombstone/replay handling, public web deletion page and privacy-policy retention schedule must be completed before production launch.
- Keep the PR in Draft until these gates and the product's actual data inventory are validated.
