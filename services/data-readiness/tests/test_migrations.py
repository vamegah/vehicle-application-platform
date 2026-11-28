"""Task 1.5: Alembic applies the data-readiness migrations to an empty PostgreSQL as the data_readiness role.

Starts the PostgreSQL image pinned in platform/docker-compose.yml with Testcontainers, runs the same bootstrap as
compose (platform/postgres/bootstrap/bootstrap.sql), runs `alembic upgrade head`, and checks the tables, forced
row-level security, ownership, and the version table location. Needs Docker; nothing is skipped.
"""
from __future__ import annotations

import os
import re
import secrets
import time
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from testcontainers.core.container import DockerContainer

SERVICE = Path(__file__).resolve().parents[1]
REPO = SERVICE.parents[1]
PLATFORM = REPO / "platform"
LOGIN_ROLES = ("data_readiness", "legacy_integration", "integration", "configuration", "release", "audit", "audit_app")
SCHEMA = "data_readiness"
BASELINE_TABLES = {"outbox", "inbox_event"}


def compose_postgres_image() -> str:
    compose = (PLATFORM / "docker-compose.yml").read_text(encoding="utf-8")
    m = re.search(r"(?m)^  postgres:\s*\n\s+image:\s*(\S+)", compose)
    assert m, "no postgres image in platform/docker-compose.yml"
    return m.group(1)


@pytest.fixture(scope="module")
def database():
    credentials = {role: secrets.token_hex(16) for role in LOGIN_ROLES}
    superuser_credential = secrets.token_hex(16)
    container = (
        DockerContainer(compose_postgres_image())
        .with_env("POSTGRES_DB", "autoreliance")
        .with_env("POSTGRES_USER", "postgres")
        .with_env("POSTGRES_PASSWORD", superuser_credential)
        .with_volume_mapping(str(PLATFORM / "postgres" / "bootstrap"), "/bootstrap", "ro")
        .with_exposed_ports(5432)
    )
    container.start()
    try:
        deadline = time.monotonic() + 120
        while container.exec(["pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "autoreliance"]).exit_code != 0:
            assert time.monotonic() < deadline, "PostgreSQL did not become ready"
            time.sleep(1)
        cmd = ["psql", "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-q", "-h", "127.0.0.1", "-U", "postgres", "-d", "autoreliance"]
        for role, value in credentials.items():
            cmd += ["-v", f"{role}_password={value}"]
        cmd += ["-f", "/bootstrap/bootstrap.sql"]
        result = container.exec(cmd)
        assert result.exit_code == 0, result.output.decode(errors="replace")
        host, port = container.get_container_host_ip(), int(container.get_exposed_port(5432))
        yield {"host": host, "port": port, "credentials": credentials}
    finally:
        container.stop()


def alembic_upgrade(db: dict, role_credential: str) -> None:
    os.environ["DATA_READINESS_DB_URL"] = f"postgresql+psycopg://{db['host']}:{db['port']}/autoreliance"
    os.environ["DATA_READINESS_DB_PASSWORD"] = role_credential
    try:
        command.upgrade(Config(str(SERVICE / "alembic.ini")), "head")
    finally:
        os.environ.pop("DATA_READINESS_DB_URL", None)
        os.environ.pop("DATA_READINESS_DB_PASSWORD", None)


def scalar(conn: psycopg.Connection, sql: str):
    return conn.execute(sql).fetchone()[0]


def connect(db: dict, role: str) -> psycopg.Connection:
    return psycopg.connect(host=db["host"], port=db["port"], dbname="autoreliance", user=role,
                           password=db["credentials"][role], autocommit=True)


@pytest.fixture(scope="module")
def migrated(database):
    alembic_upgrade(database, database["credentials"][SCHEMA])
    return database


def test_alembic_applies_the_baseline_to_an_empty_database(migrated):
    with connect(migrated, SCHEMA) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind = 'r'", (SCHEMA,))}
        assert tables == BASELINE_TABLES | {"alembic_version"}
        assert scalar(conn, f"SELECT version_num FROM {SCHEMA}.alembic_version") == "0001_baseline"


def test_version_table_is_only_in_the_context_schema(migrated):
    with connect(migrated, SCHEMA) as conn:
        schemas = {r[0] for r in conn.execute(
            "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relname = 'alembic_version'")}
        assert schemas == {SCHEMA}


def test_baseline_tables_have_forced_rls_and_are_owned_by_the_role(migrated):
    with connect(migrated, SCHEMA) as conn:
        for table in sorted(BASELINE_TABLES):
            row = conn.execute(
                "SELECT c.relrowsecurity, c.relforcerowsecurity, pg_get_userbyid(c.relowner), "
                "(SELECT count(*) FROM pg_policies p WHERE p.schemaname = n.nspname AND p.tablename = c.relname "
                " AND p.policyname = 'tenant_isolation'), "
                "(SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'tenant_id') "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relname = %s",
                (SCHEMA, table)).fetchone()
            assert row == (True, True, SCHEMA, 1, "uuid"), (table, row)
            assert scalar(conn, f"SELECT count(*) FROM {SCHEMA}.{table}") == 0, "zero rows without a tenant"


def test_upgrade_again_is_a_no_op(migrated):
    alembic_upgrade(migrated, migrated["credentials"][SCHEMA])
    with connect(migrated, SCHEMA) as conn:
        assert scalar(conn, f"SELECT count(*) FROM {SCHEMA}.alembic_version") == 1


def test_another_context_role_cannot_run_the_data_readiness_migrations(migrated):
    # The URL never names the role; env.py always connects as data_readiness, so another role's credential fails.
    with pytest.raises(Exception):
        alembic_upgrade(migrated, migrated["credentials"]["legacy_integration"])


def test_a_url_with_credentials_is_refused(migrated, monkeypatch):
    monkeypatch.setenv("DATA_READINESS_DB_URL", f"postgresql+psycopg://legacy_integration@{migrated['host']}:{migrated['port']}/autoreliance")
    monkeypatch.setenv("DATA_READINESS_DB_PASSWORD", migrated["credentials"]["legacy_integration"])
    with pytest.raises(RuntimeError, match="must not carry credentials"):
        command.upgrade(Config(str(SERVICE / "alembic.ini")), "head")
