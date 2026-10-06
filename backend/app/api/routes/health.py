"""Health check routes."""

from fastapi import APIRouter, Response, status

from app.db.health import database_is_healthy
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Liveness probe — does not require database connectivity."""
    return HealthResponse(status="healthy")


@router.get("/health/database", response_model=HealthResponse)
def get_database_health(response: Response) -> HealthResponse:
    """Report database connectivity only (``SELECT 1``).

    Never includes hostnames, usernames, passwords, connection strings,
    or Supabase keys in the response body.
    """
    if database_is_healthy():
        return HealthResponse(status="healthy")

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="unhealthy")
