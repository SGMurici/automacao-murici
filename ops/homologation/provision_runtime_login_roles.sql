-- KAPPA runtime login roles — HOMOLOGATION ONLY
-- Target used for the initial provision: Neon project sweet-dust-48417314,
-- disposable branch br-delicate-snow-b6qpdscm (not production/default).
--
-- This script creates non-admin LOGIN roles without setting passwords and
-- without granting table privileges, function EXECUTE, or memberships.
-- Do not run against production or a persistent/customer-data branch.
-- Credentials and workload memberships are intentionally deferred until
-- each workload's capability contract and negative privilege tests are ready.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'kappa_web_runtime_login') THEN
        CREATE ROLE kappa_web_runtime_login
            LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'kappa_scheduler_runtime_login') THEN
        CREATE ROLE kappa_scheduler_runtime_login
            LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'kappa_otp_worker_runtime_login') THEN
        CREATE ROLE kappa_otp_worker_runtime_login
            LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'kappa_analytics_runtime_login') THEN
        CREATE ROLE kappa_analytics_runtime_login
            LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
END
$$;

COMMENT ON ROLE kappa_web_runtime_login IS
    'Homologation runtime login. No direct table privileges or capability memberships until API capability contract is frozen.';
COMMENT ON ROLE kappa_scheduler_runtime_login IS
    'Homologation runtime login. No direct table privileges or capability memberships until scheduler capability contract is frozen.';
COMMENT ON ROLE kappa_otp_worker_runtime_login IS
    'Homologation runtime login. No direct table privileges or capability memberships until OTP worker capability contract is frozen.';
COMMENT ON ROLE kappa_analytics_runtime_login IS
    'Homologation runtime login. No direct table privileges or capability memberships until analytics capability contract is frozen.';

-- Expected postcondition: all four roles have LOGIN=true and all admin
-- attributes false. No passwords, role memberships, direct table grants,
-- sequence grants, or function EXECUTE grants are created by this script.
SELECT rolname, rolcanlogin, rolinherit, rolsuper, rolcreatedb,
       rolcreaterole, rolreplication, rolbypassrls
FROM pg_catalog.pg_roles
WHERE rolname IN (
    'kappa_web_runtime_login',
    'kappa_scheduler_runtime_login',
    'kappa_otp_worker_runtime_login',
    'kappa_analytics_runtime_login'
)
ORDER BY rolname;
