-- Store the exact legal document versions accepted when a signup OTP is requested.
-- This binds the consent evidence to the challenge and avoids trusting client-supplied versions.

ALTER TABLE otp_challenges
    ADD COLUMN IF NOT EXISTS terms_policy_version VARCHAR(40),
    ADD COLUMN IF NOT EXISTS privacy_notice_version VARCHAR(40);

ALTER TABLE otp_challenges
    ADD CONSTRAINT otp_challenges_signup_policy_versions_consistent
    CHECK (
        (terms_policy_version IS NULL AND privacy_notice_version IS NULL)
        OR (
            purpose = 'signup'
            AND terms_policy_version IS NOT NULL
            AND length(btrim(terms_policy_version)) BETWEEN 1 AND 40
            AND privacy_notice_version IS NOT NULL
            AND length(btrim(privacy_notice_version)) BETWEEN 1 AND 40
        )
    );
