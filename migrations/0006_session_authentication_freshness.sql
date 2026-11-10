-- Preserve the time of the last successful identity authentication.
-- Session rotation must not make an old authentication appear recent.

ALTER TABLE auth_sessions
    ADD COLUMN authenticated_at TIMESTAMPTZ;

UPDATE auth_sessions
SET authenticated_at = created_at
WHERE authenticated_at IS NULL;

ALTER TABLE auth_sessions
    ALTER COLUMN authenticated_at SET DEFAULT NOW();

ALTER TABLE auth_sessions
    ALTER COLUMN authenticated_at SET NOT NULL;
