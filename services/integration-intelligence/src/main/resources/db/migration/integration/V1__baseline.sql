-- integration-intelligence baseline (task 1.5). Runs as the `integration` role in the `integration` schema.
-- Creates the tables of the `integration` schema that no domain task owns; every table is tenant-scoped through the
-- shared function of task 1.3 (forced row-level security, policy tenant_isolation). Domain tables come with the
-- context's own task. All data is fictional.

CREATE TABLE integration.outbox (
    id           uuid        PRIMARY KEY,
    tenant_id    uuid        NOT NULL,
    aggregate_id text        NOT NULL,
    event_type   text        NOT NULL,
    payload      jsonb       NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);
-- The relay of task 4.2 selects unpublished rows in creation order.
CREATE INDEX outbox_unpublished_idx ON integration.outbox (created_at) WHERE published_at IS NULL;
SELECT platform.enable_tenant_rls('integration.outbox');

CREATE TABLE integration.inbox_event (
    event_id       uuid        PRIMARY KEY,
    tenant_id      uuid        NOT NULL,
    consumer_group text        NOT NULL,
    processed_at   timestamptz NOT NULL DEFAULT now()
);
SELECT platform.enable_tenant_rls('integration.inbox_event');
