"""Liveness (/health) and readiness (/ready), without Authorization."""

import logging
from collections.abc import Callable
from functools import partial

from fastapi import APIRouter, Depends, Request

from my_finance_ai.api.errors import ApiError
from my_finance_ai.data.db import (
    DatabaseUnavailableError,
    SchemaUnreadableError,
    UnsupportedSchemaError,
    check_schema,
    read_schema_revisions,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _unsupported_schema() -> ApiError:
    return ApiError(
        503, "UNSUPPORTED_SCHEMA", "Versão de schema não suportada."
    )


def get_schema_revision_reader(request: Request) -> Callable[[], list[str]]:
    return partial(read_schema_revisions, request.app.state.engine)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready(
    reader: Callable[[], list[str]] = Depends(get_schema_revision_reader),
) -> dict:
    try:
        revisions = reader()
    except DatabaseUnavailableError:
        raise ApiError(503, "DB_UNAVAILABLE", "Banco de dados indisponível.")
    except SchemaUnreadableError as exc:
        logger.warning("Cannot read alembic_version: %s", exc.reason)
        raise _unsupported_schema()

    try:
        check_schema(revisions)
    except UnsupportedSchemaError as exc:
        logger.warning("Unsupported schema revisions: %s", exc.revisions)
        raise _unsupported_schema()

    return {
        "status": "ready",
        "schema_revision": ",".join(sorted(set(revisions))),
    }
