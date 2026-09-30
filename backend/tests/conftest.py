import pytest
from fastapi.testclient import TestClient

from ragnaw.main import app


@pytest.fixture(scope="session")
def client():
    # The context manager runs the lifespan, which loads the search index.
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def index(client):
    return client.app.state.index
