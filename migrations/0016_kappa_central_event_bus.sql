-- Central KAPPA event ledger with isolated delivery state per consumer.
-- Apply only through the separately authorized migration process.
CREATE TABLE IF NOT EXISTS kappa_domain_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT kappa_domain_events_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT kappa_domain_events_idempotency_unique UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_kappa_domain_events_tenant_time
    ON kappa_domain_events (tenant_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS kappa_event_deliveries (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL REFERENCES kappa_domain_events(id) ON DELETE CASCADE,
    consumer_key VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    last_error_code VARCHAR(60),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ,
    CONSTRAINT kappa_event_deliveries_consumer_unique UNIQUE (event_id, consumer_key),
    CONSTRAINT kappa_event_deliveries_consumer_check CHECK (consumer_key IN (
        'push_notifications', 'calendar_sync', 'gmail_integrations',
        'analytics', 'lyla_assistant'
    )),
    CONSTRAINT kappa_event_deliveries_status_check
        CHECK (status IN ('pending', 'processing', 'delivered', 'dead_letter')),
    CONSTRAINT kappa_event_deliveries_attempts_check CHECK (attempts BETWEEN 0 AND 8),
    CONSTRAINT kappa_event_deliveries_lease_check CHECK (
        (status = 'processing' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (status <> 'processing' AND lease_token IS NULL AND lease_expires_at IS NULL)
    ),
    CONSTRAINT kappa_event_deliveries_delivered_check CHECK (
        (status = 'delivered' AND delivered_at IS NOT NULL)
        OR (status <> 'delivered' AND delivered_at IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_kappa_event_deliveries_due
    ON kappa_event_deliveries (consumer_key, available_at, created_at)
    WHERE status IN ('pending', 'processing');
CREATE INDEX IF NOT EXISTS idx_kappa_event_deliveries_lease
    ON kappa_event_deliveries (lease_expires_at)
    WHERE status = 'processing';
CREATE INDEX IF NOT EXISTS idx_kappa_event_deliveries_backlog
    ON kappa_event_deliveries (consumer_key, status, created_at);
