-- Global platform administrators are distinct from tenant owner/admin roles.
-- Bootstrap is deliberately out-of-band: never allow public self-promotion.
CREATE TABLE IF NOT EXISTS global_administrators (
    user_id UUID PRIMARY KEY
        REFERENCES app_users(id) ON DELETE RESTRICT,
    status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'revoked')),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    granted_by UUID REFERENCES app_users(id) ON DELETE SET NULL,
    grant_reason VARCHAR(240) NOT NULL
        CHECK (length(btrim(grant_reason)) BETWEEN 1 AND 240),
    revoked_at TIMESTAMPTZ,
    CONSTRAINT global_administrators_revocation_consistency
        CHECK (
            (status = 'revoked' AND revoked_at IS NOT NULL)
            OR
            (status IN ('active', 'suspended') AND revoked_at IS NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_global_administrators_active
    ON global_administrators (user_id)
    WHERE status = 'active' AND revoked_at IS NULL;

COMMENT ON TABLE global_administrators IS
    'Platform-wide administrators are separate from tenant_memberships roles. Bootstrap only through a controlled operator procedure.';
