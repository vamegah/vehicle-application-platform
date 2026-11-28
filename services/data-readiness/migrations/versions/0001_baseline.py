"""data-readiness baseline (task 1.5).

Creates the tables of the data_readiness schema that no domain task owns (outbox and inbox_event); every table is
tenant-scoped through the shared function of task 1.3 (forced row-level security, policy tenant_isolation). The
domain tables come with task 6.1. Runs as the data_readiness role in its own schema.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-28
"""
from __future__ import annotations

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE data_readiness.outbox (
            id           uuid        PRIMARY KEY,
            tenant_id    uuid        NOT NULL,
            aggregate_id text        NOT NULL,
            event_type   text        NOT NULL,
            payload      jsonb       NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            published_at timestamptz
        )
    """)
    # The relay of task 4.2 selects unpublished rows in creation order.
    op.execute("CREATE INDEX outbox_unpublished_idx ON data_readiness.outbox (created_at) WHERE published_at IS NULL")
    op.execute("SELECT platform.enable_tenant_rls('data_readiness.outbox')")
    op.execute("""
        CREATE TABLE data_readiness.inbox_event (
            event_id       uuid        PRIMARY KEY,
            tenant_id      uuid        NOT NULL,
            consumer_group text        NOT NULL,
            processed_at   timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("SELECT platform.enable_tenant_rls('data_readiness.inbox_event')")


def downgrade() -> None:
    op.execute("DROP TABLE data_readiness.inbox_event")
    op.execute("DROP TABLE data_readiness.outbox")
