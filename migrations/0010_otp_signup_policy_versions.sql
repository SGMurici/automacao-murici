-- Preserve the exact policy versions accepted at the time of signup OTP request.
-- The versions are written to consent/audit records only after email verification.
ALTER TABLE otp_challenges
    ADD COLUMN IF NOT EXISTS terms_policy_version VARCHAR(40),
    ADD COLUMN IF NOT EXISTS privacy_notice_version VARCHAR(40);

ALTER TABLE otp_challenges
    ADD CONSTRAINT otp_challenges_policy_versions_paired
    CHECK (
        (terms_policy_version IS NULL AND privacy_notice_version IS NULL)
        OR
        (terms_policy_version IS NOT NULL AND privacy_notice_version IS NOT NULL)
    );
