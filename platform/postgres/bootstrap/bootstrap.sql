-- PostgreSQL bootstrap (task 1.3): schemas, per-context roles, and the row-level security baseline.
-- Run with psql as a superuser in the platform database. Idempotent: safe to run again.
--
--   psql -v ON_ERROR_STOP=1 \
--        -v data_readiness_password=... -v legacy_integration_password=... -v integration_password=... \
--        -v configuration_password=... -v release_password=... -v audit_password=... -v audit_app_password=... \
--        -f bootstrap.sql
--
-- One schema and one login role per bounded context (Req 21.1). The role has the schema's name and owns it, so
-- the context's migrations (Flyway or Alembic, task 1.5) and its process run as that role and nothing else.
-- No role holds any privilege on another context's schema, including contexts packaged in the same deployable
-- (data-platform: data_readiness + legacy_integration; integration-config: integration + configuration).
-- The audit schema also has the application role audit_app with INSERT and SELECT only (Req 16.4).
-- The schema `platform` holds only the shared RLS function; it has no tables.

\set ON_ERROR_STOP on

-- Login roles. Passwords come from psql variables (platform/.env locally, Vault in deployed environments).
SELECT format(
  'DO $do$ BEGIN
     IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %1$L) THEN
       CREATE ROLE %1$I LOGIN;
     END IF;
   END $do$;', r) AS stmt
FROM unnest(ARRAY['data_readiness', 'legacy_integration', 'integration', 'configuration', 'release', 'audit', 'audit_app']) AS r
\gexec

ALTER ROLE data_readiness     LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'data_readiness_password';
ALTER ROLE legacy_integration LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'legacy_integration_password';
ALTER ROLE integration        LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'integration_password';
ALTER ROLE configuration      LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'configuration_password';
ALTER ROLE release            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'release_password';
ALTER ROLE audit              LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'audit_password';
ALTER ROLE audit_app          LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD :'audit_app_password';

-- Database: only the platform roles may connect; nobody else gets default privileges.
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), r)
FROM unnest(ARRAY['data_readiness', 'legacy_integration', 'integration', 'configuration', 'release', 'audit', 'audit_app']) AS r
\gexec

-- The public schema holds extensions only (pgvector). Nobody may create objects in it.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- One schema per context, owned by the context role, closed to everyone else.
CREATE SCHEMA IF NOT EXISTS data_readiness     AUTHORIZATION data_readiness;
CREATE SCHEMA IF NOT EXISTS legacy_integration AUTHORIZATION legacy_integration;
CREATE SCHEMA IF NOT EXISTS integration        AUTHORIZATION integration;
CREATE SCHEMA IF NOT EXISTS configuration      AUTHORIZATION configuration;
CREATE SCHEMA IF NOT EXISTS release            AUTHORIZATION release;
CREATE SCHEMA IF NOT EXISTS audit              AUTHORIZATION audit;
SELECT format('ALTER SCHEMA %1$I OWNER TO %1$I', s), format('REVOKE ALL ON SCHEMA %I FROM PUBLIC', s)
FROM unnest(ARRAY['data_readiness', 'legacy_integration', 'integration', 'configuration', 'release', 'audit']) AS s
\gexec

-- Each role resolves unqualified names in its own schema first.
SELECT format('ALTER ROLE %1$I SET search_path = %1$I, public', r)
FROM unnest(ARRAY['data_readiness', 'legacy_integration', 'integration', 'configuration', 'release', 'audit']) AS r
\gexec
ALTER ROLE audit_app SET search_path = audit, public;

-- Audit application role: INSERT and SELECT only, on every table the audit role creates (now or later).
GRANT USAGE ON SCHEMA audit TO audit_app;
ALTER DEFAULT PRIVILEGES FOR ROLE audit IN SCHEMA audit REVOKE ALL ON TABLES FROM audit_app;
ALTER DEFAULT PRIVILEGES FOR ROLE audit IN SCHEMA audit GRANT SELECT, INSERT ON TABLES TO audit_app;
ALTER DEFAULT PRIVILEGES FOR ROLE audit IN SCHEMA audit GRANT USAGE ON SEQUENCES TO audit_app;

-- Shared RLS baseline, callable from Flyway (Java) and Alembic (Python) migrations:
--   SELECT platform.enable_tenant_rls('<schema>.<table>');
-- The table must have a `tenant_id uuid` column. The function enables and forces row-level security (so the
-- owning role is subject to it too) and (re)creates the policy `tenant_isolation`. NULLIF maps the empty string,
-- which PostgreSQL leaves in a pooled session after a `SET LOCAL app.tenant_id` transaction ends, to NULL: a query
-- with no tenant in context then returns zero rows instead of failing on ''::uuid (Req 15.5).
CREATE SCHEMA IF NOT EXISTS platform;
REVOKE ALL ON SCHEMA platform FROM PUBLIC;

CREATE OR REPLACE FUNCTION platform.enable_tenant_rls(target regclass)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $fn$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_attribute
    WHERE attrelid = target AND attname = 'tenant_id' AND atttypid = 'uuid'::regtype
      AND attnum > 0 AND NOT attisdropped
  ) THEN
    RAISE EXCEPTION 'table % has no tenant_id uuid column; every tenant-scoped table needs one', target
      USING ERRCODE = 'invalid_table_definition';
  END IF;
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', target);
  EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', target);
  EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %s', target);
  EXECUTE format(
    'CREATE POLICY tenant_isolation ON %s '
    'USING (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid) '
    'WITH CHECK (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid)', target);
END
$fn$;

REVOKE ALL ON FUNCTION platform.enable_tenant_rls(regclass) FROM PUBLIC;
SELECT format('GRANT USAGE ON SCHEMA platform TO %I', r), format('GRANT EXECUTE ON FUNCTION platform.enable_tenant_rls(regclass) TO %I', r)
FROM unnest(ARRAY['data_readiness', 'legacy_integration', 'integration', 'configuration', 'release', 'audit']) AS r
\gexec
