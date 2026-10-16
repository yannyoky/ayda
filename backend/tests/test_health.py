import httpx
import pytest
from fastapi import FastAPI

from ayda.core.config import Settings
from ayda.main import create_app
from tests.contract import assert_matches


async def test_health_checks_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert_matches(response, "getHealth")


@pytest.fixture
def broken_app() -> FastAPI:
    return create_app(
        Settings(environment="test", database_url="postgresql+asyncpg://nobody:x@127.0.0.1:1/x")
    )


async def test_health_returns_503_problem_without_database(broken_app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=broken_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        response = await c.get("/health")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "https://ayda.app/errors/database-unavailable"
    assert_matches(response, "getHealth")
