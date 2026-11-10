-- Atomic OTP resend throttling by pseudonymous identity, IP or device dimensions.
-- Stores only keyed dimension hashes, never raw email, phone, IP or device identifiers.

CREATE TABLE IF NOT EXISTS otp_request_limits (
    dimension_type VARCHAR(12) NOT NULL
        CHECK (dimension_type IN ('identity', 'ip', 'device')),
    dimension_hash BYTEA NOT NULL
        CHECK (octet_length(dimension_hash) = 32),
    purpose VARCHAR(24) NOT NULL
        CHECK (purpose IN ('signup', 'login', 'verify_identity', 'recovery')),
    window_started_at TIMESTAMPTZ NOT NULL,
    request_count SMALLINT NOT NULL
        CHECK (request_count >= 1 AND request_count <= 1000),
    last_requested_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (dimension_type, dimension_hash, purpose)
);

CREATE INDEX IF NOT EXISTS idx_otp_request_limits_last_requested
    ON otp_request_limits (last_requested_at);
