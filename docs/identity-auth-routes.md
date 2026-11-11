# Identity authentication API — email OTP

## Status and activation boundary

The email OTP signup/login routes are implemented behind fail-closed configuration checks. They are not operational in production until the required secrets, SES SMTP sender, published legal-document versions and verified Render proxy chain are configured. No production migration, Render setting or real email delivery is part of this change.

The flow currently supports email only. Phone/SMS, account recovery, identity changes and administrator bootstrap are separate follow-up scopes.

## Endpoints

### Request a code

\`POST /api/v1/auth/otp/request\`

Request JSON:

\`\`\`json
{
  "email": "customer@example.com",
  "purpose": "signup",
  "device_id": "a stable app-generated UUID"
}
\`\`\`

- \`purpose\` is \`signup\` or \`login\`.
- \`device_id\` is optional and must be an app-generated opaque UUID. Do not use IMEI, advertising ID, hardware serial or other persistent hardware identifier.
- The endpoint returns HTTP 202 with the same generic response for eligible and ineligible addresses.
- It does not return the challenge ID or OTP.
- Signup creates a pending user and stores the email encrypted with a dedicated identity key. No tenant is created yet.
- Login only sends a code for an active user with a verified email.

### Verify a code

\`POST /api/v1/auth/otp/verify\`

Signup request JSON:

\`\`\`json
{
  "email": "customer@example.com",
  "code": "12345678",
  "purpose": "signup",
  "accept_terms": true,
  "acknowledge_privacy": true,
  "display_name": "Optional display name",
  "device_label": "Optional device label"
}
\`\`\`

Login uses the same endpoint with \`purpose: "login"\`; terms/privacy fields are not required.

- Verification uses the latest unexpired, delivered, unconsumed challenge for the normalized email and purpose.
- OTPs expire after 10 minutes, allow five failed attempts and are single-use.
- Signup acceptance is validated before the code is consumed. Policy versions are read only from backend configuration.
- Successful signup activates the user, marks the email verified, creates a personal tenant and owner membership, records terms/privacy acknowledgement and issues a seven-day revocable bearer session in one database transaction.
- Login requires an active user and verified email, records an audit event and issues a seven-day revocable bearer session.
- Responses containing the access token use \`Cache-Control: no-store\` and \`Pragma: no-cache\`.

The authenticated session can be checked at \`GET /api/v1/me\`, rotated at \`POST /api/v1/session/rotate\` and revoked at \`POST /api/v1/logout\`. Send it only in \`Authorization: Bearer <token>\`.

## Required backend configuration

All keys below must be backend-only, generated independently and shared consistently across application instances. Never reuse a key for another purpose.

- \`IDENTITY_LOOKUP_PEPPER\`: at least 32 random bytes; HMAC lookup hashes for normalized email.
- \`IDENTITY_ENCRYPTION_KEY\`: valid Fernet key dedicated to identity ciphertext. Separate from OAuth \`TOKEN_ENCRYPTION_KEY\`.
- \`OTP_PEPPER\`: at least 32 random bytes; HMAC OTP challenge digest.
- \`OTP_RATE_LIMIT_PEPPER\`: at least 32 random bytes; pseudonymous identity/IP/device quota hashes.
- \`OTP_TRUSTED_PROXY_HOPS\`: exact number of trusted proxies that append to the right side of the forwarded IP chain. Do not guess this value. The route fails closed if missing, invalid or if the forwarded chain is incomplete.
- \`TERMS_POLICY_VERSION\`: identifier of the published terms version.
- \`PRIVACY_NOTICE_VERSION\`: identifier of the published privacy notice version.
- SES SMTP: \`SMTP_HOST=email-smtp.sa-east-1.amazonaws.com\`, \`SMTP_PORT=587\`, \`SMTP_FROM\`, \`SMTP_USERNAME\`, \`SMTP_PASSWORD\`, \`SMTP_USE_TLS=true\`, \`SMTP_USE_SSL=false\`.

Existing \`TOKEN_ENCRYPTION_KEY\` remains required for OAuth tokens and must not be replaced with the identity key.

## Abuse controls

- OTP issuance: five requests/hour per identity, 60-second identity cooldown; 100/hour per IP; ten/hour per optional device, 60-second device cooldown.
- Verification: ten/hour per identity, 100/hour per IP and twenty/hour per optional device; separate domain-separated buckets in the existing \`otp_request_limits\` table.
- Each challenge independently allows five failed attempts and one successful consumption.
- Only HMAC digests of identities and abuse dimensions are stored in their lookup/limiter columns. The normalized email ciphertext is stored separately.
- Client IP is accepted only from the configured trusted proxy chain. A raw client-supplied forwarding header is not trusted without the verified proxy topology.

## SES and domain prerequisites

Before enabling delivery:
1. Verify control of the sender domain/subdomain in SES \`sa-east-1\`.
2. Publish the SES-provided DKIM records and configure SPF and DMARC.
3. Move SES out of sandbox and verify production sending limits.
4. Create SMTP credentials for a least-privilege IAM identity; do not use root credentials or paste AWS access keys into the app.
5. Store the SMTP username/password in the Render secret manager; never commit them.
6. Test delivery, bounce/complaint handling, suppression and alerting before public release.

The recommended sender is a dedicated address such as \`nao-responda@auth.<controlled-domain>\`, only after the actual domain is confirmed.

## Legal and operational gates

- Publish and version the terms and privacy notice before setting their version environment variables.
- Explain the purpose of email verification and retain only required delivery/security metadata.
- Review the SES DPA, subprocessors, data location, international transfer mechanism under LGPD and retention terms.
- Confirm the exact Cloudflare → Render proxy chain and test the forwarded IP extraction in a controlled non-production service before setting \`OTP_TRUSTED_PROXY_HOPS\`.
- Add an expiry/cleanup policy for abandoned pending users and stale OTP challenge/limiter rows.
- Add recovery and email-change workflows only after this flow is validated.

## Security boundary

No production secrets, Render environment variables, sender-domain DNS, SES account, production schema, customer identity, or administrator identity were changed by this implementation. Real SMTP delivery is mocked in the PostgreSQL integration tests.
