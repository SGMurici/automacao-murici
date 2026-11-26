-- Narrow SECURITY DEFINER capabilities for the OTP email outbox worker.
-- Local proposal only. Requires isolated NOLOGIN roles and real-role validation.
-- Do not apply to a shared Neon branch or production until separately authorized.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = CURRENT_USER AND (rolsuper OR rolcreaterole)
    ) THEN
        RAISE EXCEPTION 'Migration 0032 requires a superuser or a CREATEROLE migration principal with controlled membership on the capability owner';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_otp_outbox_expire_due()
RETURNS TABLE(uncertain integer, failed integer)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    v_uncertain integer := 0;
    v_failed integer := 0;
BEGIN
    WITH stale_dispatch AS (
        UPDATE public.otp_email_outbox
           SET status = 'uncertain', payload_ciphertext = NULL,
               lease_token = NULL, lease_expires_at = NULL,
               last_error_code = 'delivery_uncertain', updated_at = pg_catalog.now()
         WHERE status = 'dispatching' AND lease_expires_at <= pg_catalog.now()
         RETURNING challenge_id
    )
    UPDATE public.otp_challenges c
       SET delivery_status = 'uncertain',
           delivery_attempted_at = COALESCE(c.delivery_attempted_at, pg_catalog.now()),
           consumed_at = COALESCE(c.consumed_at, pg_catalog.now())
      FROM stale_dispatch s
     WHERE c.id = s.challenge_id AND c.delivery_status = 'pending';
    GET DIAGNOSTICS v_uncertain = ROW_COUNT;

    WITH expired AS (
        UPDATE public.otp_email_outbox o
           SET status = 'failed', payload_ciphertext = NULL,
               lease_token = NULL, lease_expires_at = NULL,
               last_error_code = CASE
                   WHEN c.expires_at <= pg_catalog.now() THEN 'expired'
                   ELSE 'attempts_exhausted'
               END,
               updated_at = pg_catalog.now()
          FROM public.otp_challenges c
         WHERE c.id = o.challenge_id
           AND (c.expires_at <= pg_catalog.now() OR o.attempts >= 8)
           AND o.status IN ('pending', 'processing')
         RETURNING o.challenge_id
    )
    UPDATE public.otp_challenges c
       SET delivery_status = 'failed',
           delivery_attempted_at = COALESCE(c.delivery_attempted_at, pg_catalog.now()),
           consumed_at = COALESCE(c.consumed_at, pg_catalog.now())
      FROM expired e
     WHERE c.id = e.challenge_id AND c.delivery_status = 'pending';
    GET DIAGNOSTICS v_failed = ROW_COUNT;

    RETURN QUERY SELECT v_uncertain, v_failed;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_otp_outbox_claim_one()
