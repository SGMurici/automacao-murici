-- Narrow SECURITY DEFINER capabilities for the KAPPA event worker.
-- Prerequisite: provision isolated NOLOGIN roles as described in docs/74.
-- This migration is local-only until role ownership and grants are proven in a
-- disposable database with real PostgreSQL roles.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = CURRENT_USER AND (rolsuper OR rolcreaterole)
    ) THEN
        RAISE EXCEPTION 'Migration 0031 requires a superuser or a CREATEROLE migration principal with controlled membership on the capability owner';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_recover_exhausted_event_leases(p_consumer text)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    affected integer;
BEGIN
    IF p_consumer IS NULL OR p_consumer NOT IN (
        'push_notifications', 'calendar_sync', 'gmail_integrations',
        'analytics', 'lyla_assistant'
    ) THEN
        RAISE EXCEPTION 'Unknown event consumer';
    END IF;

    UPDATE public.kappa_event_deliveries
       SET status = 'dead_letter',
           lease_token = NULL,
           lease_expires_at = NULL,
           last_error_code = 'lease_expired_exhausted',
           updated_at = pg_catalog.now()
     WHERE consumer_key = p_consumer
       AND status = 'processing'
       AND lease_expires_at <= pg_catalog.now()
       AND attempts >= 8;
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_claim_event_delivery(
    p_consumer text,
    p_limit integer DEFAULT 1
)
RETURNS TABLE(
    delivery_id bigint,
    event_id uuid,
    lease_token uuid,
    attempts integer,
    consumer_key varchar(40),
    tenant_id uuid,
    event_type varchar(100),
    payload jsonb
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_consumer IS NULL OR p_consumer NOT IN (
        'push_notifications', 'calendar_sync', 'gmail_integrations',
        'analytics', 'lyla_assistant'
    ) THEN
        RAISE EXCEPTION 'Unknown event consumer';
    END IF;
    -- Until lease renewal or parallel per-job execution exists, a single
    -- claim per worker invocation prevents later serial jobs expiring in queue.
    IF p_limit IS DISTINCT FROM 1 THEN
        RAISE EXCEPTION 'Event worker claim limit must be exactly one';
    END IF;

    RETURN QUERY
    WITH due AS (
        SELECT d.id
          FROM public.kappa_event_deliveries AS d
         WHERE d.consumer_key = p_consumer
           AND d.attempts < 8
           AND (
                (d.status = 'pending' AND d.available_at <= pg_catalog.now())
                OR
                (d.status = 'processing' AND d.lease_expires_at <= pg_catalog.now())
           )
         ORDER BY d.available_at, d.created_at
         FOR UPDATE OF d SKIP LOCKED
         LIMIT 1
    )
    UPDATE public.kappa_event_deliveries AS d
       SET status = 'processing',
           attempts = d.attempts + 1,
           lease_token = pg_catalog.gen_random_uuid(),
           lease_expires_at = pg_catalog.now() + INTERVAL '120 seconds',
           updated_at = pg_catalog.now()
      FROM due, public.kappa_domain_events AS e
     WHERE d.id = due.id
       AND e.id = d.event_id
    RETURNING d.id, d.event_id, d.lease_token, d.attempts,
              d.consumer_key, e.tenant_id, e.event_type, e.payload;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_ack_event_delivery(
    p_delivery_id bigint,
    p_lease_token uuid
)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    affected integer;
BEGIN
    IF p_delivery_id IS NULL OR p_delivery_id < 1 OR p_lease_token IS NULL THEN
        RETURN false;
    END IF;

    UPDATE public.kappa_event_deliveries
       SET status = 'delivered',
           delivered_at = pg_catalog.now(),
           lease_token = NULL,
           lease_expires_at = NULL,
           last_error_code = NULL,
           updated_at = pg_catalog.now()
     WHERE id = p_delivery_id
       AND status = 'processing'
       AND lease_token = p_lease_token
       AND lease_expires_at > pg_catalog.now();
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected = 1;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_retry_event_delivery(
    p_delivery_id bigint,
    p_lease_token uuid,
    p_attempts integer,
    p_error_code text DEFAULT 'consumer_error'
)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    affected integer;
    terminal boolean;
    retry_delay integer;
BEGIN
    IF p_delivery_id IS NULL OR p_delivery_id < 1 OR p_lease_token IS NULL
       OR p_attempts IS NULL OR p_attempts < 1 OR p_attempts > 8 THEN
        RETURN false;
    END IF;
    IF p_error_code IS NULL OR p_error_code !~ '^[a-z0-9_]{1,60}$' THEN
        RAISE EXCEPTION 'Invalid event error code';
    END IF;

    terminal := p_attempts >= 8;
    retry_delay := LEAST(3600, 5 * (2 ^ LEAST(p_attempts - 1, 10)));

    UPDATE public.kappa_event_deliveries
       SET status = CASE WHEN terminal THEN 'dead_letter' ELSE 'pending' END,
           available_at = CASE WHEN terminal THEN available_at
               ELSE pg_catalog.now() + (retry_delay * INTERVAL '1 second') END,
           lease_token = NULL,
           lease_expires_at = NULL,
           last_error_code = p_error_code,
           updated_at = pg_catalog.now()
     WHERE id = p_delivery_id
       AND status = 'processing'
       AND lease_token = p_lease_token
       AND lease_expires_at > pg_catalog.now()
       AND attempts = p_attempts;
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected = 1;
END;
$$;

REVOKE ALL ON FUNCTION public.kappa_recover_exhausted_event_leases(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_claim_event_delivery(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_ack_event_delivery(bigint, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_retry_event_delivery(bigint, uuid, integer, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.kappa_recover_exhausted_event_leases(text)
    TO kappa_event_worker_executor;
GRANT EXECUTE ON FUNCTION public.kappa_claim_event_delivery(text, integer)
    TO kappa_event_worker_executor;
GRANT EXECUTE ON FUNCTION public.kappa_ack_event_delivery(bigint, uuid)
    TO kappa_event_worker_executor;
GRANT EXECUTE ON FUNCTION public.kappa_retry_event_delivery(bigint, uuid, integer, text)
    TO kappa_event_worker_executor;

DO $$
DECLARE
    owner_role text := 'kappa_event_capability_owner';
    executor_role text := 'kappa_event_worker_executor';
    item record;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
         WHERE rolname = owner_role AND NOT rolsuper AND NOT rolcanlogin
           AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication
           AND NOT rolinherit AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'Required role % must be NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, NOREPLICATION, NOBYPASSRLS', owner_role;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
         WHERE rolname = executor_role AND NOT rolsuper AND NOT rolcanlogin
           AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication
           AND NOT rolinherit AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'Required role % must be NOLOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, NOREPLICATION, NOBYPASSRLS', executor_role;
    END IF;

    -- Neon adds a platform-managed, non-inheritable/non-settable membership
    -- from neondb_owner to newly provisioned roles, granted by cloud_admin.
    -- Permit only that exact platform edge; capability roles may not inherit
    -- from any other role and no application/runtime login may be a member yet.
    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_auth_members m
          JOIN pg_catalog.pg_roles member_role ON member_role.oid = m.member
          JOIN pg_catalog.pg_roles grantor_role ON grantor_role.oid = m.grantor
         WHERE m.member = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = owner_role)
            OR (
                m.roleid = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = owner_role)
                AND NOT (
                    member_role.rolname = 'neondb_owner'
                    AND grantor_role.rolname = 'cloud_admin'
                    AND m.admin_option
                    AND NOT m.inherit_option
                    AND NOT m.set_option
                )
            )
    ) THEN
        RAISE EXCEPTION 'Function owner % has an unexpected role membership', owner_role;
    END IF;
    IF EXISTS (
        SELECT 1
          FROM pg_catalog.pg_auth_members m
          JOIN pg_catalog.pg_roles member_role ON member_role.oid = m.member
          JOIN pg_catalog.pg_roles grantor_role ON grantor_role.oid = m.grantor
         WHERE m.member = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = executor_role)
            OR (
                m.roleid = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = executor_role)
                AND NOT (
                    member_role.rolname = 'neondb_owner'
                    AND grantor_role.rolname = 'cloud_admin'
                    AND m.admin_option
                    AND NOT m.inherit_option
                    AND NOT m.set_option
                )
            )
    ) THEN
        RAISE EXCEPTION 'Executor role % has an unexpected role membership', executor_role;
    END IF;

    FOR item IN SELECT unnest(ARRAY['kappa_domain_events', 'kappa_event_deliveries']) AS table_name
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = item.table_name
        ) THEN
            RAISE EXCEPTION 'Required table public.% does not exist', item.table_name;
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = item.table_name
              AND c.relowner = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = owner_role)
        ) THEN
            RAISE EXCEPTION 'Function owner % must not own protected table %', owner_role, item.table_name;
        END IF;
    END LOOP;
