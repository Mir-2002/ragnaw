from fastapi.testclient import TestClient

from ragnaw.main import app

client = TestClient(app)


def test_health_get():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_health_head():
    # Uptime monitors default to HEAD; a 405 here would mark the Space as down.
    assert client.head("/health").status_code == 200
