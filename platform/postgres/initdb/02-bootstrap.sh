#!/bin/sh
# Task 1.3: run the PostgreSQL bootstrap (schemas, per-context roles, RLS baseline) when the compose volume is
# first initialized. Passwords come from the container environment (platform/.env); nothing is printed.
# The postgres entrypoint may source this file, so it sets no shell options; psql's ON_ERROR_STOP makes a
# failure exit non-zero, which stops the entrypoint (it runs with `set -e`).
psql -v ON_ERROR_STOP=1 --no-psqlrc -q \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v data_readiness_password="$PG_DATA_READINESS_PASSWORD" \
  -v legacy_integration_password="$PG_LEGACY_INTEGRATION_PASSWORD" \
  -v integration_password="$PG_INTEGRATION_PASSWORD" \
  -v configuration_password="$PG_CONFIGURATION_PASSWORD" \
  -v release_password="$PG_RELEASE_PASSWORD" \
  -v audit_password="$PG_AUDIT_PASSWORD" \
  -v audit_app_password="$PG_AUDIT_APP_PASSWORD" \
  -f /bootstrap/bootstrap.sql