END;
$$;

GRANT USAGE ON SCHEMA public TO kappa_event_capability_owner, kappa_event_worker_executor;
REVOKE ALL ON public.kappa_domain_events, public.kappa_event_deliveries
    FROM kappa_event_capability_owner;

GRANT SELECT (id, event_id, consumer_key, status, attempts, available_at,
              lease_token, lease_expires_at, created_at),
      UPDATE (status, attempts, available_at, lease_token, lease_expires_at,
              last_error_code, updated_at, delivered_at)
ON public.kappa_event_deliveries TO kappa_event_capability_owner;

GRANT SELECT (id, tenant_id, event_type, payload)
ON public.kappa_domain_events TO kappa_event_capability_owner;

-- Transfer ownership with temporary membership and schema CREATE, then
-- revoke both temporary grants. Neon retains only its non-inheritable/non-settable
-- platform membership from neondb_owner to the capability role.
DO $$
DECLARE
    owner_role text := 'kappa_event_capability_owner';
    is_superuser boolean;
    item text;
BEGIN
    SELECT rolsuper INTO is_superuser
      FROM pg_catalog.pg_roles WHERE rolname = CURRENT_USER;
    IF NOT is_superuser THEN
        EXECUTE pg_catalog.format('GRANT %I TO %I', owner_role, CURRENT_USER);
        EXECUTE pg_catalog.format('GRANT CREATE ON SCHEMA public TO %I', owner_role);
    END IF;
    FOREACH item IN ARRAY ARRAY[
        'public.kappa_recover_exhausted_event_leases(text)',
        'public.kappa_claim_event_delivery(text,integer)',
        'public.kappa_ack_event_delivery(bigint,uuid)',
        'public.kappa_retry_event_delivery(bigint,uuid,integer,text)'
    ]
    LOOP
        EXECUTE pg_catalog.format(
            'ALTER FUNCTION %s OWNER TO %I', item::pg_catalog.regprocedure, owner_role
        );
    END LOOP;
    IF NOT is_superuser THEN
        EXECUTE pg_catalog.format('REVOKE CREATE ON SCHEMA public FROM %I', owner_role);
        EXECUTE pg_catalog.format('REVOKE %I FROM %I', owner_role, CURRENT_USER);
    END IF;
END;
$$;

