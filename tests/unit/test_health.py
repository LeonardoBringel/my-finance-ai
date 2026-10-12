"""Liveness and readiness (FND-06 to FND-09, FND-11)."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from my_finance_ai.api.errors import register_error_handlers
from my_finance_ai.api.routes.health import get_schema_revision_reader, router
from my_finance_ai.data.db import (
    DatabaseUnavailableError,
    SchemaUnreadableError,
)

HEALTH_LOGGER = "my_finance_ai.api.routes.health"


def _client_with_reader(reader):
    # No app.state.engine on purpose: a route touching the database fails.
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_schema_revision_reader] = lambda: reader
    return TestClient(app, raise_server_exceptions=False)


def _returning(revisions):
    return lambda: list(revisions)


def _raising(error):
    def reader():
        raise error

    return reader


def _assert_unsupported_schema(response):
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "UNSUPPORTED_SCHEMA",
            "message": "Versão de schema não suportada.",
        }
    }


def _warnings(caplog):
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == HEALTH_LOGGER and record.levelno == logging.WARNING
    ]


# FND-06


def test_health_does_not_touch_the_database():
    def reader_must_not_run():
        raise AssertionError("reader called by /health")

    client = _client_with_reader(reader_must_not_run)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# FND-07 and the multi-row edge case


@pytest.mark.parametrize("revisions", [["0009"], ["0009", "0009"]])
def test_ready_with_supported_revision(revisions):
    client = _client_with_reader(_returning(revisions))

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "schema_revision": "0009"}


# FND-08


def test_ready_when_database_is_unavailable():
    client = _client_with_reader(_raising(DatabaseUnavailableError()))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "DB_UNAVAILABLE",
            "message": "Banco de dados indisponível.",
        }
    }


# FND-09 and the multi-row edge case


@pytest.mark.parametrize("revisions", [["0010"], ["0009", "0010"]])
def test_ready_with_unknown_revision_logs_it(caplog, revisions):
    client = _client_with_reader(_returning(revisions))

    with caplog.at_level(logging.WARNING, logger=HEALTH_LOGGER):
        response = client.get("/ready")

    _assert_unsupported_schema(response)
    assert any("0010" in message for message in _warnings(caplog))


def test_ready_with_empty_alembic_version(caplog):
    client = _client_with_reader(_returning([]))

    with caplog.at_level(logging.WARNING, logger=HEALTH_LOGGER):
        response = client.get("/ready")

    _assert_unsupported_schema(response)
    assert _warnings(caplog)


# FND-09, missing-grant edge case


def test_ready_without_grant_logs_permission_denied(caplog):
    error = SchemaUnreadableError("permission denied for table alembic_version")
    client = _client_with_reader(_raising(error))

    with caplog.at_level(logging.WARNING, logger=HEALTH_LOGGER):
        response = client.get("/ready")

    _assert_unsupported_schema(response)
    assert any("permission denied" in message for message in _warnings(caplog))


# FND-11


def test_health_stays_up_while_schema_is_unsupported():
    client = _client_with_reader(_returning(["0010"]))

    _assert_unsupported_schema(client.get("/ready"))
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# Edge case: the database comes back


def test_ready_recovers_without_recreating_the_app():
    calls = []

    def flaky_reader():
        calls.append(None)
        if len(calls) == 1:
            raise DatabaseUnavailableError()
        return ["0009"]

    client = _client_with_reader(flaky_reader)

    first = client.get("/ready")
    second = client.get("/ready")

    assert first.status_code == 503
    assert first.json()["error"]["code"] == "DB_UNAVAILABLE"
    assert second.status_code == 200
    assert second.json() == {"status": "ready", "schema_revision": "0009"}
