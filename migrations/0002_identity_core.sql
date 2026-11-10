-- Identity, ownership, consent and revocable-session foundation.
-- Apply only to a development/test database before enabling application routes.
-- Existing operational Google/LinkedIn rows are intentionally not auto-assigned to users.

CREATE TABLE IF NOT EXISTS app_users (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'suspended', 'deleted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS user_identities (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    identity_type VARCHAR(10) NOT NULL
        CHECK (identity_type IN ('email', 'phone')),
    identity_lookup_hash BYTEA NOT NULL,
    identity_value_ciphertext BYTEA NOT NULL,
    verified_at TIMESTAMPTZ,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (identity_type, identity_lookup_hash),
    UNIQUE (user_id, identity_type, identity_lookup_hash)
);

CREATE INDEX IF NOT EXISTS idx_user_identities_user
    ON user_identities (user_id, identity_type);

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_identities_single_primary
    ON user_identities (user_id, identity_type)
    WHERE is_primary = TRUE;

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY,
    tenant_type VARCHAR(20) NOT NULL DEFAULT 'personal'
        CHECK (tenant_type IN ('personal', 'shared')),
    display_name VARCHAR(160),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_memberships (
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'member'
        CHECK (role IN ('owner', 'admin', 'member')),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('invited', 'active', 'suspended', 'removed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_memberships_user
    ON tenant_memberships (user_id, status);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    replaced_by_token_hash CHAR(64),
    device_label VARCHAR(120),
    CONSTRAINT auth_sessions_expiry_after_creation
        CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_active
    ON auth_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS otp_challenges (
    id UUID PRIMARY KEY,
    identity_type VARCHAR(10) NOT NULL
        CHECK (identity_type IN ('email', 'phone')),
    identity_lookup_hash BYTEA NOT NULL,
    purpose VARCHAR(24) NOT NULL
        CHECK (purpose IN ('signup', 'login', 'verify_identity', 'recovery')),
    code_hash BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    failed_attempts SMALLINT NOT NULL DEFAULT 0
        CHECK (failed_attempts >= 0),
    max_attempts SMALLINT NOT NULL DEFAULT 5
        CHECK (max_attempts BETWEEN 1 AND 10),
    delivery_status VARCHAR(12) NOT NULL DEFAULT 'pending'
        CHECK (delivery_status IN ('pending', 'sent', 'failed')),
    CONSTRAINT otp_challenges_expiry_after_creation
        CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_otp_challenges_lookup
    ON otp_challenges (identity_type, identity_lookup_hash, purpose, created_at DESC);

CREATE TABLE IF NOT EXISTS consent_events (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    purpose VARCHAR(80) NOT NULL,
    policy_version VARCHAR(40) NOT NULL,
    decision VARCHAR(12) NOT NULL
        CHECK (decision IN ('granted', 'denied', 'revoked')),
    source VARCHAR(30) NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_consent_events_user_purpose
    ON consent_events (user_id, purpose, decided_at DESC);

CREATE TABLE IF NOT EXISTS external_connections (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(30) NOT NULL,
    external_account_id VARCHAR(255) NOT NULL,
    account_label VARCHAR(160),
    granted_scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    access_token_ciphertext BYTEA,
    refresh_token_ciphertext BYTEA,
    token_expires_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'revoked', 'reauthorization_required')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    UNIQUE (tenant_id, provider, external_account_id),
    CONSTRAINT external_connections_owner_membership
        FOREIGN KEY (tenant_id, user_id)
        REFERENCES tenant_memberships (tenant_id, user_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_external_connections_owner
    ON external_connections (user_id, tenant_id, provider, status);

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY,
    actor_user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    action VARCHAR(80) NOT NULL,
    resource_type VARCHAR(80),
    resource_id VARCHAR(160),
    result VARCHAR(20) NOT NULL
        CHECK (result IN ('success', 'denied', 'failure')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audit_events_tenant_time
    ON audit_events (tenant_id, occurred_at DESC);
