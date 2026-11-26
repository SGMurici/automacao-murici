-- Provider-scoped external connection persistence and refresh capabilities.
-- Local-only migration. Requires the OAuth capability roles from 0030/0034.
-- No LOGIN role, runtime membership, RLS, Analytics token, or publisher capability is created.

CREATE OR REPLACE FUNCTION public.kappa_oauth_connection_context_valid(
    p_user_id uuid, p_tenant_id uuid
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE
    v_user text := pg_catalog.current_setting('app.user_id', true);
    v_tenant text := pg_catalog.current_setting('app.tenant_id', true);
    v_actor_role text := pg_catalog.current_setting('app.actor_role', true);
BEGIN
    IF p_user_id IS NULL OR p_tenant_id IS NULL
       OR v_user IS DISTINCT FROM p_user_id::text
       OR v_tenant IS DISTINCT FROM p_tenant_id::text
       OR v_actor_role IS NULL THEN RETURN false; END IF;
    RETURN EXISTS (
        SELECT 1 FROM public.tenant_memberships m
        JOIN public.app_users u ON u.id = m.user_id
        WHERE m.user_id = p_user_id AND m.tenant_id = p_tenant_id
          AND m.status = 'active' AND m.role::text = v_actor_role
          AND u.status = 'active' AND u.deleted_at IS NULL
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_upsert_google_gmail_connection(
    p_id uuid, p_user_id uuid, p_tenant_id uuid, p_external_account_id text,
    p_account_label text, p_granted_scopes text[], p_access_token_ciphertext bytea,
    p_refresh_token_ciphertext bytea, p_token_expires_at timestamptz
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_id uuid;
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id, p_tenant_id)
       OR p_id IS NULL OR p_external_account_id IS NULL
       OR pg_catalog.length(p_external_account_id) NOT BETWEEN 1 AND 255
       OR p_account_label IS NULL OR pg_catalog.length(p_account_label) NOT BETWEEN 1 AND 160
       OR p_granted_scopes IS DISTINCT FROM ARRAY['https://www.googleapis.com/auth/gmail.readonly']::text[]
       OR p_access_token_ciphertext IS NULL OR pg_catalog.octet_length(p_access_token_ciphertext) = 0
       OR p_token_expires_at IS NULL OR p_token_expires_at <= pg_catalog.now()
    THEN RAISE EXCEPTION 'Invalid Google connection context or parameters'; END IF;
    INSERT INTO public.external_connections
        (id,user_id,tenant_id,provider,external_account_id,account_label,granted_scopes,
         access_token_ciphertext,refresh_token_ciphertext,token_expires_at,status,connection_purpose)
    VALUES (p_id,p_user_id,p_tenant_id,'google_gmail',p_external_account_id,p_account_label,
            p_granted_scopes,p_access_token_ciphertext,p_refresh_token_ciphertext,
            p_token_expires_at,'active','gmail_read')
    ON CONFLICT (tenant_id,provider,external_account_id,connection_purpose)
        WHERE provider = 'google_gmail'
    DO UPDATE SET account_label=EXCLUDED.account_label, granted_scopes=EXCLUDED.granted_scopes,
        access_token_ciphertext=EXCLUDED.access_token_ciphertext,
        refresh_token_ciphertext=EXCLUDED.refresh_token_ciphertext,
        token_expires_at=EXCLUDED.token_expires_at, status='active',
        revoked_at=NULL, updated_at=pg_catalog.now()
    WHERE external_connections.user_id=EXCLUDED.user_id
      AND external_connections.connection_purpose='gmail_read'
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_upsert_microsoft_connection(
    p_id uuid, p_user_id uuid, p_tenant_id uuid, p_external_account_id text,
    p_account_label text, p_granted_scopes text[], p_access_token_ciphertext bytea,
    p_refresh_token_ciphertext bytea, p_token_expires_at timestamptz
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_id uuid;
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
       OR p_id IS NULL OR p_external_account_id IS NULL
       OR pg_catalog.length(p_external_account_id) NOT BETWEEN 1 AND 255
       OR p_account_label IS NULL OR pg_catalog.length(p_account_label) NOT BETWEEN 1 AND 160
       OR p_granted_scopes IS NULL OR pg_catalog.cardinality(p_granted_scopes)=0
       OR NOT ('https://graph.microsoft.com/Mail.Read'=ANY(p_granted_scopes))
       OR NOT ('offline_access'=ANY(p_granted_scopes))
       OR NOT (p_granted_scopes <@ ARRAY['openid','profile','email','offline_access','https://graph.microsoft.com/Mail.Read']::text[])
       OR p_access_token_ciphertext IS NULL OR pg_catalog.octet_length(p_access_token_ciphertext)=0
       OR p_token_expires_at IS NULL OR p_token_expires_at<=pg_catalog.now()
    THEN RAISE EXCEPTION 'Invalid Microsoft connection context or parameters'; END IF;
    INSERT INTO public.external_connections
        (id,user_id,tenant_id,provider,external_account_id,account_label,granted_scopes,
         access_token_ciphertext,refresh_token_ciphertext,token_expires_at,status,connection_purpose)
    VALUES (p_id,p_user_id,p_tenant_id,'microsoft_outlook',p_external_account_id,p_account_label,
            p_granted_scopes,p_access_token_ciphertext,p_refresh_token_ciphertext,
            p_token_expires_at,'active',NULL)
    ON CONFLICT (tenant_id,provider,external_account_id) WHERE provider <> 'google_gmail'
    DO UPDATE SET account_label=EXCLUDED.account_label, granted_scopes=EXCLUDED.granted_scopes,
        access_token_ciphertext=EXCLUDED.access_token_ciphertext,
        refresh_token_ciphertext=EXCLUDED.refresh_token_ciphertext,
        token_expires_at=EXCLUDED.token_expires_at, status='active',
        revoked_at=NULL, updated_at=pg_catalog.now()
    WHERE external_connections.user_id=EXCLUDED.user_id
      AND external_connections.provider='microsoft_outlook'
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_upsert_linkedin_connection(
    p_id uuid, p_user_id uuid, p_tenant_id uuid, p_external_account_id text,
    p_account_label text, p_granted_scopes text[], p_access_token_ciphertext bytea,
    p_token_expires_at timestamptz
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_id uuid;
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
       OR p_id IS NULL OR p_external_account_id IS NULL
       OR pg_catalog.length(p_external_account_id) NOT BETWEEN 1 AND 255
       OR p_account_label IS NULL OR pg_catalog.length(p_account_label) NOT BETWEEN 1 AND 160
       OR p_granted_scopes IS NULL OR pg_catalog.cardinality(p_granted_scopes)=0
       OR NOT ('w_member_social'=ANY(p_granted_scopes))
       OR NOT (p_granted_scopes <@ ARRAY['openid','profile','email','w_member_social']::text[])
       OR p_access_token_ciphertext IS NULL OR pg_catalog.octet_length(p_access_token_ciphertext)=0
       OR p_token_expires_at IS NULL OR p_token_expires_at<=pg_catalog.now()
    THEN RAISE EXCEPTION 'Invalid LinkedIn connection context or parameters'; END IF;
    INSERT INTO public.external_connections
        (id,user_id,tenant_id,provider,external_account_id,account_label,granted_scopes,
         access_token_ciphertext,token_expires_at,status,connection_purpose)
    VALUES (p_id,p_user_id,p_tenant_id,'linkedin',p_external_account_id,p_account_label,
            p_granted_scopes,p_access_token_ciphertext,p_token_expires_at,'active',NULL)
    ON CONFLICT (tenant_id,provider,external_account_id) WHERE provider <> 'google_gmail'
    DO UPDATE SET account_label=EXCLUDED.account_label, granted_scopes=EXCLUDED.granted_scopes,
        access_token_ciphertext=EXCLUDED.access_token_ciphertext,
        token_expires_at=EXCLUDED.token_expires_at, status='active',
        revoked_at=NULL, updated_at=pg_catalog.now()
    WHERE external_connections.user_id=EXCLUDED.user_id
      AND external_connections.provider='linkedin'
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_read_external_connection_status(
    p_user_id uuid, p_tenant_id uuid, p_provider text
) RETURNS TABLE(
    id uuid, provider varchar(30), connection_purpose varchar(24),
    external_account_id varchar(255), account_label varchar(160),
    granted_scopes text[], status varchar(40), token_expires_at timestamptz,
    updated_at timestamptz
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
       OR p_provider IS NULL
       OR p_provider NOT IN ('google_gmail','microsoft_outlook','linkedin')
    THEN RAISE EXCEPTION 'Invalid external connection status context'; END IF;
    RETURN QUERY SELECT c.id,c.provider,c.connection_purpose,c.external_account_id,
        c.account_label,c.granted_scopes,c.status,c.token_expires_at,c.updated_at
      FROM public.external_connections c
     WHERE c.user_id=p_user_id AND c.tenant_id=p_tenant_id AND c.provider=p_provider
     ORDER BY c.updated_at DESC,c.id;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_read_google_gmail_token(
    p_connection_id uuid, p_user_id uuid, p_tenant_id uuid
) RETURNS TABLE(access_token_ciphertext bytea,refresh_token_ciphertext bytea,token_expires_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
    THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    RETURN QUERY SELECT c.access_token_ciphertext,c.refresh_token_ciphertext,c.token_expires_at
      FROM public.external_connections c
     WHERE c.id=p_connection_id AND c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='google_gmail' AND c.connection_purpose='gmail_read' AND c.status='active';
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_read_microsoft_token(
    p_connection_id uuid, p_user_id uuid, p_tenant_id uuid
) RETURNS TABLE(access_token_ciphertext bytea,refresh_token_ciphertext bytea,token_expires_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
    THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    RETURN QUERY SELECT c.access_token_ciphertext,c.refresh_token_ciphertext,c.token_expires_at
      FROM public.external_connections c
     WHERE c.id=p_connection_id AND c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='microsoft_outlook' AND c.connection_purpose IS NULL AND c.status='active';
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_refresh_google_gmail_token(
    p_connection_id uuid,p_user_id uuid,p_tenant_id uuid,p_expected_refresh_ciphertext bytea,
    p_access_token_ciphertext bytea,p_refresh_token_ciphertext bytea,p_token_expires_at timestamptz
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
       OR p_access_token_ciphertext IS NULL OR pg_catalog.octet_length(p_access_token_ciphertext)=0
       OR p_token_expires_at IS NULL OR p_token_expires_at<=pg_catalog.now()
    THEN RAISE EXCEPTION 'Invalid Google token refresh context'; END IF;
    UPDATE public.external_connections c SET access_token_ciphertext=p_access_token_ciphertext,
        refresh_token_ciphertext=p_refresh_token_ciphertext,token_expires_at=p_token_expires_at,
        updated_at=pg_catalog.now()
     WHERE c.id=p_connection_id AND c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='google_gmail' AND c.connection_purpose='gmail_read' AND c.status='active'
       AND c.refresh_token_ciphertext IS NOT DISTINCT FROM p_expected_refresh_ciphertext;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_refresh_microsoft_token(
    p_connection_id uuid,p_user_id uuid,p_tenant_id uuid,p_expected_refresh_ciphertext bytea,
    p_access_token_ciphertext bytea,p_refresh_token_ciphertext bytea,p_token_expires_at timestamptz
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
       OR p_access_token_ciphertext IS NULL OR pg_catalog.octet_length(p_access_token_ciphertext)=0
       OR p_token_expires_at IS NULL OR p_token_expires_at<=pg_catalog.now()
    THEN RAISE EXCEPTION 'Invalid Microsoft token refresh context'; END IF;
    UPDATE public.external_connections c SET access_token_ciphertext=p_access_token_ciphertext,
        refresh_token_ciphertext=p_refresh_token_ciphertext,token_expires_at=p_token_expires_at,
        updated_at=pg_catalog.now()
     WHERE c.id=p_connection_id AND c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='microsoft_outlook' AND c.connection_purpose IS NULL AND c.status='active'
       AND c.refresh_token_ciphertext IS NOT DISTINCT FROM p_expected_refresh_ciphertext;
    RETURN FOUND;
END;
$$;


CREATE OR REPLACE FUNCTION public.kappa_mark_google_gmail_reauthorization_required(
    p_connection_id uuid,p_user_id uuid,p_tenant_id uuid,p_expected_refresh_ciphertext bytea
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
    THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    UPDATE public.external_connections c
       SET status='reauthorization_required',updated_at=pg_catalog.now()
     WHERE c.id=p_connection_id AND c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='google_gmail' AND c.connection_purpose='gmail_read'
       AND c.status='active'
       AND c.refresh_token_ciphertext IS NOT DISTINCT FROM p_expected_refresh_ciphertext;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_mark_microsoft_reauthorization_required(
    p_connection_id uuid,p_user_id uuid,p_tenant_id uuid
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
    THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    UPDATE public.external_connections c
       SET status='reauthorization_required',updated_at=pg_catalog.now()
     WHERE c.id=p_connection_id AND c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='microsoft_outlook' AND c.connection_purpose IS NULL
       AND c.status='active';
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_begin_google_gmail_revocation(
    p_user_id uuid,p_tenant_id uuid
) RETURNS TABLE(
    id uuid,connection_purpose varchar(24),
    access_token_ciphertext bytea,refresh_token_ciphertext bytea
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
    THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    RETURN QUERY
    UPDATE public.external_connections c
       SET status='reauthorization_required',updated_at=pg_catalog.now()
     WHERE c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='google_gmail' AND c.connection_purpose='gmail_read'
       AND c.status IN ('active','reauthorization_required')
    RETURNING c.id,c.connection_purpose,c.access_token_ciphertext,c.refresh_token_ciphertext;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_finish_google_gmail_revocation(
    p_connection_id uuid,p_user_id uuid,p_tenant_id uuid
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
    THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    UPDATE public.external_connections c
       SET status='revoked',revoked_at=pg_catalog.now(),
           access_token_ciphertext=NULL,refresh_token_ciphertext=NULL,
           updated_at=pg_catalog.now()
     WHERE c.id=p_connection_id AND c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='google_gmail' AND c.connection_purpose='gmail_read'
       AND c.status='reauthorization_required';
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_revoke_microsoft_connections(
    p_user_id uuid,p_tenant_id uuid
) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
DECLARE v_count integer;
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
    THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    UPDATE public.external_connections c
       SET status='revoked',revoked_at=pg_catalog.now(),
           access_token_ciphertext=NULL,refresh_token_ciphertext=NULL,
           updated_at=pg_catalog.now()
     WHERE c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='microsoft_outlook'
       AND c.status IN ('active','reauthorization_required');
    GET DIAGNOSTICS v_count=ROW_COUNT;
    RETURN v_count;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_revoke_linkedin_connection(
    p_connection_id uuid,p_user_id uuid,p_tenant_id uuid
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT public.kappa_oauth_connection_context_valid(p_user_id,p_tenant_id)
    THEN RAISE EXCEPTION 'Active tenant membership required'; END IF;
    UPDATE public.external_connections c
       SET status='revoked',revoked_at=pg_catalog.now(),
           access_token_ciphertext=NULL,updated_at=pg_catalog.now()
     WHERE c.id=p_connection_id AND c.user_id=p_user_id AND c.tenant_id=p_tenant_id
       AND c.provider='linkedin' AND c.connection_purpose IS NULL
       AND c.status='active';
    RETURN FOUND;
END;
$$;

REVOKE ALL ON FUNCTION public.kappa_mark_google_gmail_reauthorization_required(uuid,uuid,uuid,bytea) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_mark_microsoft_reauthorization_required(uuid,uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_begin_google_gmail_revocation(uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_finish_google_gmail_revocation(uuid,uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_revoke_microsoft_connections(uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_revoke_linkedin_connection(uuid,uuid,uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.kappa_mark_google_gmail_reauthorization_required(uuid,uuid,uuid,bytea) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_mark_microsoft_reauthorization_required(uuid,uuid,uuid) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_begin_google_gmail_revocation(uuid,uuid) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_finish_google_gmail_revocation(uuid,uuid,uuid) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_revoke_microsoft_connections(uuid,uuid) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_revoke_linkedin_connection(uuid,uuid,uuid) TO kappa_api_oauth_executor;

REVOKE ALL ON FUNCTION public.kappa_oauth_connection_context_valid(uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_upsert_google_gmail_connection(uuid,uuid,uuid,text,text,text[],bytea,bytea,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_upsert_microsoft_connection(uuid,uuid,uuid,text,text,text[],bytea,bytea,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_upsert_linkedin_connection(uuid,uuid,uuid,text,text,text[],bytea,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_read_external_connection_status(uuid,uuid,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_read_google_gmail_token(uuid,uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_read_microsoft_token(uuid,uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_refresh_google_gmail_token(uuid,uuid,uuid,bytea,bytea,bytea,timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_refresh_microsoft_token(uuid,uuid,uuid,bytea,bytea,bytea,timestamptz) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.kappa_upsert_google_gmail_connection(uuid,uuid,uuid,text,text,text[],bytea,bytea,timestamptz) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_upsert_microsoft_connection(uuid,uuid,uuid,text,text,text[],bytea,bytea,timestamptz) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_upsert_linkedin_connection(uuid,uuid,uuid,text,text,text[],bytea,timestamptz) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_read_external_connection_status(uuid,uuid,text) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_read_google_gmail_token(uuid,uuid,uuid) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_read_microsoft_token(uuid,uuid,uuid) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_refresh_google_gmail_token(uuid,uuid,uuid,bytea,bytea,bytea,timestamptz) TO kappa_api_oauth_executor;
GRANT EXECUTE ON FUNCTION public.kappa_refresh_microsoft_token(uuid,uuid,uuid,bytea,bytea,bytea,timestamptz) TO kappa_api_oauth_executor;

-- The owner gets only the columns referenced by the fixed functions.
REVOKE ALL ON public.external_connections FROM kappa_oauth_capability_owner;
REVOKE ALL ON public.external_connections FROM kappa_api_oauth_executor;
GRANT SELECT (user_id,tenant_id,status,role) ON public.tenant_memberships TO kappa_oauth_capability_owner;
GRANT SELECT (id,status,deleted_at) ON public.app_users TO kappa_oauth_capability_owner;
GRANT SELECT (id,user_id,tenant_id,provider,connection_purpose,external_account_id,
    account_label,granted_scopes,access_token_ciphertext,refresh_token_ciphertext,
    token_expires_at,status,updated_at)
ON public.external_connections TO kappa_oauth_capability_owner;
GRANT INSERT (id,user_id,tenant_id,provider,external_account_id,account_label,granted_scopes,
    access_token_ciphertext,refresh_token_ciphertext,token_expires_at,status,connection_purpose)
ON public.external_connections TO kappa_oauth_capability_owner;
GRANT UPDATE (account_label,granted_scopes,access_token_ciphertext,refresh_token_ciphertext,
    token_expires_at,status,revoked_at,updated_at)
ON public.external_connections TO kappa_oauth_capability_owner;

DO $$
DECLARE is_superuser boolean;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='kappa_oauth_capability_owner'
        AND NOT rolsuper AND NOT rolcanlogin AND NOT rolcreatedb AND NOT rolcreaterole
        AND NOT rolreplication AND NOT rolinherit AND NOT rolbypassrls)
       OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='kappa_api_oauth_executor'
        AND NOT rolsuper AND NOT rolcanlogin AND NOT rolcreatedb AND NOT rolcreaterole
        AND NOT rolreplication AND NOT rolinherit AND NOT rolbypassrls)
    THEN RAISE EXCEPTION 'OAuth capability roles are missing or unsafe'; END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_catalog.pg_roles r ON r.oid=c.relowner
        WHERE n.nspname='public' AND c.relname='external_connections'
          AND r.rolname='kappa_oauth_capability_owner')
    THEN RAISE EXCEPTION 'Capability owner must not own external_connections'; END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles member_role ON member_role.oid=m.member
        JOIN pg_catalog.pg_roles grantor_role ON grantor_role.oid=m.grantor
        WHERE m.member=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='kappa_oauth_capability_owner')
           OR (m.roleid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='kappa_oauth_capability_owner')
               AND NOT (member_role.rolname='neondb_owner' AND grantor_role.rolname='cloud_admin'
                        AND m.admin_option AND NOT m.inherit_option AND NOT m.set_option))
    ) THEN RAISE EXCEPTION 'Capability owner has an unexpected role membership'; END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles member_role ON member_role.oid=m.member
        JOIN pg_catalog.pg_roles grantor_role ON grantor_role.oid=m.grantor
        WHERE m.member=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='kappa_api_oauth_executor')
           OR (m.roleid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='kappa_api_oauth_executor')
               AND NOT (member_role.rolname='neondb_owner' AND grantor_role.rolname='cloud_admin'
                        AND m.admin_option AND NOT m.inherit_option AND NOT m.set_option))
    ) THEN RAISE EXCEPTION 'API executor has an unexpected role membership'; END IF;
    SELECT rolsuper INTO is_superuser FROM pg_catalog.pg_roles WHERE rolname=CURRENT_USER;
    IF NOT is_superuser THEN
        EXECUTE pg_catalog.format('GRANT kappa_oauth_capability_owner TO %I',CURRENT_USER);
        GRANT CREATE ON SCHEMA public TO kappa_oauth_capability_owner;
    END IF;
    ALTER FUNCTION public.kappa_oauth_connection_context_valid(uuid,uuid) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_upsert_google_gmail_connection(uuid,uuid,uuid,text,text,text[],bytea,bytea,timestamptz) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_upsert_microsoft_connection(uuid,uuid,uuid,text,text,text[],bytea,bytea,timestamptz) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_upsert_linkedin_connection(uuid,uuid,uuid,text,text,text[],bytea,timestamptz) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_read_external_connection_status(uuid,uuid,text) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_read_google_gmail_token(uuid,uuid,uuid) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_read_microsoft_token(uuid,uuid,uuid) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_refresh_google_gmail_token(uuid,uuid,uuid,bytea,bytea,bytea,timestamptz) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_refresh_microsoft_token(uuid,uuid,uuid,bytea,bytea,bytea,timestamptz) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_mark_google_gmail_reauthorization_required(uuid,uuid,uuid,bytea) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_mark_microsoft_reauthorization_required(uuid,uuid,uuid) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_begin_google_gmail_revocation(uuid,uuid) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_finish_google_gmail_revocation(uuid,uuid,uuid) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_revoke_microsoft_connections(uuid,uuid) OWNER TO kappa_oauth_capability_owner;
    ALTER FUNCTION public.kappa_revoke_linkedin_connection(uuid,uuid,uuid) OWNER TO kappa_oauth_capability_owner;
    IF NOT is_superuser THEN
        REVOKE CREATE ON SCHEMA public FROM kappa_oauth_capability_owner;
        EXECUTE pg_catalog.format('REVOKE kappa_oauth_capability_owner FROM %I',CURRENT_USER);
    END IF;
END;
$$;
