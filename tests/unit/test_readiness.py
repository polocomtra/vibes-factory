from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from apps.api.app import main


async def fake_database_check() -> None:
    return None


def test_readiness_returns_database_check(monkeypatch) -> None:
    monkeypatch.setattr(main, "check_database", fake_database_check)

    with TestClient(main.app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


async def failing_database_check() -> None:
    raise SQLAlchemyError("database unavailable")


def test_readiness_returns_service_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(main, "check_database", failing_database_check)

    with TestClient(main.app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_NOT_READY"
    assert response.headers["X-Request-ID"].startswith("req_")


async def os_error_database_check() -> None:
    raise OSError("database socket unavailable")


def test_readiness_handles_low_level_connection_errors(monkeypatch) -> None:
    monkeypatch.setattr(main, "check_database", os_error_database_check)

    with TestClient(main.app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_NOT_READY"
