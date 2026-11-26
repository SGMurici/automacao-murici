-- Bind each one-time App Link ticket to the exact Gmail connection created by its OAuth callback.
-- Prevent concurrent account authorizations from finishing against the wrong mailbox.
ALTER TABLE client_google_oauth_tickets
    ADD COLUMN IF NOT EXISTS external_connection_id UUID
    REFERENCES external_connections(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_client_google_oauth_ticket_connection
    ON client_google_oauth_tickets (external_connection_id)
    WHERE external_connection_id IS NOT NULL;
