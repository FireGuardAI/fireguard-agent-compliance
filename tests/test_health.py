import os

os.environ.setdefault("GEMINI_API_KEY", "test-key-for-unit-tests")

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
