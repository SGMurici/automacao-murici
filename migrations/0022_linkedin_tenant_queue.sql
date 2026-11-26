-- Tenant-scoped client publishing queue.
-- Existing legacy rows remain tenant_id NULL and are not exposed to client APIs.
ALTER TABLE linkedin_publish_queue
    ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS client_post_id UUID,
    ADD COLUMN IF NOT EXISTS content_hash CHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_linkedin_publish_queue_tenant_client_post
    ON linkedin_publish_queue (tenant_id, client_post_id)
    WHERE tenant_id IS NOT NULL AND client_post_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_linkedin_publish_queue_tenant_status_schedule
    ON linkedin_publish_queue (tenant_id, status, scheduled_for)
    WHERE tenant_id IS NOT NULL;
-- The previous post_number uniqueness was global; scope new client records by tenant.
DROP INDEX IF EXISTS uq_linkedin_publish_queue_reserved_post_number;

CREATE UNIQUE INDEX IF NOT EXISTS uq_linkedin_publish_queue_tenant_reserved_post_number
    ON linkedin_publish_queue (tenant_id, post_number)
    WHERE tenant_id IS NOT NULL
      AND post_number IS NOT NULL
      AND status IN ('aguardando_conexao', 'agendado', 'processando', 'publicado', 'incerto');

-- Preserve collision protection for historical, unscoped queue rows.
CREATE UNIQUE INDEX IF NOT EXISTS uq_linkedin_publish_queue_legacy_reserved_post_number
    ON linkedin_publish_queue (post_number)
    WHERE tenant_id IS NULL
      AND post_number IS NOT NULL
      AND status IN ('agendado', 'processando', 'publicado', 'incerto');
