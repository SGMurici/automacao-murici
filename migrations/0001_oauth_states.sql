-- Server-side OAuth state store.
-- Apply in the target environment before deploying code that uses this table.
CREATE TABLE IF NOT EXISTS oauth_states (
    state_hash CHAR(64) PRIMARY KEY,
    provider VARCHAR(20) NOT NULL
        CHECK (provider IN ('google', 'linkedin')),
    browser_session_id VARCHAR(128) NOT NULL,
    account_name VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT oauth_states_expiry_after_creation
        CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_oauth_states_expiry
    ON oauth_states (expires_at);

CREATE INDEX IF NOT EXISTS idx_oauth_states_browser_provider
    ON oauth_states (browser_session_id, provider);
