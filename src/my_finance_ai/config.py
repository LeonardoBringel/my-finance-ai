"""Application settings, validated once at boot."""

import binascii
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_FIELDS = (
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "FERNET_KEY",
    "AI_JWT_SECRET",
    "GOOGLE_API_KEY",
    "AGENT_MODEL",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", hide_input_in_errors=True, extra="ignore"
    )

    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: SecretStr
    FERNET_KEY: SecretStr
    AI_JWT_SECRET: SecretStr
    GOOGLE_API_KEY: SecretStr
    AGENT_MODEL: str

    AI_JWT_ISSUER: str = "my-finance"
    AI_JWT_AUDIENCE: str = "my-finance-ai"
    AGENT_MAX_LLM_CALLS: int = Field(10, ge=1, le=50)
    CHAT_TIMEOUT_SECONDS: int = Field(60, ge=5, le=300)
    SESSION_TTL_MINUTES: int = Field(30, ge=1, le=1440)
    MAX_SESSIONS_PER_USER: int = Field(5, ge=1, le=50)
    MAX_MESSAGE_CHARS: int = Field(2000, ge=1, le=10000)
    RATE_LIMIT_PER_USER: int = Field(30, ge=1, le=1000)
    DB_POOL_SIZE: int = Field(5, ge=1, le=20)
    TRACING_ENABLED: bool = False
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: SecretStr | None = None

    @field_validator(*REQUIRED_FIELDS, mode="before")
    @classmethod
    def _reject_blank(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("não pode ser vazia")
        return value

    @field_validator("FERNET_KEY")
    @classmethod
    def _check_fernet_key(cls, value: SecretStr) -> SecretStr:
        try:
            Fernet(value.get_secret_value())
        except (ValueError, TypeError, binascii.Error):
            raise ValueError("não é uma chave Fernet válida") from None
        return value


def get_settings() -> Settings:
    return Settings()


def _range_message(name: str) -> str:
    metadata = Settings.model_fields[name].metadata
    low = next(m.ge for m in metadata if hasattr(m, "ge"))
    high = next(m.le for m in metadata if hasattr(m, "le"))
    return f"deve estar no intervalo {low}-{high}"


def format_settings_error(exc: ValidationError) -> str:
    """One line per invalid variable, never including the input value."""
    lines = []
    for error in exc.errors(include_input=False, include_url=False):
        name = str(error["loc"][0])
        if error["type"] == "missing":
            reason = "variável obrigatória não definida"
        elif error["type"] == "value_error":
            reason = str(error["ctx"]["error"])
        elif error["type"] in ("greater_than_equal", "less_than_equal"):
            reason = _range_message(name)
        else:
            reason = error["msg"]
        lines.append(f"{name}: {reason}")
    return "\n".join(lines)
