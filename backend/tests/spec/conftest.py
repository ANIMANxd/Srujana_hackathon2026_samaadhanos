"""Fixtures for the spec suite.

The client is built with `raise_server_exceptions=False` so that if the app
blows up on malformed input, the test sees a 500 *response* and can assert
against it ("clean validation errors, never stack traces") instead of the
test itself dying with the server's traceback.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)
