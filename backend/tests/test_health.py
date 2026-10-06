"""Application startup and health endpoint tests."""

from fastapi.testclient import TestClient


def test_application_starts(client: TestClient) -> None:
    assert client.app is not None
    assert client.app.title  # type: ignore[union-attr]


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
