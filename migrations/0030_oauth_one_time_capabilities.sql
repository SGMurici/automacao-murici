-- One-time OAuth state/ticket consumption capabilities.
-- Prerequisite: provision both NOLOGIN roles as described in docs/70.
-- The function owner must not own protected tables and must not bypass RLS.
-- Capability roles may only have the Neon-managed incoming membership from
-- neondb_owner (NOINHERIT/NOSET); ownership transfer uses temporary grants.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = CURRENT_USER AND (rolsuper OR rolcreaterole)
    ) THEN
        RAISE EXCEPTION 'Migration 0030 requires a superuser or a CREATEROLE migration principal with controlled membership on the capability owner';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_consume_google_oauth_state(p_hash text)
RETURNS TABLE(user_id uuid, tenant_id uuid, purpose varchar(24), pkce_verifier_ciphertext bytea)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$' THEN RETURN; END IF;
    RETURN QUERY
    UPDATE public.client_google_oauth_states AS s
       SET consumed_at = pg_catalog.now()
     WHERE s.state_hash = p_hash::char(64)
       AND s.consumed_at IS NULL AND s.expires_at > pg_catalog.now()
    RETURNING s.user_id, s.tenant_id, s.purpose, s.pkce_verifier_ciphertext;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_consume_microsoft_oauth_state(p_hash text)
RETURNS TABLE(user_id uuid, tenant_id uuid, pkce_verifier_ciphertext bytea)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$' THEN RETURN; END IF;
    RETURN QUERY
    UPDATE public.client_microsoft_oauth_states AS s
       SET consumed_at = pg_catalog.now()
     WHERE s.state_hash = p_hash::char(64)
       AND s.consumed_at IS NULL AND s.expires_at > pg_catalog.now()
    RETURNING s.user_id, s.tenant_id, s.pkce_verifier_ciphertext;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_consume_linkedin_oauth_state(p_hash text)
RETURNS TABLE(user_id uuid, tenant_id uuid)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$' THEN RETURN; END IF;
    RETURN QUERY
    UPDATE public.client_linkedin_oauth_states AS s
       SET consumed_at = pg_catalog.now()
     WHERE s.state_hash = p_hash::char(64)
       AND s.consumed_at IS NULL AND s.expires_at > pg_catalog.now()
    RETURNING s.user_id, s.tenant_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_consume_linkedin_analytics_oauth_state(p_hash text)
RETURNS TABLE(user_id uuid, tenant_id uuid)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$' THEN RETURN; END IF;
    RETURN QUERY
    UPDATE public.linkedin_analytics_oauth_states AS s
       SET consumed_at = pg_catalog.now()
     WHERE s.state_hash = p_hash::char(64)
       AND s.consumed_at IS NULL AND s.expires_at > pg_catalog.now()
    RETURNING s.user_id, s.tenant_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_consume_google_oauth_ticket(
    p_hash text, p_user_id uuid, p_tenant_id uuid
)
RETURNS TABLE(purpose varchar(24), external_connection_id uuid)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR p_user_id IS NULL OR p_tenant_id IS NULL THEN RETURN; END IF;
    RETURN QUERY
    UPDATE public.client_google_oauth_tickets AS t
       SET consumed_at = pg_catalog.now()
     WHERE t.ticket_hash = p_hash::char(64)
       AND t.user_id = p_user_id AND t.tenant_id = p_tenant_id
       AND t.consumed_at IS NULL AND t.expires_at > pg_catalog.now()
    RETURNING t.purpose, t.external_connection_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_consume_microsoft_oauth_ticket(
    p_hash text, p_user_id uuid, p_tenant_id uuid
)
RETURNS TABLE(external_connection_id uuid)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR p_user_id IS NULL OR p_tenant_id IS NULL THEN RETURN; END IF;
    RETURN QUERY
    UPDATE public.client_microsoft_oauth_tickets AS t
       SET consumed_at = pg_catalog.now()
     WHERE t.ticket_hash = p_hash::char(64)
       AND t.user_id = p_user_id AND t.tenant_id = p_tenant_id
       AND t.consumed_at IS NULL AND t.expires_at > pg_catalog.now()
    RETURNING t.external_connection_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_consume_linkedin_oauth_ticket(
    p_hash text, p_user_id uuid, p_tenant_id uuid
)
RETURNS TABLE(external_connection_id uuid)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR p_user_id IS NULL OR p_tenant_id IS NULL THEN RETURN; END IF;
    RETURN QUERY
    UPDATE public.client_linkedin_oauth_tickets AS t
       SET consumed_at = pg_catalog.now()
     WHERE t.ticket_hash = p_hash::char(64)
       AND t.user_id = p_user_id AND t.tenant_id = p_tenant_id
       AND t.consumed_at IS NULL AND t.expires_at > pg_catalog.now()
    RETURNING t.external_connection_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_consume_linkedin_analytics_oauth_ticket(
    p_hash text, p_user_id uuid, p_tenant_id uuid
)
RETURNS TABLE(analytics_connection_id uuid)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR p_user_id IS NULL OR p_tenant_id IS NULL THEN RETURN; END IF;
    RETURN QUERY
    UPDATE public.linkedin_analytics_oauth_tickets AS t
       SET consumed_at = pg_catalog.now()
     WHERE t.ticket_hash = p_hash::char(64)
       AND t.user_id = p_user_id AND t.tenant_id = p_tenant_id
       AND t.consumed_at IS NULL AND t.expires_at > pg_catalog.now()
    RETURNING t.analytics_connection_id;
END;
$$;

