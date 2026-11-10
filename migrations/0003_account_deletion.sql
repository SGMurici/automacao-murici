-- Account deletion requests and auditable per-system deletion tracking.
-- This migration only creates the workflow; it does not delete production data.

ALTER TABLE app_users
    DROP CONSTRAINT IF EXISTS app_users_status_check;

ALTER TABLE app_users
    ADD CONSTRAINT app_users_status_check
    CHECK (status IN ('pending', 'active', 'suspended', 'deletion_pending', 'deleted'));

CREATE TABLE IF NOT EXISTS account_deletion_requests (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
    receipt_hash CHAR(64) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'requested'
        CHECK (status IN ('requested', 'processing', 'blocked', 'completed', 'failed')),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    receipt_expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days'),
    failure_code VARCHAR(80),
    CONSTRAINT account_deletion_receipt_expiry
        CHECK (receipt_expires_at > requested_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_account_deletion_one_open_request
    ON account_deletion_requests (user_id)
    WHERE user_id IS NOT NULL
      AND status IN ('requested', 'processing', 'blocked');

CREATE INDEX IF NOT EXISTS idx_account_deletion_requests_status
    ON account_deletion_requests (status, requested_at);

CREATE TABLE IF NOT EXISTS account_deletion_steps (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL
        REFERENCES account_deletion_requests(id) ON DELETE CASCADE,
    system_key VARCHAR(40) NOT NULL
        CHECK (system_key IN (
            'primary_database',
            'connected_providers',
            'app_storage',
            'backups',
            'legal_retention'
        )),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'in_progress', 'completed', 'not_applicable', 'blocked', 'failed'
        )),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    evidence_reference VARCHAR(160),
    failure_code VARCHAR(80),
    UNIQUE (request_id, system_key)
);

CREATE INDEX IF NOT EXISTS idx_account_deletion_steps_request
    ON account_deletion_steps (request_id, status);
