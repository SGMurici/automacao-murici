# Identity onboarding and email OTP — implementation design

**Status:** design baseline for review; not production-ready.  
**Parent code baseline:** PR #16 HEAD `ca63c5ed1ec2a44e0ef4750c2fd0a8138e5dbf49`.  
**Branch:** `feat/identity-email-otp-design-2026-11-11`.  
**Scope:** email-based signup, verification, login, recovery prerequisites and later operational-admin enrollment for the approved Android application, backed by the existing Flask/PostgreSQL service.  
**Explicit non-goals:** applying migrations, sending real email, selecting/contracting an email provider, changing Render secrets, creating Murici's account, enabling production routes, merging or deploying.

## 1. Findings from inspected code

- `migrations/0002_identity_core.sql` defines `app_users`, `user_identities`, `tenants`, `tenant_memberships`, `auth_sessions`, `otp_challenges`, `consent_events`, `external_connections` and `audit_events`.
- `migrations/0006_session_authentication_freshness.sql` adds `authenticated_at` to sessions. It is needed because rotation must not refresh the time of the last successful identity authentication.
- `identity_core.issue_session()` creates an opaque 48-byte-url-safe session token and stores only its SHA-256 digest. It assumes authentication has already succeeded.
- `validate_session()`, `is_recent_session()`, `rotate_session()`, `revoke_session()` and `revoke_all_sessions()` are session primitives, not a login flow.
- `app.py` currently exposes `/api/v1/me`, `/api/v1/session/rotate`, account deletion request/status and logout. It has no signup, login, OTP issuance, OTP verification or email delivery route.
- `requirements.txt` contains Flask, Gunicorn, psycopg and cryptography. No transactional email SDK/provider is currently declared.
- `authorization_core.py` provides tenant-scoped roles and audit/consent primitives. A tenant's `owner` or `admin` role must never imply global operational-admin access.
- The identity migrations have not been applied to production. The production database snapshot contains no identity tables.

## 2. Account lifecycle

### Signup
1. Accept a normalized email and only the minimum signup fields required to create an account.
2. Apply request validation, IP and identity rate limits before generating a challenge.
3. Create an `app_users` row with status `pending` and an unverified `user_identities` row, or reuse an existing pending signup state without creating duplicates.
4. Issue a purpose-bound `signup` OTP. Do not create a tenant or owner membership yet.
5. Return a generic acknowledgement that does not disclose whether an account exists. Never return the code.

### Verify signup
1. Require challenge ID and code; never accept a client-supplied user ID as the authority.
2. Atomically consume one unexpired, unconsumed challenge whose purpose is `signup`, whose delivery state is `sent`, and whose attempts remain.
3. Compare a keyed HMAC of the normalized code using a dedicated server-side pepper; use constant-time comparison in application code where comparison is not performed inside a single SQL update.
4. On success, mark the identity verified and activate the pending user; create a personal tenant and `owner` membership in the same database transaction.
5. Emit a session only after the transaction's state checks succeed. The raw session token is returned once with `Cache-Control: no-store`.
6. Repeated verification must not create another tenant, membership, consent event or session. A replay returns a generic invalid/expired result.

### Login
1. Accept email and request a purpose-bound `login` challenge only for an active user with a verified email identity.
2. Use the same response shape and comparable timing for unknown, pending, suspended and active accounts. Do not send a login code to an unverified or unknown address.
3. Verify the OTP atomically, then call `identity_core.issue_session()` for the user resolved by the challenge record.
4. Suspended/deleted/pending accounts never receive a session.

### Recovery and email change
- Recovery must be a separate purpose and state machine; do not treat signup/login OTP as recovery proof.
- Recovery must revoke existing sessions after successful identity recovery and notify the previously verified address when feasible.
- Email change requires recent authentication plus verification of the new address; do not silently replace the primary identity.
- Do not implement recovery in the first coding increment until its threat model and support process are specified.

## 3. OTP controls

Initial values below are configuration candidates, not immutable product promises. Validate with tests and abuse simulation before release.

