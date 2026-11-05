-- Test-branch migration only. Do not apply to production without separate approval.
-- Adds an explicit terminal state for permanent Drive deletion while preserving
-- the editorial row and all LinkedIn publication metadata.
BEGIN;

ALTER TABLE public.project_assets
    DROP CONSTRAINT IF EXISTS project_assets_status_check;

ALTER TABLE public.project_assets
    ADD CONSTRAINT project_assets_status_check
    CHECK (
        asset_status IN (
            'pending',
            'stored',
            'duplicate',
            'review',
            'error',
            'deleted'
        )
    );

ALTER TABLE public.project_assets
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

COMMIT;
