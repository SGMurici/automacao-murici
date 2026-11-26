-- Provision the operational scheduler and LinkedIn analytics schema outside request paths.
-- Requires the existing editorial_posts table.
-- Existing legacy columns are preserved and only missing structures are added.

CREATE TABLE IF NOT EXISTS linkedin_post_metrics (
    id BIGSERIAL PRIMARY KEY,
    editorial_post_id BIGINT REFERENCES editorial_posts(id) ON DELETE SET NULL,
    linkedin_post_id TEXT NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    impressions BIGINT,
    members_reached BIGINT,
    reactions BIGINT,
    comments BIGINT,
    reposts BIGINT,
    post_saves BIGINT,
    post_sends BIGINT,
    link_clicks BIGINT,
    premium_cta_clicks BIGINT,
    followers_gained_from_content BIGINT,
    profile_views_from_content BIGINT,
    engagement_total BIGINT,
    source VARCHAR(50) NOT NULL DEFAULT 'linkedin_api',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT linkedin_post_metrics_unique_snapshot
        UNIQUE (linkedin_post_id, measured_at)
);

CREATE INDEX IF NOT EXISTS idx_linkedin_post_metrics_post
    ON linkedin_post_metrics(linkedin_post_id);
CREATE INDEX IF NOT EXISTS idx_linkedin_post_metrics_editorial
    ON linkedin_post_metrics(editorial_post_id);
CREATE INDEX IF NOT EXISTS idx_linkedin_post_metrics_measured_at
    ON linkedin_post_metrics(measured_at);

CREATE TABLE IF NOT EXISTS linkedin_metrics_collection_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(30) NOT NULL DEFAULT 'started',
    posts_found INTEGER DEFAULT 0,
    posts_updated INTEGER DEFAULT 0,
    metrics_saved INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_linkedin_metrics_runs_started
    ON linkedin_metrics_collection_runs(started_at);

CREATE TABLE IF NOT EXISTS linkedin_publish_queue (
    id BIGSERIAL PRIMARY KEY,
    post_number INTEGER,
    title TEXT,
    content TEXT NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'agendado',
    attempts INTEGER NOT NULL DEFAULT 0,
    locked_at TIMESTAMPTZ,
    reconciliation_required_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    linkedin_post_id TEXT,
    editorial_post_id BIGINT REFERENCES editorial_posts(id) ON DELETE SET NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE linkedin_publish_queue
    ADD COLUMN IF NOT EXISTS reconciliation_required_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_linkedin_publish_queue_due
    ON linkedin_publish_queue(status, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_linkedin_publish_queue_post_number
    ON linkedin_publish_queue(post_number);
CREATE INDEX IF NOT EXISTS idx_linkedin_publish_queue_linkedin_post
    ON linkedin_publish_queue(linkedin_post_id);
CREATE INDEX IF NOT EXISTS idx_linkedin_publish_queue_expired_processing
    ON linkedin_publish_queue(locked_at)
    WHERE status = 'processando' AND locked_at IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_linkedin_publish_queue_reserved_post_number
    ON linkedin_publish_queue(post_number)
    WHERE post_number IS NOT NULL
      AND status IN ('agendado', 'processando', 'publicado', 'incerto');
