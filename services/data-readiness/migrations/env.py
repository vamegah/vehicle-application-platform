"""Alembic migration environment of the data-readiness context (task 1.5).

Scoped to the context's own schema and role: it connects as the `data_readiness` login role, refuses any other
role, keeps the version table in the `data_readiness` schema, and sets the search path to that schema. The
database location and the credential come from the environment, never from alembic.ini:

    DATA_READINESS_DB_URL       e.g. postgresql+psycopg://127.0.0.1:5432/autoreliance (no credentials)
    DATA_READINESS_DB_PASSWORD  the credential of the data_readiness role
"""
from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import URL

SCHEMA = "data_readiness"
ROLE = "data_readiness"


def database_url() -> URL:
    raw = os.environ.get("DATA_READINESS_DB_URL")
    secret = os.environ.get("DATA_READINESS_DB_PASSWORD")
    if not raw or not secret:
        raise RuntimeError("set DATA_READINESS_DB_URL (no credentials) and DATA_READINESS_DB_PASSWORD")
    url = make_url(raw)
    if url.username not in (None, ROLE) or url.password is not None:
        raise RuntimeError("DATA_READINESS_DB_URL must not carry credentials; the role is always data_readiness")
    return url.set(drivername="postgresql+psycopg", username=ROLE, password=secret)


def run_migrations_online() -> None:
    engine = create_engine(database_url())
    with engine.connect() as connection:
        user = connection.execute(text("SELECT current_user")).scalar_one()
        if user != ROLE:
            raise RuntimeError(f"Alembic must run as the {ROLE} role, not {user}")
        connection.execute(text(f"SET search_path TO {SCHEMA}, public"))
        connection.commit()
        context.configure(
            connection=connection,
            version_table="alembic_version",
            version_table_schema=SCHEMA,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline (SQL script) mode is not used; run `alembic upgrade head` against the database")
run_migrations_online()
