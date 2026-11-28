-- audit-sink baseline (task 1.5). Runs as the `audit` role in the `audit` schema.
-- Creates the tables of the `audit` schema that no domain task owns; every table is tenant-scoped through the
-- shared function of task 1.3 (forced row-level security, policy tenant_isolation). Domain tables come with the
-- context's own task. All data is fictional.

-- Insert-only: the audit_app role has INSERT and SELECT only (default privileges from bootstrap.sql).
-- The hash chain (recordHash over prevRecordHash and the canonical bytes) is computed by task 14.1.
CREATE TABLE audit.audit_record (
    id               bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id        uuid        NOT NULL,
    event_id         uuid        NOT NULL UNIQUE,
    actor            jsonb,
    resource_id      text,
    action           text        NOT NULL,
    occurred_at      timestamptz NOT NULL,
    trace_id         text        NOT NULL,
    prev_record_hash text        CHECK (prev_record_hash ~ '^[0-9a-f]{64}$'),
    record_hash      text        NOT NULL CHECK (record_hash ~ '^[0-9a-f]{64}$'),
    received_at      timestamptz NOT NULL DEFAULT now()
);
SELECT platform.enable_tenant_rls('audit.audit_record');
