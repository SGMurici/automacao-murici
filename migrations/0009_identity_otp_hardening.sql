-- Harden email OTP challenges and add shared, privacy-preserving rate-limit buckets.
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

CREATE TABLE IF NOT EXISTS auth_rate_limit_buckets (
    scope VARCHAR(24) NOT NULL
        CHECK (scope IN ('otp_identity', 'otp_ip')),
    key_hash BYTEA NOT NULL,
    window_started_at TIMESTAMPTZ NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0
        CHECK (hit_count >= 0),
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (scope, key_hash, window_started_at),
    CONSTRAINT auth_rate_limit_expiry_after_window
        CHECK (expires_at > window_started_at)
);

CREATE INDEX IF NOT EXISTS idx_auth_rate_limit_expiry
    ON auth_rate_limit_buckets (expires_at);

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