RETURNS TABLE(
    challenge_id uuid,
    payload_ciphertext text,
    lease_token uuid,
    attempts integer
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    RETURN QUERY
    WITH due AS (
        SELECT o.challenge_id
          FROM public.otp_email_outbox o
          JOIN public.otp_challenges c ON c.id = o.challenge_id
         WHERE (
                (o.status = 'pending' AND o.available_at <= pg_catalog.now())
                OR
                (o.status = 'processing' AND o.lease_expires_at <= pg_catalog.now())
         )
           AND c.expires_at > pg_catalog.now()
           AND c.consumed_at IS NULL
           AND c.delivery_status = 'pending'
           AND o.attempts < 8
         ORDER BY o.available_at, o.created_at
         FOR UPDATE OF o SKIP LOCKED
         LIMIT 1
    )
    UPDATE public.otp_email_outbox o
       SET status = 'processing',
           attempts = o.attempts + 1,
           lease_token = pg_catalog.gen_random_uuid(),
           lease_expires_at = pg_catalog.now() + INTERVAL '240 seconds',
           updated_at = pg_catalog.now()
      FROM due
     WHERE o.challenge_id = due.challenge_id
    RETURNING o.challenge_id, o.payload_ciphertext, o.lease_token, o.attempts;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_otp_outbox_mark_dispatching(
    p_challenge_id uuid, p_lease_token uuid, p_attempts integer
)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    affected integer;
    valid_challenge uuid;
BEGIN
    IF p_challenge_id IS NULL OR p_lease_token IS NULL
       OR p_attempts IS NULL OR p_attempts < 1 OR p_attempts > 8 THEN
        RETURN false;
    END IF;

    -- Lock order is always outbox first, challenge second. This serializes
    -- dispatch authorization against concurrent OTP consumption/revocation.
    UPDATE public.otp_email_outbox
       SET status = 'dispatching', updated_at = pg_catalog.now()
     WHERE challenge_id = p_challenge_id AND status = 'processing'
       AND lease_token = p_lease_token AND lease_expires_at > pg_catalog.now()
       AND attempts = p_attempts;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 1 THEN RETURN false; END IF;

    SELECT c.id INTO valid_challenge
      FROM public.otp_challenges AS c
     WHERE c.id = p_challenge_id AND c.expires_at > pg_catalog.now()
       AND c.consumed_at IS NULL AND c.delivery_status = 'pending'
     FOR UPDATE OF c;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'OTP challenge is no longer dispatchable';
    END IF;

    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_otp_outbox_mark_sent(
    p_challenge_id uuid, p_lease_token uuid, p_attempts integer,
    p_provider_reference text
)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE affected integer;
BEGIN
    IF p_challenge_id IS NULL OR p_lease_token IS NULL
       OR p_attempts IS NULL OR p_attempts < 1 OR p_attempts > 8
       OR p_provider_reference IS NULL
       OR pg_catalog.length(pg_catalog.btrim(p_provider_reference)) < 1
       OR pg_catalog.length(p_provider_reference) > 160 THEN
        RETURN false;
    END IF;

    UPDATE public.otp_email_outbox
       SET status = 'sent', payload_ciphertext = NULL,
           provider_reference = pg_catalog.btrim(p_provider_reference),
           lease_token = NULL, lease_expires_at = NULL,
           last_error_code = NULL, sent_at = pg_catalog.now(),
           updated_at = pg_catalog.now()
     WHERE challenge_id = p_challenge_id AND status = 'dispatching'
       AND lease_token = p_lease_token AND lease_expires_at > pg_catalog.now()
       AND attempts = p_attempts;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 1 THEN RETURN false; END IF;

    UPDATE public.otp_challenges
       SET delivery_attempted_at = COALESCE(delivery_attempted_at, pg_catalog.now()),
           delivery_status = 'sent', sent_at = pg_catalog.now(),
           provider_reference = pg_catalog.btrim(p_provider_reference),
           consumed_at = consumed_at,
           resend_after = pg_catalog.now() + INTERVAL '60 seconds'
     WHERE id = p_challenge_id AND delivery_status = 'pending'
       AND consumed_at IS NULL AND expires_at > pg_catalog.now();
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 1 THEN
        RAISE EXCEPTION 'OTP challenge could not be finalized as sent';
    END IF;
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_otp_outbox_mark_failure(
    p_challenge_id uuid, p_lease_token uuid, p_attempts integer,
    p_terminal boolean, p_error_code text
)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    affected integer;
    terminal boolean;
    safe_error text;
BEGIN
    IF p_challenge_id IS NULL OR p_lease_token IS NULL
       OR p_attempts IS NULL OR p_attempts < 1 OR p_attempts > 8
       OR p_terminal IS NULL THEN
        RETURN false;
    END IF;
    terminal := p_terminal OR p_attempts >= 8;
    safe_error := CASE
        WHEN p_error_code IN ('configuration', 'provider_transient', 'payload_invalid', 'expired')
        THEN p_error_code
        ELSE 'provider_transient'
    END;

    UPDATE public.otp_email_outbox o
       SET status = CASE WHEN terminal THEN 'failed' ELSE 'pending' END,
           payload_ciphertext = CASE WHEN terminal THEN NULL ELSE payload_ciphertext END,
           available_at = CASE WHEN terminal THEN o.available_at
               ELSE pg_catalog.now() + (LEAST(900, (2 ^ LEAST(o.attempts, 9))::integer) * INTERVAL '1 second') END,
           lease_token = NULL, lease_expires_at = NULL,
           last_error_code = safe_error, updated_at = pg_catalog.now()
     WHERE o.challenge_id = p_challenge_id
       AND o.status IN ('processing', 'dispatching')
       AND o.lease_token = p_lease_token
       AND o.lease_expires_at > pg_catalog.now()
       AND o.attempts = p_attempts;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 1 THEN RETURN false; END IF;

    IF terminal THEN
        UPDATE public.otp_challenges
           SET delivery_attempted_at = COALESCE(delivery_attempted_at, pg_catalog.now()),
               delivery_status = 'failed', consumed_at = pg_catalog.now()
         WHERE id = p_challenge_id AND delivery_status = 'pending'
           AND consumed_at IS NULL AND expires_at > pg_catalog.now();
        GET DIAGNOSTICS affected = ROW_COUNT;
        IF affected <> 1 THEN
            RAISE EXCEPTION 'OTP challenge could not be finalized as failed';
        END IF;
    END IF;
    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION public.kappa_otp_outbox_mark_uncertain(
    p_challenge_id uuid, p_lease_token uuid, p_attempts integer
)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE affected integer;
BEGIN
    IF p_challenge_id IS NULL OR p_lease_token IS NULL
       OR p_attempts IS NULL OR p_attempts < 1 OR p_attempts > 8 THEN
        RETURN false;
    END IF;
    UPDATE public.otp_email_outbox
       SET status = 'uncertain', payload_ciphertext = NULL,
           lease_token = NULL, lease_expires_at = NULL,
           last_error_code = 'delivery_uncertain', updated_at = pg_catalog.now()
     WHERE challenge_id = p_challenge_id AND status = 'dispatching'
       AND lease_token = p_lease_token AND lease_expires_at > pg_catalog.now()
       AND attempts = p_attempts;
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 1 THEN RETURN false; END IF;

    UPDATE public.otp_challenges
       SET delivery_attempted_at = COALESCE(delivery_attempted_at, pg_catalog.now()),
           delivery_status = 'uncertain', consumed_at = pg_catalog.now()
     WHERE id = p_challenge_id AND delivery_status = 'pending'
       AND consumed_at IS NULL AND expires_at > pg_catalog.now();
    GET DIAGNOSTICS affected = ROW_COUNT;
    IF affected <> 1 THEN
        RAISE EXCEPTION 'OTP challenge could not be finalized as uncertain';
    END IF;
    RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.kappa_otp_outbox_expire_due() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_otp_outbox_claim_one() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_otp_outbox_mark_dispatching(uuid, uuid, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_otp_outbox_mark_sent(uuid, uuid, integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_otp_outbox_mark_failure(uuid, uuid, integer, boolean, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.kappa_otp_outbox_mark_uncertain(uuid, uuid, integer) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.kappa_otp_outbox_expire_due() TO kappa_otp_outbox_worker_executor;
GRANT EXECUTE ON FUNCTION public.kappa_otp_outbox_claim_one() TO kappa_otp_outbox_worker_executor;
GRANT EXECUTE ON FUNCTION public.kappa_otp_outbox_mark_dispatching(uuid, uuid, integer) TO kappa_otp_outbox_worker_executor;
GRANT EXECUTE ON FUNCTION public.kappa_otp_outbox_mark_sent(uuid, uuid, integer, text) TO kappa_otp_outbox_worker_executor;
GRANT EXECUTE ON FUNCTION public.kappa_otp_outbox_mark_failure(uuid, uuid, integer, boolean, text) TO kappa_otp_outbox_worker_executor;
GRANT EXECUTE ON FUNCTION public.kappa_otp_outbox_mark_uncertain(uuid, uuid, integer) TO kappa_otp_outbox_worker_executor;

DO $$
DECLARE
    owner_role text := 'kappa_otp_outbox_capability_owner';
    executor_role text := 'kappa_otp_outbox_worker_executor';
    item text;
BEGIN
    FOREACH item IN ARRAY ARRAY['otp_email_outbox', 'otp_challenges']
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = item
        ) THEN
            RAISE EXCEPTION 'Required table public.% does not exist', item;
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
         WHERE rolname = owner_role AND NOT rolsuper AND NOT rolcanlogin
           AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication
           AND NOT rolinherit AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'Required safe NOLOGIN capability owner role % is missing', owner_role;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
         WHERE rolname = executor_role AND NOT rolsuper AND NOT rolcanlogin
           AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication
           AND NOT rolinherit AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'Required safe NOLOGIN executor role % is missing', executor_role;
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
        RAISE EXCEPTION 'Capability owner % has an unexpected role membership', owner_role;
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
        RAISE EXCEPTION 'Executor % has an unexpected role membership', executor_role;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname IN ('otp_email_outbox', 'otp_challenges')
          AND c.relowner = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = owner_role)
    ) THEN
        RAISE EXCEPTION 'Capability owner must not own protected OTP tables';
    END IF;
END;
$$;

GRANT USAGE ON SCHEMA public TO kappa_otp_outbox_capability_owner, kappa_otp_outbox_worker_executor;
REVOKE ALL ON public.otp_email_outbox, public.otp_challenges
    FROM kappa_otp_outbox_capability_owner;

GRANT SELECT (challenge_id, payload_ciphertext, status, attempts, available_at,
              lease_token, lease_expires_at, created_at),
      UPDATE (status, attempts, available_at, payload_ciphertext, lease_token,
              lease_expires_at, last_error_code, provider_reference, sent_at, updated_at)
ON public.otp_email_outbox TO kappa_otp_outbox_capability_owner;

GRANT SELECT (id, expires_at, consumed_at, delivery_status, delivery_attempted_at),
      UPDATE (delivery_attempted_at, delivery_status, sent_at, provider_reference,
              consumed_at, resend_after)
ON public.otp_challenges TO kappa_otp_outbox_capability_owner;

-- Transfer ownership with temporary membership and schema CREATE, then
-- revoke both temporary grants. Neon retains only its non-inheritable/non-settable
-- platform membership from neondb_owner to the capability role.
DO $$
DECLARE
    owner_role text := 'kappa_otp_outbox_capability_owner';
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
        'public.kappa_otp_outbox_expire_due()',
        'public.kappa_otp_outbox_claim_one()',
        'public.kappa_otp_outbox_mark_dispatching(uuid,uuid,integer)',
        'public.kappa_otp_outbox_mark_sent(uuid,uuid,integer,text)',
        'public.kappa_otp_outbox_mark_failure(uuid,uuid,integer,boolean,text)',
        'public.kappa_otp_outbox_mark_uncertain(uuid,uuid,integer)'
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

