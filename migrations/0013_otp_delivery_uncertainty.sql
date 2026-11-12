-- Distinguish an SMTP outcome that cannot be confirmed from a definite failure.
-- A dispatching lease is never automatically reclaimed: after DATA may have
-- reached the provider, retrying SMTP could duplicate an OTP message.
ALTER TABLE otp_challenges
    DROP CONSTRAINT IF EXISTS otp_challenges_delivery_status_check;

ALTER TABLE otp_challenges
    ADD CONSTRAINT otp_challenges_delivery_status_check
    CHECK (delivery_status IN ('pending', 'sent', 'failed', 'uncertain'));

ALTER TABLE otp_email_outbox
    DROP CONSTRAINT IF EXISTS otp_email_outbox_status_check;

ALTER TABLE otp_email_outbox
    ADD CONSTRAINT otp_email_outbox_status_check
    CHECK (status IN ('pending', 'processing', 'dispatching', 'sent', 'failed', 'uncertain'));

ALTER TABLE otp_email_outbox
    DROP CONSTRAINT IF EXISTS otp_email_outbox_lease_check;

ALTER TABLE otp_email_outbox
    ADD CONSTRAINT otp_email_outbox_lease_check
    CHECK (
        (status IN ('processing', 'dispatching')
            AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (status NOT IN ('processing', 'dispatching')
            AND lease_token IS NULL AND lease_expires_at IS NULL)
    );

ALTER TABLE otp_email_outbox
    DROP CONSTRAINT IF EXISTS otp_email_outbox_payload_check;

ALTER TABLE otp_email_outbox
    ADD CONSTRAINT otp_email_outbox_payload_check
    CHECK (
        (status IN ('pending', 'processing', 'dispatching') AND payload_ciphertext IS NOT NULL)
        OR status IN ('sent', 'failed', 'uncertain')
    );
