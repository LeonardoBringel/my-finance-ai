"""App factory: fail-fast boot and public health routes (FND-01, FND-03, FND-10)."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from my_finance_ai.api.routes.health import get_schema_revision_reader
from my_finance_ai.main import create_app
from tests.conftest import SECRET_VALUES


@pytest.fixture
def boot_env(valid_env, monkeypatch, tmp_path):
    # create_app() reads .env from the working directory; keep it empty.
    monkeypatch.chdir(tmp_path)
    return valid_env


def _critical_log(caplog) -> str:
    return "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.CRITICAL
    )


def _assert_no_secret_values(text: str) -> None:
    for value in SECRET_VALUES.values():
        assert value not in text


# FND-01


def test_missing_required_variable_exits_with_code_1(
    boot_env, monkeypatch, caplog
):
    monkeypatch.delenv("DB_HOST")

    with pytest.raises(SystemExit) as exc_info:
        create_app()

    assert exc_info.value.code == 1
    assert "DB_HOST" in _critical_log(caplog)
    _assert_no_secret_values(caplog.text)


# FND-03


def test_invalid_fernet_key_exits_without_printing_it(
    boot_env, monkeypatch, caplog
):
    invalid_key = "not-a-valid-fernet-key-value"
    monkeypatch.setenv("FERNET_KEY", invalid_key)

    with pytest.raises(SystemExit) as exc_info:
        create_app()

    assert exc_info.value.code == 1
    assert "FERNET_KEY" in _critical_log(caplog)
    assert invalid_key not in caplog.text
    _assert_no_secret_values(caplog.text)


# FND-10


def test_health_routes_answer_without_authorization(boot_env):
    app = create_app()
    app.dependency_overrides[get_schema_revision_reader] = lambda: (
        lambda: ["0009"]
    )

    with TestClient(app) as client:
        health = client.get("/health")
        ready = client.get("/ready")

    assert "authorization" not in health.request.headers
    assert "authorization" not in ready.request.headers
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "schema_revision": "0009"}


def test_lifespan_disposes_engine_on_shutdown(boot_env):
    app = create_app()
    disposed = []
    event.listen(
        app.state.engine, "engine_disposed", lambda conn: disposed.append(1)
    )

    with TestClient(app):
        assert disposed == []

    assert disposed == [1]
