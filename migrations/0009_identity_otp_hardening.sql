-- Harden OTP challenge ownership and delivery metadata.
-- Additive only. Apply to an isolated PostgreSQL branch before any production review.

ALTER TABLE otp_challenges
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES app_users(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS delivery_attempted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS resend_after TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS provider_reference VARCHAR(160);

CREATE INDEX IF NOT EXISTS idx_otp_challenges_user_purpose
    ON otp_challenges (user_id, purpose, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_otp_challenges_active_lookup
    ON otp_challenges (identity_type, identity_lookup_hash, purpose, expires_at)
    WHERE consumed_at IS NULL AND delivery_status IN ('pending', 'sent');

-- Preserve legacy challenge semantics when this additive migration follows 0002.
UPDATE otp_challenges
SET delivery_attempted_at = COALESCE(delivery_attempted_at, created_at),
    sent_at = COALESCE(sent_at, created_at),
    resend_after = COALESCE(resend_after, created_at + INTERVAL '60 seconds')
WHERE delivery_status = 'sent';

UPDATE otp_challenges
SET consumed_at = COALESCE(consumed_at, created_at)
WHERE delivery_status = 'failed' AND consumed_at IS NULL;

ALTER TABLE otp_challenges
    ADD CONSTRAINT otp_challenges_failed_attempts_within_limit
    CHECK (failed_attempts <= max_attempts);

ALTER TABLE otp_challenges
    ADD CONSTRAINT otp_challenges_delivery_timestamps_consistent
    CHECK (
        (delivery_status <> 'sent' OR sent_at IS NOT NULL)
        AND (sent_at IS NULL OR delivery_attempted_at IS NOT NULL)
        AND (provider_reference IS NULL OR delivery_status = 'sent')
    );