REVOKE ALL ON FUNCTION public.kappa_consume_google_oauth_state(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_consume_microsoft_oauth_state(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_consume_linkedin_oauth_state(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_consume_linkedin_analytics_oauth_state(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_consume_google_oauth_ticket(text, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_consume_microsoft_oauth_ticket(text, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_consume_linkedin_oauth_ticket(text, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_consume_linkedin_analytics_oauth_ticket(text, uuid, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.kappa_consume_google_oauth_state(text) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_consume_microsoft_oauth_state(text) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_consume_linkedin_oauth_state(text) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_consume_linkedin_analytics_oauth_state(text) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_consume_google_oauth_ticket(text, uuid, uuid) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_consume_microsoft_oauth_ticket(text, uuid, uuid) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_consume_linkedin_oauth_ticket(text, uuid, uuid) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_consume_linkedin_analytics_oauth_ticket(text, uuid, uuid) TO kappa_api_oauth_executor;

DO $$
DECLARE
    owner_role text := 'kappa_oauth_capability_owner';
    executor_role text := 'kappa_api_oauth_executor';
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

    FOR item IN SELECT unnest(ARRAY[
        'client_google_oauth_states', 'client_microsoft_oauth_states',
        'client_linkedin_oauth_states', 'linkedin_analytics_oauth_states',
        'client_google_oauth_tickets', 'client_microsoft_oauth_tickets',
        'client_linkedin_oauth_tickets', 'linkedin_analytics_oauth_tickets'
    ]) AS table_name
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = item.table_name
        ) THEN
            RAISE EXCEPTION 'Required protected table public.% does not exist', item.table_name;
        END IF;
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
            WHERE n.nspname = 'public' AND c.relname = item.table_name
              AND r.rolname = owner_role
        ) THEN
            RAISE EXCEPTION 'Function owner % must not own protected table %', owner_role, item.table_name;
        END IF;
    END LOOP;
END;
$$;

GRANT USAGE ON SCHEMA public TO kappa_oauth_capability_owner, kappa_api_oauth_executor;
REVOKE ALL ON
    public.client_google_oauth_states,
    public.client_microsoft_oauth_states,
    public.client_linkedin_oauth_states,
    public.linkedin_analytics_oauth_states,
    public.client_google_oauth_tickets,
    public.client_microsoft_oauth_tickets,
    public.client_linkedin_oauth_tickets,
    public.linkedin_analytics_oauth_tickets
FROM kappa_oauth_capability_owner;

GRANT SELECT (state_hash, user_id, tenant_id, purpose, pkce_verifier_ciphertext, consumed_at, expires_at),
      UPDATE (consumed_at)
ON public.client_google_oauth_states TO kappa_oauth_capability_owner;
GRANT SELECT (state_hash, user_id, tenant_id, pkce_verifier_ciphertext, consumed_at, expires_at),
      UPDATE (consumed_at)
ON public.client_microsoft_oauth_states TO kappa_oauth_capability_owner;
GRANT SELECT (state_hash, user_id, tenant_id, consumed_at, expires_at),
      UPDATE (consumed_at)
ON public.client_linkedin_oauth_states TO kappa_oauth_capability_owner;
GRANT SELECT (state_hash, user_id, tenant_id, consumed_at, expires_at),
      UPDATE (consumed_at)
ON public.linkedin_analytics_oauth_states TO kappa_oauth_capability_owner;
GRANT SELECT (ticket_hash, user_id, tenant_id, purpose, external_connection_id, consumed_at, expires_at),
      UPDATE (consumed_at)
ON public.client_google_oauth_tickets TO kappa_oauth_capability_owner;
GRANT SELECT (ticket_hash, user_id, tenant_id, external_connection_id, consumed_at, expires_at),
      UPDATE (consumed_at)
ON public.client_microsoft_oauth_tickets TO kappa_oauth_capability_owner;
GRANT SELECT (ticket_hash, user_id, tenant_id, external_connection_id, consumed_at, expires_at),
      UPDATE (consumed_at)
ON public.client_linkedin_oauth_tickets TO kappa_oauth_capability_owner;
GRANT SELECT (ticket_hash, user_id, tenant_id, analytics_connection_id, consumed_at, expires_at),
      UPDATE (consumed_at)
ON public.linkedin_analytics_oauth_tickets TO kappa_oauth_capability_owner;

REVOKE ALL ON
    public.client_google_oauth_states,
    public.client_microsoft_oauth_states,
    public.client_linkedin_oauth_states,
    public.linkedin_analytics_oauth_states,
    public.client_google_oauth_tickets,
    public.client_microsoft_oauth_tickets,
    public.client_linkedin_oauth_tickets,
    public.linkedin_analytics_oauth_tickets
FROM kappa_api_oauth_executor;

-- Transfer function ownership using a temporary SET ROLE membership. Neon
-- retains only its platform-managed membership (NOINHERIT, NOSET) afterwards.
DO $$
DECLARE
    owner_role text := 'kappa_oauth_capability_owner';
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
        'public.kappa_consume_google_oauth_state(text)',
        'public.kappa_consume_microsoft_oauth_state(text)',
        'public.kappa_consume_linkedin_oauth_state(text)',
        'public.kappa_consume_linkedin_analytics_oauth_state(text)',
        'public.kappa_consume_google_oauth_ticket(text,uuid,uuid)',
        'public.kappa_consume_microsoft_oauth_ticket(text,uuid,uuid)',
        'public.kappa_consume_linkedin_oauth_ticket(text,uuid,uuid)',
        'public.kappa_consume_linkedin_analytics_oauth_ticket(text,uuid,uuid)'
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

