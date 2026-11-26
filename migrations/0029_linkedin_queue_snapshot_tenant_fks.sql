-- Ensure LinkedIn queue connections and analytics snapshots remain in one tenant.
-- Historical queue rows with tenant_id NULL remain legacy/unscoped and are not
-- eligible for tenant APIs. Snapshot rows must pass both ownership constraints.

CREATE UNIQUE INDEX IF NOT EXISTS uq_external_connections_id_tenant
    ON external_connections (id, tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_linkedin_publish_queue_id_tenant
    ON linkedin_publish_queue (id, tenant_id);

ALTER TABLE linkedin_publish_queue
    DROP CONSTRAINT IF EXISTS linkedin_publish_queue_external_connection_id_fkey;

ALTER TABLE linkedin_publish_queue
    ADD CONSTRAINT linkedin_publish_queue_connection_tenant_fkey
    FOREIGN KEY (external_connection_id, tenant_id)
    REFERENCES external_connections (id, tenant_id)
    ON DELETE SET NULL (external_connection_id) NOT VALID;

ALTER TABLE linkedin_publish_queue
    VALIDATE CONSTRAINT linkedin_publish_queue_connection_tenant_fkey;

ALTER TABLE linkedin_post_analytics_snapshots
    DROP CONSTRAINT IF EXISTS linkedin_post_analytics_snapshots_queue_id_fkey;

ALTER TABLE linkedin_post_analytics_snapshots
    ADD CONSTRAINT linkedin_analytics_snapshot_queue_tenant_fkey
    FOREIGN KEY (queue_id, tenant_id)
    REFERENCES linkedin_publish_queue (id, tenant_id)
    ON DELETE CASCADE NOT VALID;

ALTER TABLE linkedin_post_analytics_snapshots
    VALIDATE CONSTRAINT linkedin_analytics_snapshot_queue_tenant_fkey;

ALTER TABLE linkedin_post_analytics_snapshots
    DROP CONSTRAINT IF EXISTS linkedin_post_analytics_snapshots_external_connection_id_fkey;

ALTER TABLE linkedin_post_analytics_snapshots
    ADD CONSTRAINT linkedin_analytics_snapshot_connection_tenant_fkey
    FOREIGN KEY (external_connection_id, tenant_id)
    REFERENCES external_connections (id, tenant_id)
    ON DELETE RESTRICT NOT VALID;

ALTER TABLE linkedin_post_analytics_snapshots
    VALIDATE CONSTRAINT linkedin_analytics_snapshot_connection_tenant_fkey;
