-- Independent LinkedIn read-only analytics OAuth credentials.
CREATE TABLE IF NOT EXISTS linkedin_analytics_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_connection_id UUID NOT NULL UNIQUE REFERENCES external_connections(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_account_id TEXT NOT NULL,
    account_label TEXT NOT NULL DEFAULT 'Conta LinkedIn',
    granted_scopes TEXT[] NOT NULL DEFAULT '{}',
    access_token_ciphertext BYTEA,
    token_expires_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    CONSTRAINT linkedin_analytics_connection_membership
      FOREIGN KEY (tenant_id, user_id)
      REFERENCES tenant_memberships (tenant_id, user_id) ON DELETE CASCADE,
    CONSTRAINT linkedin_analytics_connection_token_state
      CHECK ((status = 'active' AND access_token_ciphertext IS NOT NULL)
          OR (status = 'revoked' AND access_token_ciphertext IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_linkedin_analytics_connection_owner
  ON linkedin_analytics_connections(tenant_id, user_id, status);

CREATE TABLE IF NOT EXISTS linkedin_analytics_oauth_states (
    state_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT linkedin_analytics_oauth_state_expiry CHECK (expires_at > created_at),
    CONSTRAINT linkedin_analytics_oauth_state_membership
      FOREIGN KEY (tenant_id, user_id)
      REFERENCES tenant_memberships (tenant_id, user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_linkedin_analytics_oauth_state_expiry
  ON linkedin_analytics_oauth_states(expires_at);

CREATE TABLE IF NOT EXISTS linkedin_analytics_oauth_tickets (
    ticket_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    analytics_connection_id UUID NOT NULL REFERENCES linkedin_analytics_connections(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT linkedin_analytics_oauth_ticket_expiry CHECK (expires_at > created_at),
    CONSTRAINT linkedin_analytics_oauth_ticket_membership
      FOREIGN KEY (tenant_id, user_id)
      REFERENCES tenant_memberships (tenant_id, user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_linkedin_analytics_oauth_ticket_expiry
  ON linkedin_analytics_oauth_tickets(expires_at);
