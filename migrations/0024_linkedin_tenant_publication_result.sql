-- Tenant-scoped publication result and connection provenance.
ALTER TABLE linkedin_publish_queue
    ADD COLUMN IF NOT EXISTS external_connection_id UUID REFERENCES external_connections(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS linkedin_post_url TEXT;

CREATE INDEX IF NOT EXISTS idx_linkedin_publish_queue_tenant_due
    ON linkedin_publish_queue(tenant_id, status, scheduled_for)
    WHERE tenant_id IS NOT NULL;
