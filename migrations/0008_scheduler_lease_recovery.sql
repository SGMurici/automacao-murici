-- Add an explicit reconciliation timestamp for abandoned LinkedIn publications.
-- Expired processing rows are uncertain: never retry them automatically.
ALTER TABLE linkedin_publish_queue
    ADD COLUMN IF NOT EXISTS reconciliation_required_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_linkedin_publish_queue_expired_processing
    ON linkedin_publish_queue (locked_at)
    WHERE status = 'processando' AND locked_at IS NOT NULL;

-- Uncertain posts must continue reserving their editorial number.
-- Rebuild the partial unique index with the new non-retryable state included.
DROP INDEX IF EXISTS uq_linkedin_publish_queue_active_post_number;

CREATE UNIQUE INDEX uq_linkedin_publish_queue_active_post_number
    ON linkedin_publish_queue(post_number)
    WHERE post_number IS NOT NULL
      AND status IN ('agendado', 'processando', 'publicado', 'incerto');
