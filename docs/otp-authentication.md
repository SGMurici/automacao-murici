# OTP authentication foundation

## Scope

The backend has one provider-agnostic OTP lifecycle in \`otp_core.py\`. Email signup/login routes are implemented but fail closed behind \`AUTH_ROUTES_ENABLED=false\` by default. They do not become operational until the SES sender, independent secrets and trusted Render proxy chain are configured and validated.

## Unified challenge lifecycle

1. Normalize the identity with \`identity_lookup.normalize_identity\` and derive its lookup key with \`identity_lookup.hash_identity_lookup\`. Persist only the keyed digest in identity and challenge lookup columns; keep the encrypted identity value separately.
2. Reserve resend quota in the existing shared \`otp_request_limits\` table using \`otp_core.reserve_otp_request_slot\`. The current HTTP routes reserve identity and canonical client IP before generating a challenge. Device quota remains optional and is not currently applied; no hardware fingerprint is collected.
3. Create the challenge with \`otp_core.create_otp_challenge\`. It generates an eight-digit code and stores only HMAC-SHA-256 bound to challenge ID and purpose. The raw code is returned once to the private delivery adapter.
4. The adapter sends the message over authenticated TLS. Never log, persist in plaintext, return to the browser, or include the code in analytics.
5. Finalize delivery with \`otp_core.mark_otp_delivery\`. A confirmed send records delivery metadata and cooldown; a failed delivery consumes the challenge so an undelivered code cannot later be used.
6. Verify with \`otp_core.verify_otp_challenge\`. It locks the row, checks purpose, expiry, delivery state and attempts, compares the keyed digest, increments failed attempts or consumes a valid code atomically.

## Fixed safeguards

- Eight numeric digits, generated with a cryptographically secure random source.
- HMAC-SHA-256 digest bound to challenge ID and purpose.
- OTP pepper: at least 32 random bytes, backend-only and separate from identity lookup, rate-limit, Flask, OAuth and publishing secrets.
- TTL: 60–900 seconds; default 600 seconds.
- Attempts: 1–10; default 5.
- Purposes: signup, login, verify_identity and recovery.
- Identity types: email and phone.
- A challenge cannot be verified until delivery is marked sent.
- Successful verification is single-use; failed delivery consumes the challenge.
- Rate limiting uses the existing \`otp_request_limits\` ledger from migration 0005. It is shared across workers and supports identity, IP and device dimensions, separated by purpose.
- Identity/IP/device limiter keys are keyed HMAC digests. Normalize identity first; canonicalize IP and derive it only from trusted proxy configuration.

## Schema evolution

Migration \`0009_identity_otp_hardening.sql\` is additive to migration 0002. It adds optional user ownership, delivery timestamps, resend cooldown and provider reference to \`otp_challenges\`, plus indexes and consistency constraints. Migration \`0010_otp_signup_policy_versions.sql\` stores the exact terms and privacy-notice versions on signup challenges. The versions are recorded in consent/audit events only after successful e-mail verification, not merely when an unverified address requests a code. The migrations do not create a second rate-limit ledger: migration 0005 and \`otp_request_limits\` remain the single shared quota mechanism.

## Operational requirements before public routes

- Select and configure a transactional email provider; SMS is not assumed.
- Verify a controlled sender domain and configure SPF, DKIM and DMARC.
- Keep \`OTP_PEPPER\`, \`IDENTITY_LOOKUP_PEPPER\` and \`OTP_RATE_LIMIT_PEPPER\` separate in the backend secret manager; share the same key across instances and plan rotation deliberately.
- Use generic API responses to prevent account enumeration.
- Apply identity and trusted-proxy-derived IP quotas before challenge creation; device quota is a later optional control.
- Define provider failure handling, alerting, suppression handling and log retention.
- Connect successful signup verification to activation of the user and creation of the personal tenant plus owner membership in one transaction.
- Permit login only for active users with a verified identity.
- Add session issuance/rotation/revocation only after successful OTP verification.
- Test replay, expiry, concurrent verification, delivery failure, rate limits, rollback, tenant isolation and account recovery.
- Unverified pending signup records are purged by the scheduler after `PENDING_SIGNUP_TTL_HOURS` (24 hours by default); formally approve this retention period and monitor the cleanup before public activation.
- Complete privacy notice and LGPD review for authentication processing, email provider and retention before public activation.

Routes exist in code but remain disabled by default. No provider account, credential, production setting or external message was created. No production migration, merge or deployment is authorized by this foundation. See \`docs/auth-email-otp-rollout.md\` for the activation gates.
