-- Enforce tenant/user consistency for LinkedIn analytics OAuth references.
-- Preflight the existing rows before applying this migration to any shared database.
-- The provider discriminator is fixed to LinkedIn so the FK also verifies provider ownership.

CREATE UNIQUE INDEX IF NOT EXISTS uq_external_connections_id_tenant_user_provider
    ON external_connections (id, tenant_id, user_id, provider);

ALTER TABLE linkedin_analytics_connections
    ADD COLUMN IF NOT EXISTS external_provider VARCHAR(30) NOT NULL DEFAULT 'linkedin';

ALTER TABLE linkedin_analytics_connections
    ADD CONSTRAINT linkedin_analytics_external_provider_check
    CHECK (external_provider = 'linkedin');

CREATE UNIQUE INDEX IF NOT EXISTS uq_linkedin_analytics_connections_id_tenant_user
    ON linkedin_analytics_connections (id, tenant_id, user_id);

ALTER TABLE linkedin_analytics_connections
    DROP CONSTRAINT IF EXISTS linkedin_analytics_connections_external_connection_id_fkey;

ALTER TABLE linkedin_analytics_connections
    ADD CONSTRAINT linkedin_analytics_external_connection_owner_provider_fkey
    FOREIGN KEY (external_connection_id, tenant_id, user_id, external_provider)
    REFERENCES external_connections (id, tenant_id, user_id, provider)
    ON DELETE CASCADE NOT VALID;

ALTER TABLE linkedin_analytics_connections
    VALIDATE CONSTRAINT linkedin_analytics_external_connection_owner_provider_fkey;

ALTER TABLE linkedin_analytics_oauth_tickets
    DROP CONSTRAINT IF EXISTS linkedin_analytics_oauth_tickets_analytics_connection_id_fkey;

ALTER TABLE linkedin_analytics_oauth_tickets
    ADD CONSTRAINT linkedin_analytics_ticket_connection_owner_fkey
    FOREIGN KEY (analytics_connection_id, tenant_id, user_id)
    REFERENCES linkedin_analytics_connections (id, tenant_id, user_id)
    ON DELETE CASCADE NOT VALID;

ALTER TABLE linkedin_analytics_oauth_tickets
    VALIDATE CONSTRAINT linkedin_analytics_ticket_connection_owner_fkey;
