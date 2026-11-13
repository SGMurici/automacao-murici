-- Bind customer Drive backup OAuth flows to a single active user/tenant.
-- Legacy operational OAuth rows remain purpose='legacy' and unassigned.
ALTER TABLE oauth_states
    ALTER COLUMN browser_session_id DROP NOT NULL;

ALTER TABLE oauth_states
    ADD COLUMN IF NOT EXISTS purpose VARCHAR(24) NOT NULL DEFAULT 'legacy',
    ADD COLUMN IF NOT EXISTS user_id UUID,
    ADD COLUMN IF NOT EXISTS tenant_id UUID,
    ADD COLUMN IF NOT EXISTS code_verifier_ciphertext BYTEA,
    ADD COLUMN IF NOT EXISTS redirect_uri VARCHAR(512);

ALTER TABLE oauth_states
    ADD CONSTRAINT oauth_states_purpose_check
        CHECK (purpose IN ('legacy', 'drive_backup'));

ALTER TABLE oauth_states
    ADD CONSTRAINT oauth_states_customer_context_check
        CHECK (
            (purpose = 'legacy'
             AND user_id IS NULL
             AND tenant_id IS NULL
             AND code_verifier_ciphertext IS NULL
             AND redirect_uri IS NULL)
            OR
            (purpose = 'drive_backup'
             AND user_id IS NOT NULL
             AND tenant_id IS NOT NULL
             AND code_verifier_ciphertext IS NOT NULL
             AND redirect_uri IS NOT NULL)
        );

ALTER TABLE oauth_states
    ADD CONSTRAINT oauth_states_customer_membership_fk
        FOREIGN KEY (tenant_id, user_id)
        REFERENCES tenant_memberships (tenant_id, user_id)
        ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_oauth_states_customer_flow
    ON oauth_states (user_id, tenant_id, expires_at)
    WHERE purpose = 'drive_backup';
