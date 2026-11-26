-- Bind OAuth completion tickets to the exact connection, owner, tenant and provider.
-- Preflight existing non-null connection references before validating these constraints.

CREATE UNIQUE INDEX IF NOT EXISTS uq_external_connections_id_tenant_user_provider_purpose
    ON external_connections (id, tenant_id, user_id, provider, connection_purpose);

ALTER TABLE client_google_oauth_tickets
    ADD COLUMN IF NOT EXISTS external_provider VARCHAR(30) NOT NULL DEFAULT 'google_gmail';

ALTER TABLE client_google_oauth_tickets
    ADD CONSTRAINT client_google_oauth_ticket_provider_check
    CHECK (external_provider = 'google_gmail');

ALTER TABLE client_google_oauth_tickets
    DROP CONSTRAINT IF EXISTS client_google_oauth_tickets_external_connection_id_fkey;

ALTER TABLE client_google_oauth_tickets
    ADD CONSTRAINT client_google_oauth_ticket_connection_owner_provider_purpose_fkey
    FOREIGN KEY (external_connection_id, tenant_id, user_id, external_provider, purpose)
    REFERENCES external_connections (id, tenant_id, user_id, provider, connection_purpose)
    ON DELETE CASCADE NOT VALID;

ALTER TABLE client_google_oauth_tickets
    VALIDATE CONSTRAINT client_google_oauth_ticket_connection_owner_provider_purpose_fkey;

ALTER TABLE client_microsoft_oauth_tickets
    ADD COLUMN IF NOT EXISTS external_provider VARCHAR(30) NOT NULL DEFAULT 'microsoft_outlook';

ALTER TABLE client_microsoft_oauth_tickets
    ADD CONSTRAINT client_microsoft_oauth_ticket_provider_check
    CHECK (external_provider = 'microsoft_outlook');

ALTER TABLE client_microsoft_oauth_tickets
    DROP CONSTRAINT IF EXISTS client_microsoft_oauth_tickets_external_connection_id_fkey;

ALTER TABLE client_microsoft_oauth_tickets
    ADD CONSTRAINT client_microsoft_oauth_ticket_connection_owner_provider_fkey
    FOREIGN KEY (external_connection_id, tenant_id, user_id, external_provider)
    REFERENCES external_connections (id, tenant_id, user_id, provider)
    ON DELETE CASCADE NOT VALID;

ALTER TABLE client_microsoft_oauth_tickets
    VALIDATE CONSTRAINT client_microsoft_oauth_ticket_connection_owner_provider_fkey;

ALTER TABLE client_linkedin_oauth_tickets
    ADD COLUMN IF NOT EXISTS external_provider VARCHAR(30) NOT NULL DEFAULT 'linkedin';

ALTER TABLE client_linkedin_oauth_tickets
    ADD CONSTRAINT client_linkedin_oauth_ticket_provider_check
    CHECK (external_provider = 'linkedin');

ALTER TABLE client_linkedin_oauth_tickets
    DROP CONSTRAINT IF EXISTS client_linkedin_oauth_tickets_external_connection_id_fkey;

ALTER TABLE client_linkedin_oauth_tickets
    ADD CONSTRAINT client_linkedin_oauth_ticket_connection_owner_provider_fkey
    FOREIGN KEY (external_connection_id, tenant_id, user_id, external_provider)
    REFERENCES external_connections (id, tenant_id, user_id, provider)
    ON DELETE CASCADE NOT VALID;

ALTER TABLE client_linkedin_oauth_tickets
    VALIDATE CONSTRAINT client_linkedin_oauth_ticket_connection_owner_provider_fkey;
