-- Microsoft OAuth state and completion tickets are isolated from Gmail.
-- Only hashes of state/tickets are stored; PKCE verifier is encrypted by the application.
CREATE TABLE IF NOT EXISTS client_microsoft_oauth_states (
    state_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    pkce_verifier_ciphertext BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT client_microsoft_oauth_state_expiry CHECK (expires_at > created_at),
    CONSTRAINT client_microsoft_oauth_state_membership
      FOREIGN KEY (tenant_id, user_id)
      REFERENCES tenant_memberships (tenant_id, user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_client_microsoft_oauth_state_expiry
  ON client_microsoft_oauth_states (expires_at);

CREATE TABLE IF NOT EXISTS client_microsoft_oauth_tickets (
    ticket_hash CHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_connection_id UUID NOT NULL REFERENCES external_connections(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT client_microsoft_oauth_ticket_expiry CHECK (expires_at > created_at),
    CONSTRAINT client_microsoft_oauth_ticket_membership
      FOREIGN KEY (tenant_id, user_id)
      REFERENCES tenant_memberships (tenant_id, user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_client_microsoft_oauth_ticket_expiry
  ON client_microsoft_oauth_tickets (expires_at);
CREATE INDEX IF NOT EXISTS idx_client_microsoft_oauth_ticket_connection
  ON client_microsoft_oauth_tickets (external_connection_id);