| Control | Initial proposal | Rationale |
| --- | --- | --- |
| Code | 8 decimal digits from a cryptographically secure RNG | Usable manually; high entropy for short-lived challenge |
| Lifetime | 10 minutes | Balances usability and exposure window |
| Attempts | 5 per challenge | Bounds online guessing |
| Resend cooldown | 60 seconds | Limits nuisance and delivery cost |
| Per-identity sends | 3 per 30 minutes, 8 per 24 hours | Controls provider cost and abuse |
| Per-IP requests | Configurable sliding window, initially 10 per 15 minutes | Mitigates bulk abuse; trust only canonical client IP |
| Active challenge | One active challenge per identity + purpose | Avoids ambiguity and stale codes |
| Delivery timeout | Bounded provider request timeout | Prevents request workers from hanging |

Security requirements:
- Generate codes with `secrets`, never `random`.
- Store only `HMAC-SHA-256(OTP_PEPPER, challenge_id || purpose || code)`; never store plaintext OTP or a plain SHA-256 hash of a low-entropy code.
- `OTP_PEPPER` must be a distinct secret from `FLASK_SECRET_KEY`, `PUBLISH_SECRET` and `TOKEN_ENCRYPTION_KEY`. Missing secret fails closed.
- `OTP_DELIVERY_ENCRYPTION_KEY` must be a valid Fernet key and distinct from `IDENTITY_ENCRYPTION_KEY`, `TOKEN_ENCRYPTION_KEY` and all peppers. Missing or reused key fails closed.
- Bind the digest to challenge ID and purpose to prevent cross-challenge/cross-purpose reuse.
- Use database time for expiry and server timestamps for audit.
- Make challenge verification one-time and concurrency-safe using a row lock or one conditional `UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW() AND failed_attempts < max_attempts RETURNING ...`.
- Increment failed attempts atomically. At the limit, consume/lock the challenge.
- Invalidate the previous active challenge when a new one is accepted for delivery.
- Do not reveal whether the email is registered, pending, suspended or deleted.
- Never log codes, email bodies, raw provider responses, bearer tokens or OTP pepper.
- Store provider message ID only if needed for delivery diagnostics; sanitize and minimize it.
- Do not rely on application memory for rate limits; multiple Gunicorn workers and instances require shared durable coordination.

## 4. Schema changes required before route implementation

The current `otp_challenges` table is a starting point, not a complete production contract. An additive migration (proposed `0009_identity_otp_hardening.sql`) should be drafted and tested on a disposable Neon branch before any production migration.

Candidate additions:
- `user_id UUID NULL REFERENCES app_users(id) ON DELETE CASCADE` to bind a challenge to the resolved account when applicable.
- `delivery_attempted_at`, `sent_at`, `resend_after`, and a bounded provider delivery reference/status.
- A challenge purpose/status constraint and index supporting lookup of active challenges by identity, purpose and creation time.
- A partial uniqueness or transaction/lock strategy that prevents multiple active challenges for one identity/purpose without making resend races possible.
- Reuse the existing `otp_request_limits` table from migration 0005 as the single shared rate-limit ledger. It supports identity, IP and device dimensions per purpose; derive dimension hashes with a backend-only HMAC pepper and apply IP canonicalization before hashing. Do not create a parallel OTP limiter table.
- An explicit account activation invariant: only verified primary email identities can transition a user from pending to active through the signup verification transaction.

Do not store raw IP indefinitely. If IP-based abuse protection needs persistence, use short retention and a documented lawful purpose. Do not store the email in challenge rows if the identity table can resolve it; if provider delivery needs a transient value, decrypt only inside the delivery adapter and never log it.

Migration acceptance:
- additive and repeatable where feasible;
- no rewrite or reassignment of existing operational Google/LinkedIn rows;
- foreign keys and check constraints tested;
- concurrency tests against PostgreSQL 16;
- migration applied only to a disposable child branch first;
- no production execution without separate explicit authorization.

## 5. Email delivery adapter and provider decision

The HTTP request must not open an SMTP connection or wait for a provider. Use a transactional outbox so the OTP challenge and its delivery intent commit atomically.

### Outbox contract

