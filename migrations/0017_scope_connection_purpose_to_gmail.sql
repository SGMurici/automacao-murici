-- Scope Gmail authorization purpose to Gmail connections only.
-- Preserve the original per-provider uniqueness for every other integration.
ALTER TABLE external_connections
    ALTER COLUMN connection_purpose DROP DEFAULT,
    ALTER COLUMN connection_purpose DROP NOT NULL;

UPDATE external_connections
SET connection_purpose = NULL
WHERE provider <> 'google_gmail';

ALTER TABLE external_connections
    ADD CONSTRAINT external_connections_connection_purpose_scope
    CHECK (
        (provider = 'google_gmail'
            AND connection_purpose IS NOT NULL
            AND connection_purpose IN ('gmail_read', 'gmail_send'))
        OR
        (provider <> 'google_gmail' AND connection_purpose IS NULL)
    );

DROP INDEX IF EXISTS uq_external_connections_gmail_purpose;

CREATE UNIQUE INDEX uq_external_connections_gmail_purpose
    ON external_connections (tenant_id, provider, external_account_id, connection_purpose)
    WHERE provider = 'google_gmail';

CREATE UNIQUE INDEX uq_external_connections_non_gmail
    ON external_connections (tenant_id, provider, external_account_id)
    WHERE provider <> 'google_gmail';
