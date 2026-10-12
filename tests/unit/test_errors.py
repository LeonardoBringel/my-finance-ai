"""Unified error format (FND-12 to FND-15)."""

import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from my_finance_ai.api.errors import ApiError, register_error_handlers


@pytest.fixture
def client():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("SELECT secret")

    @app.get("/items/{item_id}")
    def get_item(item_id: int):
        return {"item_id": item_id}

    @app.post("/only-post")
    def only_post():
        return {}

    @app.get("/api-error")
    def api_error():
        raise ApiError(503, "X", "m")

    @app.get("/conflict")
    def conflict():
        raise HTTPException(status_code=409, detail="internal detail")

    return TestClient(app, raise_server_exceptions=False)


def _assert_error_body(response, status, code, message):
    body = response.json()
    assert response.status_code == status
    assert body == {"error": {"code": code, "message": message}}


# FND-13


def test_unhandled_exception_returns_generic_500(client, caplog):
    with caplog.at_level(logging.ERROR):
        response = client.get("/boom")

    _assert_error_body(response, 500, "INTERNAL", "Erro interno.")
    assert "SELECT" not in response.text
    assert "secret" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" in caplog.text
    assert "RuntimeError: SELECT secret" in caplog.text


# FND-14


def test_invalid_parameter_returns_invalid_request(client):
    response = client.get("/items/not-a-number")

    _assert_error_body(response, 422, "INVALID_REQUEST", "Requisição inválida.")


# FND-15


def test_unknown_route_returns_not_found(client):
    response = client.get("/nao-existe")

    _assert_error_body(response, 404, "NOT_FOUND", "Recurso não encontrado.")


# FND-12


def test_wrong_method_returns_method_not_allowed(client):
    response = client.get("/only-post")

    _assert_error_body(
        response, 405, "METHOD_NOT_ALLOWED", "Método não permitido."
    )


def test_other_http_exception_uses_generic_code(client):
    response = client.get("/conflict")

    _assert_error_body(response, 409, "HTTP_ERROR", "Erro na requisição.")
    assert "internal detail" not in response.text


def test_api_error_keeps_its_status_code_and_message(client):
    response = client.get("/api-error")

    _assert_error_body(response, 503, "X", "m")
