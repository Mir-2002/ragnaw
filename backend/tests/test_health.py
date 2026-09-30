def test_health_get(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["data_ready"] is True


def test_health_head(client):
    # Uptime monitors default to HEAD; a 405 here would mark the Space as down.
    assert client.head("/health").status_code == 200
