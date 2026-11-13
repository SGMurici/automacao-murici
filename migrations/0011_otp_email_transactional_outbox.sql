-- Transactional, encrypted OTP email delivery intent.
CREATE TABLE IF NOT EXISTS otp_email_outbox (
    id BIGSERIAL PRIMARY KEY,
    challenge_id UUID NOT NULL UNIQUE
        REFERENCES otp_challenges(id) ON DELETE CASCADE,
    payload_ciphertext TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    last_error_code VARCHAR(40),
    provider_reference VARCHAR(160),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    CONSTRAINT otp_email_outbox_status_check
        CHECK (status IN ('pending', 'processing', 'sent', 'failed')),
    CONSTRAINT otp_email_outbox_attempts_check
        CHECK (attempts BETWEEN 0 AND 8),
    CONSTRAINT otp_email_outbox_lease_check
        CHECK (
            (status = 'processing' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
            OR
            (status <> 'processing' AND lease_token IS NULL AND lease_expires_at IS NULL)
        ),
    CONSTRAINT otp_email_outbox_sent_check
        CHECK (
            (status = 'sent' AND sent_at IS NOT NULL AND payload_ciphertext IS NULL)
            OR
            (status <> 'sent' AND sent_at IS NULL)
        ),
    CONSTRAINT otp_email_outbox_payload_check
        CHECK (
            (status IN ('pending', 'processing') AND payload_ciphertext IS NOT NULL)
            OR status IN ('sent', 'failed')
        )
);

CREATE INDEX IF NOT EXISTS idx_otp_email_outbox_due
    ON otp_email_outbox (available_at, created_at)
    WHERE status IN ('pending', 'processing');

CREATE INDEX IF NOT EXISTS idx_otp_email_outbox_lease
    ON otp_email_outbox (lease_expires_at)
    WHERE status = 'processing';
