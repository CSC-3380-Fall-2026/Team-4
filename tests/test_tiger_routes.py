import os
import sys
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from fastapi.testclient import TestClient
from tiger_app import app

client = TestClient(app)


def test_health_route():
    response = client.get("/health")
    assert response.status_code == 200


def test_public_page_routes():
    for path in ["/", "/login", "/signin", "/dashboard", "/schedule", "/planning", "/friends", "/profile"]:
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"
        assert "text/html" in response.headers["content-type"]


def test_unknown_route_returns_404():
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
