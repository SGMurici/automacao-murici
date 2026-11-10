# OTP authentication foundation

## Scope

The backend now contains provider-agnostic OTP challenge primitives in `otp_core.py`. This is an internal foundation only. It does not send email/SMS, expose a public OTP route, create accounts, authenticate a customer end to end, or issue the first application session.

## Challenge lifecycle

1. The authenticated server flow normalizes the email/phone with `identity_lookup.normalize_identity` and supplies only the HMAC-SHA256 lookup digest from `identity_lookup.hash_identity_lookup` to the core. Never use an unkeyed SHA-256 digest for an email address or phone number.
2. `create_otp_challenge` generates a six-digit code, binds its HMAC-SHA256 digest to the random challenge ID, and stores only the digest.
3. A private delivery adapter receives the raw code once and sends it through the approved provider. The code must never be logged, persisted in plaintext, returned to the browser, or included in analytics.
4. After the provider responds, the adapter marks delivery as `sent` or `failed`. Verification only accepts `sent` challenges.
5. `verify_otp_challenge` locks the challenge row, checks expiry, delivery state, consumption and attempt count, then consumes a valid challenge atomically. Invalid codes increment the attempt counter.

## Fixed safeguards

- Six numeric digits.
- HMAC-SHA256 digest keyed by an injected pepper of at least 32 bytes.
- Digest is bound to the challenge ID to prevent cross-challenge reuse.
- TTL: 60–900 seconds; default 300 seconds.
- Attempts: 1–10; default 5.
- Purposes: signup, login, verify_identity and recovery.
- Identity types: email and phone.
- A challenge cannot be verified until delivery is marked sent.
- A successful code is single-use.

## Operational requirements before public routes

- Choose and configure an email delivery provider; SMS is not assumed.
- Keep the pepper in the backend secret manager; never in source control or frontend configuration.
- Define resend cooldowns and rate limits by identity, IP/device and purpose.
- Define abuse monitoring, generic responses that prevent account enumeration, and provider failure handling.
- Complete email normalization and verified-identity lookup rules.
- Connect OTP success to the approved signup/login/recovery flow and session issuance.
- Add authenticated onboarding and versioned consent capture before enabling customer data features.
- Test delivery failure, replay, concurrent verification, expiry, rate limiting and recovery.
- Do not activate customer authentication until the delivery adapter and abuse controls are reviewed.

No provider account, credential, route, production setting or external message was created by this implementation.


## OTP resend and abuse throttling

Migration `0005_otp_request_limits.sql` adds an atomic quota ledger keyed by a dimension type, a pseudonymous 32-byte dimension digest and OTP purpose. The core exposes `reserve_otp_request_slot`, which enforces a resend cooldown and a fixed-window request quota in one PostgreSQL UPSERT. Concurrent requests for the same dimension cannot both bypass the quota.

The caller should reserve all dimensions available for a request (identity, IP and device) before creating or delivering a challenge. Generate the dimension digest with `otp_core.hash_otp_rate_limit_dimension`, which uses HMAC-SHA-256 with a backend-only pepper and domain-separates identity, IP and device values. Normalize the value according to its type before calling the helper. Never use a plain hash of an email, phone number, IP address or device identifier. Keep the HMAC key in the secret manager and rotate it only with a deliberate migration/expiry plan. Do not store raw dimensions in this table or logs.

Default policy in the primitive: 60-second cooldown, at most 5 requests per 60-minute window per dimension and purpose. Parameters are validated and can be adjusted by the application policy. These limits are a foundation; final thresholds require monitoring and abuse testing before public signup/login routes are enabled.

The new primitive does not send messages, expose routes or activate OTP authentication. The provider, public endpoints, generic anti-enumeration responses, distributed IP/device fingerprinting strategy and operational alerting remain pending.


## Identity normalization and privacy-preserving lookup

Use `identity_lookup.normalize_identity(identity_type, value)` before any identity lookup or OTP rate-limit reservation:

- Email: trim whitespace, normalize the local part with Unicode NFC and case-folding, convert the domain to IDNA ASCII lower-case, and reject malformed or oversized values.
- Phone: require an explicit international country code and normalize to E.164. Do not infer a country from device locale or IP address.
- Lookup: use `identity_lookup.hash_identity_lookup(identity_type, value, IDENTITY_LOOKUP_PEPPER)`. The helper applies HMAC-SHA256 with domain separation and returns a 32-byte digest suitable for `user_identities.identity_lookup_hash` and `otp_challenges.identity_lookup_hash`.
- Keep `IDENTITY_LOOKUP_PEPPER` separate from the OTP-code pepper and rate-limit pepper, at least 32 random bytes, stored only in the backend secret manager and identical across app instances.
- Never log raw identity values or persist them outside the encrypted identity-value column.
- Do not rotate this key casually. Rotation requires recomputing lookup digests for all stored identities and active OTP challenges. A plain SHA-256 digest cannot be converted to HMAC without recovering the original identity from its encrypted value; if that is impossible, require identity re-verification before enabling the new key.

The helper is provider-agnostic and does not create routes or activate authentication. Before connecting any signup/login route, confirm that every caller uses the same normalization and keyed digest path.
