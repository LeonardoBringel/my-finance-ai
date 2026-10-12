"""Read-only engine and alembic_version check."""

from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from my_finance_ai.config import Settings

SUPPORTED_SCHEMA_REVISIONS: tuple[str, ...] = ("0009",)
READY_TIMEOUT_SECONDS = 2


class DatabaseUnavailableError(Exception):
    """The database did not answer (refused, timed out, query canceled)."""


class SchemaUnreadableError(Exception):
    """alembic_version could not be read (missing table or grant)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class UnsupportedSchemaError(Exception):
    """alembic_version is empty or holds a revision this code does not know."""

    def __init__(self, revisions: list[str]) -> None:
        super().__init__(f"unsupported schema revisions: {revisions}")
        self.revisions = revisions


def engine_kwargs(settings: Settings) -> dict:
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": 0,
        "pool_pre_ping": True,
        "connect_args": {
            "connect_timeout": READY_TIMEOUT_SECONDS,
            "options": "-c default_transaction_read_only=on",
        },
    }


def create_db_engine(settings: Settings) -> Engine:
    url = URL.create(
        "postgresql+psycopg",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD.get_secret_value(),
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
    )
    return create_engine(url, **engine_kwargs(settings))


def read_schema_revisions(engine: Engine) -> list[str]:
    try:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "SET LOCAL statement_timeout = "
                    f"'{READY_TIMEOUT_SECONDS}s'"
                )
            )
            result = conn.execute(
                text("SELECT version_num FROM alembic_version")
            )
            return list(result.scalars())
    except OperationalError as exc:
        raise DatabaseUnavailableError(str(exc.orig)) from exc
    except ProgrammingError as exc:
        raise SchemaUnreadableError(str(exc.orig)) from exc


def check_schema(revisions: list[str]) -> None:
    if not revisions or any(
        revision not in SUPPORTED_SCHEMA_REVISIONS for revision in revisions
    ):
        raise UnsupportedSchemaError(revisions)
