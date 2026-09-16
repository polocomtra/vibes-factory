from fastapi.testclient import TestClient

from apps.api.app.main import app


def test_health_returns_ok_and_request_id() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "vibesfactory-api"}
    assert response.headers["X-Request-ID"].startswith("req_")


def test_health_reuses_valid_request_id() -> None:
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "req_test"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req_test"
