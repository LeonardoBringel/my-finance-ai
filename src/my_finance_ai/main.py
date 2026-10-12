"""App factory, started by uvicorn with --factory (1 worker, port 8000)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import ValidationError

from my_finance_ai.api.errors import register_error_handlers
from my_finance_ai.api.routes.health import router as health_router
from my_finance_ai.config import Settings, format_settings_error, get_settings
from my_finance_ai.data.db import create_db_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        try:
            settings = get_settings()
        except ValidationError as exc:
            for line in format_settings_error(exc).splitlines():
                logger.critical("Invalid configuration: %s", line)
            raise SystemExit(1) from None

    logging.basicConfig(level=settings.LOG_LEVEL)

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = create_db_engine(settings)
    register_error_handlers(app)
    app.include_router(health_router)
    return app
