-- Tenant-bound creation capabilities for OAuth states.
-- Requires migrations 0030-0033 and the existing capability roles.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'kappa_oauth_capability_owner'
          AND NOT rolsuper AND NOT rolcanlogin AND NOT rolcreatedb
          AND NOT rolcreaterole AND NOT rolreplication AND NOT rolinherit
          AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'Required capability owner is missing or unsafe';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'kappa_api_oauth_executor'
          AND NOT rolsuper AND NOT rolcanlogin AND NOT rolcreatedb
          AND NOT rolcreaterole AND NOT rolreplication AND NOT rolinherit
          AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'Required capability executor is missing or unsafe';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_create_google_oauth_state(
    p_hash text, p_user_id uuid, p_tenant_id uuid, p_purpose text,
    p_pkce_ciphertext bytea, p_ttl_seconds integer
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
    v_user text := pg_catalog.current_setting('app.user_id', true);
    v_tenant text := pg_catalog.current_setting('app.tenant_id', true);
    v_actor_role text := pg_catalog.current_setting('app.actor_role', true);
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR p_user_id IS NULL OR p_tenant_id IS NULL
       OR p_purpose IS NULL OR p_purpose NOT IN ('gmail_read', 'gmail_send')
       OR p_pkce_ciphertext IS NULL OR pg_catalog.octet_length(p_pkce_ciphertext) < 1
       OR p_ttl_seconds IS NULL OR p_ttl_seconds NOT BETWEEN 60 AND 900
       OR v_user IS DISTINCT FROM p_user_id::text
       OR v_tenant IS DISTINCT FROM p_tenant_id::text
       OR v_actor_role IS NULL THEN
        RAISE EXCEPTION 'Invalid OAuth state context or parameters';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.tenant_memberships m
        JOIN public.app_users u ON u.id = m.user_id
        WHERE m.user_id = p_user_id AND m.tenant_id = p_tenant_id
          AND m.status = 'active' AND m.role::text = v_actor_role
          AND u.status = 'active' AND u.deleted_at IS NULL
    ) THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    INSERT INTO public.client_google_oauth_states
        (state_hash, user_id, tenant_id, purpose, pkce_verifier_ciphertext, expires_at)
    VALUES (p_hash, p_user_id, p_tenant_id, p_purpose,
            p_pkce_ciphertext, pg_catalog.now() + p_ttl_seconds * INTERVAL '1 second');
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_create_microsoft_oauth_state(
    p_hash text, p_user_id uuid, p_tenant_id uuid,
    p_pkce_ciphertext bytea, p_ttl_seconds integer
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
    v_user text := pg_catalog.current_setting('app.user_id', true);
    v_tenant text := pg_catalog.current_setting('app.tenant_id', true);
    v_actor_role text := pg_catalog.current_setting('app.actor_role', true);
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR p_user_id IS NULL OR p_tenant_id IS NULL
       OR p_pkce_ciphertext IS NULL OR pg_catalog.octet_length(p_pkce_ciphertext) < 1
       OR p_ttl_seconds IS NULL OR p_ttl_seconds NOT BETWEEN 60 AND 900
       OR v_user IS DISTINCT FROM p_user_id::text
       OR v_tenant IS DISTINCT FROM p_tenant_id::text
       OR v_actor_role IS NULL THEN
        RAISE EXCEPTION 'Invalid OAuth state context or parameters';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.tenant_memberships m
        JOIN public.app_users u ON u.id = m.user_id
        WHERE m.user_id = p_user_id AND m.tenant_id = p_tenant_id
          AND m.status = 'active' AND m.role::text = v_actor_role
          AND u.status = 'active' AND u.deleted_at IS NULL
    ) THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    INSERT INTO public.client_microsoft_oauth_states
        (state_hash, user_id, tenant_id, pkce_verifier_ciphertext, expires_at)
    VALUES (p_hash, p_user_id, p_tenant_id, p_pkce_ciphertext,
            pg_catalog.now() + p_ttl_seconds * INTERVAL '1 second');
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_create_linkedin_oauth_state(
    p_hash text, p_user_id uuid, p_tenant_id uuid, p_ttl_seconds integer
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
    v_user text := pg_catalog.current_setting('app.user_id', true);
    v_tenant text := pg_catalog.current_setting('app.tenant_id', true);
    v_actor_role text := pg_catalog.current_setting('app.actor_role', true);
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR p_user_id IS NULL OR p_tenant_id IS NULL
       OR p_ttl_seconds IS NULL OR p_ttl_seconds NOT BETWEEN 60 AND 900
       OR v_user IS DISTINCT FROM p_user_id::text
       OR v_tenant IS DISTINCT FROM p_tenant_id::text
       OR v_actor_role IS NULL THEN
        RAISE EXCEPTION 'Invalid OAuth state context or parameters';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.tenant_memberships m
        JOIN public.app_users u ON u.id = m.user_id
        WHERE m.user_id = p_user_id AND m.tenant_id = p_tenant_id
          AND m.status = 'active' AND m.role::text = v_actor_role
          AND u.status = 'active' AND u.deleted_at IS NULL
    ) THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    INSERT INTO public.client_linkedin_oauth_states
        (state_hash, user_id, tenant_id, expires_at)
    VALUES (p_hash, p_user_id, p_tenant_id,
            pg_catalog.now() + p_ttl_seconds * INTERVAL '1 second');
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_create_linkedin_analytics_oauth_state(
    p_hash text, p_user_id uuid, p_tenant_id uuid, p_ttl_seconds integer
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
    v_user text := pg_catalog.current_setting('app.user_id', true);
    v_tenant text := pg_catalog.current_setting('app.tenant_id', true);
    v_actor_role text := pg_catalog.current_setting('app.actor_role', true);
BEGIN
    IF p_hash IS NULL OR p_hash !~ '^[0-9a-f]{64}$'
       OR p_user_id IS NULL OR p_tenant_id IS NULL
       OR p_ttl_seconds IS NULL OR p_ttl_seconds NOT BETWEEN 60 AND 900
       OR v_user IS DISTINCT FROM p_user_id::text
       OR v_tenant IS DISTINCT FROM p_tenant_id::text
       OR v_actor_role IS NULL THEN
        RAISE EXCEPTION 'Invalid OAuth state context or parameters';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.tenant_memberships m
        JOIN public.app_users u ON u.id = m.user_id
        WHERE m.user_id = p_user_id AND m.tenant_id = p_tenant_id
          AND m.status = 'active' AND m.role::text = v_actor_role
          AND u.status = 'active' AND u.deleted_at IS NULL
    ) THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    INSERT INTO public.linkedin_analytics_oauth_states
        (state_hash, user_id, tenant_id, expires_at)
    VALUES (p_hash, p_user_id, p_tenant_id,
            pg_catalog.now() + p_ttl_seconds * INTERVAL '1 second');
    RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.kappa_create_google_oauth_state(text,uuid,uuid,text,bytea,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_create_microsoft_oauth_state(text,uuid,uuid,bytea,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_create_linkedin_oauth_state(text,uuid,uuid,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_create_linkedin_analytics_oauth_state(text,uuid,uuid,integer) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.kappa_create_google_oauth_state(text,uuid,uuid,text,bytea,integer) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_create_microsoft_oauth_state(text,uuid,uuid,bytea,integer) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_create_linkedin_oauth_state(text,uuid,uuid,integer) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_create_linkedin_analytics_oauth_state(text,uuid,uuid,integer) TO kappa_api_oauth_executor;

GRANT SELECT (user_id, tenant_id, status, role) ON public.tenant_memberships TO kappa_oauth_capability_owner;
GRANT SELECT (id, status, deleted_at) ON public.app_users TO kappa_oauth_capability_owner;
GRANT INSERT (state_hash, user_id, tenant_id, purpose, pkce_verifier_ciphertext, expires_at)
    ON public.client_google_oauth_states TO kappa_oauth_capability_owner;
GRANT INSERT (state_hash, user_id, tenant_id, pkce_verifier_ciphertext, expires_at)
    ON public.client_microsoft_oauth_states TO kappa_oauth_capability_owner;
GRANT INSERT (state_hash, user_id, tenant_id, expires_at)
    ON public.client_linkedin_oauth_states, public.linkedin_analytics_oauth_states
    TO kappa_oauth_capability_owner;

DO $$
DECLARE
    is_superuser boolean;
    item text;
BEGIN
    SELECT rolsuper INTO is_superuser FROM pg_catalog.pg_roles WHERE rolname = CURRENT_USER;
    IF NOT is_superuser THEN
        EXECUTE 'GRANT kappa_oauth_capability_owner TO ' || pg_catalog.quote_ident(CURRENT_USER);
        EXECUTE 'GRANT CREATE ON SCHEMA public TO kappa_oauth_capability_owner';
    END IF;
    FOREACH item IN ARRAY ARRAY[
        'public.kappa_create_google_oauth_state(text,uuid,uuid,text,bytea,integer)',
        'public.kappa_create_microsoft_oauth_state(text,uuid,uuid,bytea,integer)',
        'public.kappa_create_linkedin_oauth_state(text,uuid,uuid,integer)',
        'public.kappa_create_linkedin_analytics_oauth_state(text,uuid,uuid,integer)'
    ] LOOP
        EXECUTE pg_catalog.format(
            'ALTER FUNCTION %s OWNER TO kappa_oauth_capability_owner',
            item::pg_catalog.regprocedure
        );
    END LOOP;
    IF NOT is_superuser THEN
        EXECUTE 'REVOKE CREATE ON SCHEMA public FROM kappa_oauth_capability_owner';
        EXECUTE 'REVOKE kappa_oauth_capability_owner FROM ' || pg_catalog.quote_ident(CURRENT_USER);
    END IF;
END;
$$;
