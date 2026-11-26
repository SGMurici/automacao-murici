-- Distinguish acknowledgement of a privacy notice from a granted processing permission.
ALTER TABLE consent_events
    DROP CONSTRAINT IF EXISTS consent_events_decision_check;

ALTER TABLE consent_events
    ADD CONSTRAINT consent_events_decision_check
    CHECK (decision IN ('granted', 'denied', 'revoked', 'acknowledged'));
