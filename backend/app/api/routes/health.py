"""Health check route."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Liveness probe — does not require database connectivity."""
    return HealthResponse(status="healthy")
