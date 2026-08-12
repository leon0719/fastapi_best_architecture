"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """TestClient without lifespan (no DB/Redis needed)."""
    from app.main import app

    return TestClient(app)
