"""Shared fixtures for the my-finance-ai test suite."""

import base64

import pytest

from my_finance_ai.config import Settings

# Fixed, deterministic 32-byte url-safe base64 key (valid Fernet key).
TEST_FERNET_KEY = base64.urlsafe_b64encode(
    b"my_finance_ai_test_fernet_key_32"
).decode()

SECRET_VALUES = {
    "DB_PASSWORD": "db-password-test-value",
    "FERNET_KEY": TEST_FERNET_KEY,
    "AI_JWT_SECRET": "ai-jwt-secret-test-value",
    "GOOGLE_API_KEY": "google-api-key-test-value",
}

VALID_ENV = {
    "DB_HOST": "db",
    "DB_PORT": "5432",
    "DB_NAME": "finance",
    "DB_USER": "my_finance_ai",
    "AGENT_MODEL": "gemini-test-model",
    **SECRET_VALUES,
}


@pytest.fixture
def valid_env(monkeypatch):
    """Environment with every required variable set and no optional one."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)
    return dict(VALID_ENV)