- `otp_email_outbox` has one row per challenge (`challenge_id` unique), encrypted payload, `pending|processing|sent|failed` state, attempt counters, `available_at`, lease token/expiry, sanitized error code, provider reference and timestamps.
- The payload contains only the normalized recipient, OTP, purpose, challenge ID and expiry window. Encrypt it with a dedicated Fernet key `OTP_DELIVERY_ENCRYPTION_KEY`; require this key to be distinct from identity/token encryption keys and all peppers. Never persist plaintext OTP or recipient in the outbox row.
- Create the challenge and encrypted outbox row in the same PostgreSQL transaction. If encryption or enqueue fails, roll back both.
- The API returns the same generic `202 accepted` contract after commit. It does not claim that the message has been delivered.
- A one-shot worker claims due rows with `FOR UPDATE SKIP LOCKED`, increments attempts and assigns a lease token/expiry. It commits the claim before calling SMTP.
- On provider confirmation, the worker updates the challenge to `sent` and the outbox to `sent` in one transaction, records only the provider reference and erases the encrypted payload.
- On transient failure, retry with bounded exponential backoff while retaining the encrypted payload. An expired processing lease can be reclaimed by another worker.
- On terminal failure, expiration or exhausted attempts, mark the challenge `failed` and consumed, mark the outbox `failed`, and erase the encrypted payload.
- A timeout after the SMTP server accepted a message can cause a duplicate delivery on retry. The retry must reuse the same challenge and code; never mint a second code merely because delivery acknowledgement was uncertain.
- Use bounded SMTP timeouts and a maximum lease longer than the SMTP timeout. A worker that lost its lease must not finalize another worker's claim.
- Logs contain job/challenge IDs and a sanitized error class only; never log OTP, ciphertext, recipient, email body, credentials or raw provider response.

The outbox worker is a separate command, not a Flask request hook or an implicit in-process scheduler. Production scheduling, provider credentials and worker deployment remain disabled until separately reviewed.

Do not use a personal Gmail account as the transactional mail system by default. It couples authentication availability to a personal mailbox, increases account-security risk and creates operational limits. Compare provider cost, deliverability, Brazilian domain/DNS setup, data processing terms, data residency, logs, support and sender reputation before selecting one. The provider is not selected in this design.

## 6. API contract proposal (Android client / Flask backend)

- `POST /api/v1/auth/signup`: request signup and send verification code; generic 202 response.
- `POST /api/v1/auth/signup/verify`: consume signup challenge; activate account and create personal tenant; issue bearer session.
- `POST /api/v1/auth/login`: request login code; generic 202 response.
- `POST /api/v1/auth/login/verify`: consume login challenge; issue bearer session.
- `POST /api/v1/auth/recovery` and verification routes: explicitly out of first implementation increment.
- Existing `/api/v1/me`, `/api/v1/session/rotate` and `/api/v1/logout` remain compatible.

All auth responses:
- `Cache-Control: no-store`;
- strict JSON schema and request size limits;
- no account enumeration;
- no code, raw identity hash, user UUID or provider payload in public response;
- no CORS wildcard with credentials;
- rate limiting at API and provider boundary;
- no bearer token in URL, analytics or browser localStorage.

The current product direction (decision dated 10/11/2026) is migration of the same product to an Android application; the Lovable PWA is an earlier web prototype, not the approved primary client. Keep authentication in the Flask backend and do not introduce a second identity provider. For Android, use platform-backed secure storage (Android Keystore-backed encrypted storage) for refresh/session material, never SharedPreferences/plain files; prefer short-lived access tokens held in memory and rotate/revoke sessions server-side. Evaluate cookie-based auth only if a future web client needs it, with explicit CSRF/origin controls. Confirm the actual Android repository/framework and networking stack before selecting the client transport. Do not silently assume the PWA is the target.

## 7. Tenant creation and privilege boundaries

- The user starts as `pending`.
- Successful signup verification performs, in one transaction: verify identity, activate user, create one `personal` tenant, insert one active `owner` membership.
- Enforce idempotency with database constraints and transaction-level locking; repeated OTP verification cannot create duplicate personal tenants.
- Client input must never choose `tenant_id`, `role`, `status`, `verified_at`, `user_id` or admin privileges.
- Family Plan billing membership is separate from personal data ownership. A billing relationship must not grant access to another member's career data.
- Global KAPPA operational admin remains a separate server-controlled authorization binding, not a tenant role.

## 8. Murici operational-admin bootstrap

After the end-to-end signup/login flow is tested and deployed under explicit authorization:
1. Murici creates an individual account through the normal signup flow.
2. The authenticated `/api/v1/me` response supplies the user UUID.
3. A server-side, separately reviewed configuration binds `KAPPA_ADMIN_USER_ID` to that UUID.
4. Admin-only routes require a valid session, recent authentication for sensitive operations, and exact match against the configured UUID.
5. Missing/malformed config fails closed.
6. Never create the user directly in production SQL, never guess the UUID, never accept `operator_id` from the client.

