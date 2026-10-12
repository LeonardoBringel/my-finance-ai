"""Read-only engine and schema revision check (FND-08, FND-09, FND-16, FND-17)."""

from contextlib import contextmanager

import psycopg
import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError, ProgrammingError

from my_finance_ai.config import Settings
from my_finance_ai.data.db import (
    DatabaseUnavailableError,
    SchemaUnreadableError,
    UnsupportedSchemaError,
    check_schema,
    create_db_engine,
    engine_kwargs,
    read_schema_revisions,
)

READ_ONLY_OPTION = "-c default_transaction_read_only=on"


@pytest.fixture
def settings(valid_env, monkeypatch):
    monkeypatch.setenv("DB_POOL_SIZE", "7")
    return Settings(_env_file=None)


# FND-16, FND-08, FND-17


def test_engine_kwargs_enable_read_only_timeout_and_fixed_pool(settings):
    kwargs = engine_kwargs(settings)

    assert READ_ONLY_OPTION in kwargs["connect_args"]["options"]
    assert kwargs["connect_args"]["connect_timeout"] == 2
    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 0


def test_engine_pool_matches_db_pool_size_without_overflow(settings):
    engine = create_db_engine(settings)

    assert engine.pool.size() == 7
    assert engine.pool._max_overflow == 0


class _ConnectAttempt(Exception):
    pass


def test_engine_connections_are_opened_read_only(settings):
    engine = create_db_engine(settings)
    captured = {}

    @event.listens_for(engine, "do_connect")
    def capture(dialect, conn_rec, cargs, cparams):
        captured.update(cparams)
        raise _ConnectAttempt  # stop before touching the network

    with pytest.raises(_ConnectAttempt):
        engine.connect()

    assert READ_ONLY_OPTION in captured["options"]
    assert captured["connect_timeout"] == 2


# FND-09 and the multi-row edge case


@pytest.mark.parametrize("revisions", [["0009"], ["0009", "0009"]])
def test_check_schema_accepts_supported_revisions(revisions):
    assert check_schema(revisions) is None


@pytest.mark.parametrize("revisions", [[], ["0010"], ["0009", "0010"]])
def test_check_schema_rejects_unsupported_revisions(revisions):
    with pytest.raises(UnsupportedSchemaError) as exc_info:
        check_schema(revisions)

    assert exc_info.value.revisions == revisions


# FND-08, FND-09 and the missing-grant edge case


class _FakeConnection:
    def __init__(self, error):
        self._error = error

    def execute(self, *args, **kwargs):
        raise self._error


class _FakeEngine:
    def __init__(self, error, on):
        self._error = error
        self._on = on

    @contextmanager
    def connect(self):
        if self._on == "connect":
            raise self._error
        yield _FakeConnection(self._error)


def _operational_error():
    return OperationalError(
        "SELECT version_num FROM alembic_version",
        {},
        psycopg.OperationalError("connection timeout expired"),
    )


@pytest.mark.parametrize("on", ["connect", "execute"])
def test_operational_error_means_database_unavailable(on):
    engine = _FakeEngine(_operational_error(), on=on)

    with pytest.raises(DatabaseUnavailableError):
        read_schema_revisions(engine)


def test_permission_denied_means_schema_unreadable():
    error = ProgrammingError(
        "SELECT version_num FROM alembic_version",
        {},
        psycopg.errors.InsufficientPrivilege(
            "permission denied for table alembic_version"
        ),
    )
    engine = _FakeEngine(error, on="execute")

    with pytest.raises(SchemaUnreadableError) as exc_info:
        read_schema_revisions(engine)

    assert "permission denied" in exc_info.value.reason
