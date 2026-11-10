-- Add an explicit reconciliation timestamp for abandoned LinkedIn publications.
-- Expired processing rows are uncertain: never retry them automatically.
ALTER TABLE linkedin_publish_queue
    ADD COLUMN IF NOT EXISTS reconciliation_required_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_linkedin_publish_queue_expired_processing
    ON linkedin_publish_queue (locked_at)
    WHERE status = 'processando' AND locked_at IS NOT NULL;