This document does not authorize any of these production actions.

## 9. Required automated test matrix

### Signup and activation
- new email creates exactly one pending user and unverified identity;
- duplicate requests do not create duplicate identities;
- unverified user has no session and no tenant;
- valid signup OTP activates once and creates exactly one personal tenant + owner membership;
- replay, expired, wrong-purpose, failed-delivery and consumed OTPs do not activate;
- parallel verification requests produce one success only.

### Login and sessions
- active verified account can request and verify login OTP;
- unknown, pending, suspended and deleted accounts return indistinguishable public responses;
- only verified active accounts receive sessions;
- raw session token never stored; only digest persists;
- session expiry, revocation, rotation and recent-auth timestamp remain correct.

### Abuse and privacy
- attempt limit is enforced under concurrency;
- resend cooldown and identity/IP quotas work across multiple workers;
- canonical IP parser trusts only configured proxy chain;
- no account enumeration through status, body or meaningful timing differences;
- no OTP, token, email body or secret appears in logs;
- delivery provider timeout/failure cannot leave a usable challenge;
- database outage fails closed.

### Tenant and authorization
- user cannot select another tenant or role in request payload;
- repeated signup/verification cannot create duplicate tenant;
- one user's session cannot read another user's profile;
- tenant owner/admin does not gain global operational privilege;
- audit events derive actor from validated server session.

## 10. Legal, privacy, cost and rollout gates

- The approved platform direction as of 10/11/2026 is an Android application. The existing Lovable PWA is a legacy prototype; do not treat it as the primary product client or build a parallel PWA auth flow unless the owner explicitly changes direction.

- Publish a clear privacy notice explaining why email is collected (account authentication, security and essential account communications), retention and provider processing.
- Separate authentication necessity from optional marketing consent; never bundle them.
- Record the applicable privacy notice version and acknowledgement where legally required; do not treat an OTP as blanket consent to all product processing.
- Document controller/operator roles, provider DPA/terms, international transfer safeguards if applicable, incident handling, retention and deletion behavior under LGPD.
- Keep only minimum account data; avoid date of birth, full home address or phone unless a justified feature requires them.
- Do not select SMS in the first release; it adds cost and personal-data collection without a demonstrated requirement.
- Keep email provider spend variable and capped; instrument sends, bounces, failures and abuse before estimating per-user cost.
- Begin with internal test addresses and a non-production provider/domain configuration. Expand only after security tests, legal review and operational monitoring.
- Keep production DB, Render, OAuth, LinkedIn publishing and public product unchanged until separate approval.

## 11. Implementation sequence

1. Locate/confirm the Android application repository, framework and networking stack; define secure session transport for Android. Treat the Lovable PWA as a legacy prototype unless the product owner reverses the 10/11/2026 decision. Choose a transactional email provider after cost/legal comparison.
2. Draft migration 0009 and pure OTP core helpers (normalization, HMAC, challenge policy, rate-limit policy).
3. Test helpers and migration on isolated PostgreSQL 16.
4. Implement provider adapter and delivery-failure state handling.
5. Implement signup/verify, then login/verify; do not combine recovery into the first slice.
6. Add abuse, concurrency, enumeration and tenant-isolation tests.
7. Run full CI and security review; keep PR Draft.
8. Review migration diff and test results; ask separately before any production migration, secret change, merge or deploy.
9. Only after authorized release, create Murici's account and bind the operational admin UUID.
10. Then implement the audited LinkedIn reconciliation workflow using the verified individual admin session.

## 12. Current blockers / decisions to batch

1. **Email provider:** choose only after comparing cost, deliverability, domain/DNS, data processing terms and operational complexity. Recommendation: dedicated transactional provider, not personal Gmail; no provider selected yet.
2. **Android client/session transport:** locate the actual Android source and confirm framework, secure-storage implementation and token lifecycle. The Lovable PWA is not the approved primary client under the 10/11/2026 platform decision.
3. **Sender domain:** identify a domain/subdomain controlled by the project for SPF, DKIM and DMARC. Do not invent or configure DNS.
4. **Legal text:** approve authentication-specific privacy notice and retention language with Brazilian privacy counsel before public signup.

No production changes, email sends, database writes, migrations, secret changes, account creation, merge or deploy were performed while preparing this design.
