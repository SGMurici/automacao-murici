-- Tenant-bound calendar sync enqueue capability.
-- Requires kappa_event_capability_owner and kappa_event_api_enqueue_executor
-- to be provisioned as NOLOGIN, least-privilege roles before application.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = CURRENT_USER AND (rolsuper OR rolcreaterole)
    ) THEN
        RAISE EXCEPTION 'Migration 0033 requires a controlled migration principal';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'kappa_event_capability_owner'
          AND NOT rolsuper AND NOT rolcanlogin AND NOT rolcreatedb
          AND NOT rolcreaterole AND NOT rolreplication AND NOT rolinherit
          AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'Invalid event capability owner role';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'kappa_event_api_enqueue_executor'
          AND NOT rolsuper AND NOT rolcanlogin AND NOT rolcreatedb
          AND NOT rolcreaterole AND NOT rolreplication AND NOT rolinherit
          AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'Invalid event API enqueue executor role';
    END IF;
END;
$$;

-- The function owner receives only the columns needed by this capability.
GRANT SELECT (id, tenant_id, event_type, payload, idempotency_key, created_at)
ON public.kappa_domain_events TO kappa_event_capability_owner;
GRANT INSERT (tenant_id, event_type, payload, idempotency_key)
ON public.kappa_domain_events TO kappa_event_capability_owner;
GRANT SELECT (id, event_id, consumer_key)
ON public.kappa_event_deliveries TO kappa_event_capability_owner;
GRANT INSERT (event_id, consumer_key, status, attempts, available_at)
ON public.kappa_event_deliveries TO kappa_event_capability_owner;
GRANT USAGE ON SEQUENCE public.kappa_event_deliveries_id_seq
TO kappa_event_capability_owner;
GRANT SELECT (user_id, tenant_id, status, role)
ON public.tenant_memberships TO kappa_event_capability_owner;
GRANT SELECT (id, status, deleted_at)
ON public.app_users TO kappa_event_capability_owner;

CREATE OR REPLACE FUNCTION public.kappa_enqueue_calendar_sync_request(
    p_tenant_id uuid,
    p_change_set_id uuid,
    p_generation integer
)
RETURNS TABLE(event_id uuid, created boolean)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    expected_payload jsonb;
    expected_key text;
    existing_event record;
    delivery_count integer;
    recent_count integer;
    context_user_id uuid;
    actual_actor_role text;
BEGIN
    IF p_tenant_id IS NULL OR p_change_set_id IS NULL
       OR p_generation IS NULL OR p_generation < 1 THEN
        RAISE EXCEPTION 'Invalid calendar sync request';
    END IF;

    -- The HTTP route must authenticate the session and establish this
    -- transaction-local context after checking active tenant membership.
    IF pg_catalog.current_setting('app.tenant_id', true) IS DISTINCT FROM p_tenant_id::text
       OR NULLIF(pg_catalog.current_setting('app.user_id', true), '') IS NULL
       OR NULLIF(pg_catalog.current_setting('app.actor_role', true), '') IS NULL THEN
        RAISE EXCEPTION 'Active tenant context required';
    END IF;

    context_user_id := pg_catalog.current_setting('app.user_id', true)::uuid;
    SELECT m.role::text
      INTO actual_actor_role
      FROM public.tenant_memberships AS m
      JOIN public.app_users AS u ON u.id = m.user_id
     WHERE m.user_id = context_user_id
       AND m.tenant_id = p_tenant_id
       AND m.status = 'active'
       AND u.status = 'active'
       AND u.deleted_at IS NULL;

    IF NOT FOUND OR actual_actor_role IS DISTINCT FROM
       pg_catalog.current_setting('app.actor_role', true) THEN
        RAISE EXCEPTION 'Active tenant membership required';
    END IF;

    expected_key := 'calendar-sync:' || p_change_set_id::text;
    expected_payload := pg_catalog.jsonb_build_object(
        'change_set_id', p_change_set_id::text,
        'generation', p_generation
    );

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(p_tenant_id::text, 0)
    );

    SELECT e.id, e.event_type, e.payload
      INTO existing_event
      FROM public.kappa_domain_events AS e
     WHERE e.tenant_id = p_tenant_id
       AND e.idempotency_key = expected_key;

    IF FOUND THEN
        IF existing_event.event_type <> 'calendar.sync.requested'
           OR existing_event.payload <> expected_payload THEN
            RAISE EXCEPTION 'Idempotency key reused with different event data';
        END IF;

        SELECT pg_catalog.count(*)::integer
          INTO delivery_count
          FROM public.kappa_event_deliveries AS d
         WHERE d.event_id = existing_event.id
           AND d.consumer_key = 'calendar_sync';

        IF delivery_count <> 1 THEN
            RAISE EXCEPTION 'Idempotent event delivery mismatch';
        END IF;

        RETURN QUERY SELECT existing_event.id, false;
        RETURN;
    END IF;

    SELECT pg_catalog.count(*)::integer
      INTO recent_count
      FROM public.kappa_domain_events AS e
     WHERE e.tenant_id = p_tenant_id
       AND e.event_type = 'calendar.sync.requested'
       AND e.created_at >= pg_catalog.now() - interval '5 minutes';

    IF recent_count >= 20 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001',
            MESSAGE = 'calendar_sync_rate_limited';
    END IF;

    INSERT INTO public.kappa_domain_events
        (tenant_id, event_type, payload, idempotency_key)
    VALUES
        (p_tenant_id, 'calendar.sync.requested', expected_payload, expected_key)
    RETURNING id INTO event_id;

    INSERT INTO public.kappa_event_deliveries
        (event_id, consumer_key, status, attempts, available_at)
    VALUES
        (event_id, 'calendar_sync', 'pending', 0, pg_catalog.now());

    created := true;
    RETURN NEXT;
END;
$$;

REVOKE ALL ON FUNCTION public.kappa_enqueue_calendar_sync_request(uuid, uuid, integer)
FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.kappa_enqueue_calendar_sync_request(uuid, uuid, integer)
TO kappa_event_api_enqueue_executor;

DO $$
DECLARE
    is_superuser boolean;
BEGIN
    SELECT rolsuper INTO is_superuser
      FROM pg_catalog.pg_roles WHERE rolname = CURRENT_USER;
    IF NOT is_superuser THEN
        EXECUTE pg_catalog.format(
            'GRANT kappa_event_capability_owner TO %I', CURRENT_USER
        );
        GRANT CREATE ON SCHEMA public TO kappa_event_capability_owner;
    END IF;
    ALTER FUNCTION public.kappa_enqueue_calendar_sync_request(uuid, uuid, integer)
        OWNER TO kappa_event_capability_owner;
    IF NOT is_superuser THEN
        REVOKE CREATE ON SCHEMA public FROM kappa_event_capability_owner;
        EXECUTE pg_catalog.format(
            'REVOKE kappa_event_capability_owner FROM %I', CURRENT_USER
        );
    END IF;
END;
$$;
