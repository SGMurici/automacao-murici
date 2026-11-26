CREATE TABLE IF NOT EXISTS linkedin_post_analytics_snapshots (
    id BIGSERIAL PRIMARY KEY,
    queue_id BIGINT NOT NULL REFERENCES linkedin_publish_queue(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_connection_id UUID NOT NULL REFERENCES external_connections(id) ON DELETE RESTRICT,
    metrics JSONB NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_linkedin_analytics_tenant_queue_time
    ON linkedin_post_analytics_snapshots(tenant_id, queue_id, collected_at DESC);
