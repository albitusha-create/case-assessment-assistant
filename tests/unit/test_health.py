from fastapi.testclient import TestClient

from caa.main import create_app
from caa.storage.store import MemoryStore


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app(store=MemoryStore()))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
