"""Settings validation at boot (FND-01 to FND-05)."""

import base64

import pytest
from pydantic import ValidationError

from my_finance_ai.config import Settings, format_settings_error
from tests.conftest import SECRET_VALUES

REQUIRED = [
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "FERNET_KEY",
    "AI_JWT_SECRET",
    "GOOGLE_API_KEY",
    "AGENT_MODEL",
]

RANGES = {
    "AGENT_MAX_LLM_CALLS": (1, 50),
    "CHAT_TIMEOUT_SECONDS": (5, 300),
    "SESSION_TTL_MINUTES": (1, 1440),
    "MAX_SESSIONS_PER_USER": (1, 50),
    "MAX_MESSAGE_CHARS": (1, 10000),
    "RATE_LIMIT_PER_USER": (1, 1000),
    "DB_POOL_SIZE": (1, 20),
}

DEFAULTS = {
    "AI_JWT_ISSUER": "my-finance",
    "AI_JWT_AUDIENCE": "my-finance-ai",
    "AGENT_MAX_LLM_CALLS": 10,
    "CHAT_TIMEOUT_SECONDS": 60,
    "SESSION_TTL_MINUTES": 30,
    "MAX_SESSIONS_PER_USER": 5,
    "MAX_MESSAGE_CHARS": 2000,
    "RATE_LIMIT_PER_USER": 30,
    "DB_POOL_SIZE": 5,
    "TRACING_ENABLED": False,
    "LOG_LEVEL": "INFO",
    "OTEL_EXPORTER_OTLP_ENDPOINT": None,
    "LANGFUSE_PUBLIC_KEY": None,
    "LANGFUSE_SECRET_KEY": None,
}


def _formatted_error() -> str:
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    return format_settings_error(exc_info.value)


def _assert_no_secret_values(text: str) -> None:
    for value in SECRET_VALUES.values():
        assert value not in text


# FND-01


@pytest.mark.parametrize("name", REQUIRED)
def test_missing_required_variable_is_named(valid_env, monkeypatch, name):
    monkeypatch.delenv(name)

    lines = _formatted_error().splitlines()

    assert len(lines) == 1
    assert lines[0].startswith(f"{name}: ")


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("name", REQUIRED)
def test_empty_required_variable_is_named(valid_env, monkeypatch, name, blank):
    monkeypatch.setenv(name, blank)

    lines = _formatted_error().splitlines()

    assert len(lines) == 1
    assert lines[0].startswith(f"{name}: ")


# FND-02


@pytest.mark.parametrize("name,bounds", RANGES.items())
@pytest.mark.parametrize("side", ["below", "above"])
def test_out_of_range_names_variable_and_range(
    valid_env, monkeypatch, name, bounds, side
):
    low, high = bounds
    monkeypatch.setenv(name, str(low - 1 if side == "below" else high + 1))

    lines = _formatted_error().splitlines()

    assert len(lines) == 1
    assert lines[0].startswith(f"{name}: ")
    assert f"{low}-{high}" in lines[0]


@pytest.mark.parametrize("name,bounds", RANGES.items())
@pytest.mark.parametrize("edge", [0, 1])
def test_range_edges_are_accepted(valid_env, monkeypatch, name, bounds, edge):
    monkeypatch.setenv(name, str(bounds[edge]))

    settings = Settings(_env_file=None)

    assert getattr(settings, name) == bounds[edge]


# FND-03


@pytest.mark.parametrize(
    "invalid_key",
    [
        "not-a-valid-fernet-key-value",
        base64.urlsafe_b64encode(b"sixteen-byte-key").decode(),
    ],
)
def test_invalid_fernet_key_is_named_without_value(
    valid_env, monkeypatch, invalid_key
):
    monkeypatch.setenv("FERNET_KEY", invalid_key)

    message = _formatted_error()

    assert message.startswith("FERNET_KEY: ")
    assert len(message.splitlines()) == 1
    assert invalid_key not in message


# FND-04


def test_repr_and_str_hide_secret_values(valid_env):
    settings = Settings(_env_file=None)

    _assert_no_secret_values(repr(settings))
    _assert_no_secret_values(str(settings))


@pytest.mark.parametrize(
    "name,value",
    [("DB_HOST", ""), ("AGENT_MAX_LLM_CALLS", "0"), ("LOG_LEVEL", "VERBOSE")],
)
def test_formatted_error_hides_secret_values(
    valid_env, monkeypatch, name, value
):
    monkeypatch.setenv(name, value)

    message = _formatted_error()

    assert message.startswith(f"{name}: ")
    _assert_no_secret_values(message)


@pytest.mark.parametrize("name", list(SECRET_VALUES))
def test_formatted_error_hides_rejected_secret_value(
    valid_env, monkeypatch, name
):
    # A secret that fails validation must not leak through the error either.
    monkeypatch.setenv(name, " ")
    monkeypatch.setenv("DB_POOL_SIZE", "0")

    message = _formatted_error()

    assert f"{name}: " in message
    assert "DB_POOL_SIZE: " in message
    _assert_no_secret_values(message)


# FND-05


def test_optional_variables_take_defaults(valid_env):
    settings = Settings(_env_file=None)

    assert {name: getattr(settings, name) for name in DEFAULTS} == DEFAULTS
