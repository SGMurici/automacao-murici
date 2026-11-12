# Identity authentication API — email OTP

## Status and activation boundary

The existing signup/login API contract has been consolidated and its schema dependencies corrected. The routes remain disabled by default and fail closed unless the feature flag, separate secrets, legal-document versions, SMTP configuration and trusted proxy allowlist are valid.

This flow supports email only. Phone/SMS, account recovery, email changes and administrator bootstrap remain separate scopes.

## Endpoints

### Signup — request a code

\`POST /api/v1/auth/signup/request\`

\`\`\`json
{
  "email": "customer@example.com",
  "terms_accepted": true,
  "privacy_notice_acknowledged": true,
  "device_id": "optional app-generated UUID"
}
\`\`\`

- Both legal acknowledgements are required for signup.
- The server binds the configured \`TERMS_POLICY_VERSION\` and \`PRIVACY_NOTICE_VERSION\` to the OTP challenge in migration 0010. Client-supplied policy versions are never trusted.
- The endpoint returns HTTP 202 with a generic response and a challenge UUID. Ineligible addresses receive a random UUID in the same response shape; the UUID is not a secret and the OTP is never returned.
- A new account remains pending and has no tenant until successful email verification.
- Repeated requests consume the previous active challenge and issue a new one only when quotas allow.

### Signup — verify the code

\`POST /api/v1/auth/signup/verify\`

\`\`\`json
{
  "challenge_id": "challenge UUID returned by the request endpoint",
  "code": "12345678",
  "display_name": "Optional display name",
  "device_id": "optional app-generated UUID",
  "device_label": "Optional device label"
}
\`\`\`

On success, one database transaction verifies the email, activates the pending user, creates a personal tenant and owner membership, records the terms/privacy acknowledgement and issues a seven-day revocable bearer session.

### Login — request and verify

- \`POST /api/v1/auth/login/request\`: \`{"email":"customer@example.com","device_id":"optional app-generated UUID"}\`
- \`POST /api/v1/auth/login/verify\`: \`{"challenge_id":"challenge UUID","code":"12345678","device_label":"Optional device label"}\`

Login sends an OTP only for an active user with a verified email. Successful verification records an audit event and issues a seven-day revocable bearer session.

The authenticated session can be checked at \`GET /api/v1/me\`, rotated at \`POST /api/v1/session/rotate\` and revoked at \`POST /api/v1/logout\`. Send it only in \`Authorization: Bearer <token>\`. Access-token responses use \`Cache-Control: no-store\` and \`Pragma: no-cache\`.

## Required backend configuration

All keys must be generated independently, kept backend-only and shared consistently across app instances. Do not reuse a key for another purpose.

- \`AUTH_ROUTES_ENABLED=true\`: explicit feature flag. It remains false by default.
- \`IDENTITY_LOOKUP_PEPPER\`: at least 32 random bytes; HMAC lookup hashes for normalized email.
- \`IDENTITY_ENCRYPTION_KEY\`: valid Fernet key dedicated to identity ciphertext; separate from OAuth \`TOKEN_ENCRYPTION_KEY\` and all peppers.
- \`OTP_PEPPER\`: at least 32 random bytes; HMAC OTP challenge digest.
- \`OTP_RATE_LIMIT_PEPPER\`: at least 32 random bytes; pseudonymous identity/IP/device quota hashes.
- \`TRUSTED_PROXY_HOPS\`: exact number of trusted proxies appending to the forwarded chain (1–5).
- \`TRUSTED_PROXY_CIDRS\`: comma-separated CIDRs for the direct proxy peer and each intermediate trusted proxy. The application validates the peer and intermediate chain; do not use \`0.0.0.0/0\` or \`::/0\`.
- \`TERMS_POLICY_VERSION\`: identifier of the published terms version.
- \`PRIVACY_NOTICE_VERSION\`: identifier of the published privacy notice version.
- SES SMTP: \`SMTP_HOST=email-smtp.sa-east-1.amazonaws.com\`, \`SMTP_PORT=587\`, \`SMTP_FROM\`, \`SMTP_USERNAME\`, \`SMTP_PASSWORD\`, \`SMTP_USE_TLS=true\`, \`SMTP_USE_SSL=false\`.

Existing \`TOKEN_ENCRYPTION_KEY\` remains required for OAuth tokens and must not be replaced with the identity key.

## Abuse controls

- OTP issuance: five requests/hour per identity with 60-second identity cooldown; 100/hour per IP; ten/hour per optional device with 60-second device cooldown.
- Verification: ten/hour per identity, 100/hour per IP and twenty/hour per optional device. Verification uses domain-separated buckets in the same \`otp_request_limits\` table.
- Each challenge expires after 10 minutes, permits five failed attempts and can be consumed only once.
- Only HMAC digests of identity and abuse dimensions are stored in lookup/limiter columns. Normalized email is encrypted separately.
- The device identifier is optional and must be an app-generated opaque UUID, never IMEI, advertising ID, hardware serial or another persistent hardware identifier.
- Client IP is accepted only when the direct peer and intermediate proxy chain match the configured CIDRs. Raw client-supplied forwarding headers are not trusted.

## SES and sender-domain prerequisites

Before enabling delivery:
1. Confirm control of the sender domain/subdomain in SES \`sa-east-1\`.
2. Publish SES-provided DKIM records and configure SPF and DMARC.
3. Move SES out of sandbox and verify production sending limits.
4. Create SMTP credentials for a least-privilege IAM identity; do not use root credentials or paste AWS access keys into the app.
5. Store the SMTP username/password in Render's secret manager; never commit them.
6. Test delivery, bounce/complaint handling, suppression and alerting before public release.

Recommended sender: a dedicated address such as \`nao-responda@auth.<controlled-domain>\`, only after the actual domain is confirmed.

## Legal and operational gates

- Publish and version the terms and privacy notice before setting their version environment variables.
- Explain the purpose of email verification and retain only required delivery/security metadata.
- Review SES DPA, subprocessors, data location, international transfer mechanism under LGPD and retention terms.
- Verify the exact Cloudflare → Render proxy chain and CIDRs in a controlled non-production service before configuring \`TRUSTED_PROXY_HOPS\` and \`TRUSTED_PROXY_CIDRS\`.
- Abandoned pending users are purged by the scheduler after 24 hours by default; `PENDING_SIGNUP_TTL_HOURS` can be set from 1 to 168. Define separate cleanup/retention for stale OTP challenge and limiter rows.
- Apply migrations 0002, 0005, 0006, 0009 and 0010 only through the separately authorized production migration process.
- Add recovery and email-change workflows only after signup/login are validated.

## Security boundary

No production secrets, Render environment variables, sender-domain DNS, SES account, production schema, customer identity or administrator identity were changed by this implementation. SMTP delivery is mocked in the PostgreSQL integration tests.


## OTP delivery uncertainty

SMTP is not an exactly-once transport. If the connection drops during message submission or after the provider accepts the message but before its final response reaches KAPPA, the system cannot prove whether the email was delivered.

The worker therefore commits an outbox `dispatching` state before SMTP. An ambiguous outcome is recorded as `uncertain`, not retried. The encrypted code payload is erased and the associated OTP challenge is consumed, so a possibly delivered code cannot be used. The user must request a new challenge after the normal rate-limit cooldown. This deliberately favors avoiding duplicate messages and invalid/late-code confusion over silently retrying an unknown delivery.

A worker crash after entering `dispatching`, or a database failure after SMTP reports success but before the result is committed, also resolves to `uncertain` when the lease expires. Monitoring must alert on the worker's non-zero exit and uncertain counter.
