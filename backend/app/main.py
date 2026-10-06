"""FastAPI application factory and ASGI entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    logger.info(
        "Starting %s (env=%s, database_configured=%s)",
        settings.app_name,
        settings.app_env,
        settings.is_database_configured,
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
    )

    @application.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    application.include_router(api_router)
    return application


app = create_app()
