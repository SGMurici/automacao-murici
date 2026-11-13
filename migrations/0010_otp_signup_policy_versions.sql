-- Preserve the exact policy versions accepted at the time of signup OTP request.
-- The versions are written to consent/audit records only after email verification.
ALTER TABLE otp_challenges
    ADD COLUMN IF NOT EXISTS terms_policy_version VARCHAR(40),
    ADD COLUMN IF NOT EXISTS privacy_notice_version VARCHAR(40);

-- Outstanding legacy signup challenges did not capture the policy versions
-- accepted by the user. Invalidate them rather than inventing historical consent.
UPDATE otp_challenges
SET consumed_at = COALESCE(consumed_at, NOW()),
    terms_policy_version = NULL,
    privacy_notice_version = NULL
WHERE purpose = 'signup'
  AND (
      terms_policy_version IS NULL
      OR length(btrim(terms_policy_version)) NOT BETWEEN 1 AND 40
      OR privacy_notice_version IS NULL
      OR length(btrim(privacy_notice_version)) NOT BETWEEN 1 AND 40
  );

ALTER TABLE otp_challenges
    ADD CONSTRAINT otp_challenges_policy_versions_paired
    CHECK (
        (
            purpose <> 'signup'
            AND terms_policy_version IS NULL
            AND privacy_notice_version IS NULL
        )
        OR (
            purpose = 'signup'
            AND terms_policy_version IS NOT NULL
            AND length(btrim(terms_policy_version)) BETWEEN 1 AND 40
            AND privacy_notice_version IS NOT NULL
            AND length(btrim(privacy_notice_version)) BETWEEN 1 AND 40
        )
        OR (
            purpose = 'signup'
            AND consumed_at IS NOT NULL
            AND terms_policy_version IS NULL
            AND privacy_notice_version IS NULL
        )
    );
