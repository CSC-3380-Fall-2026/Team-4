
import pytest


@pytest.fixture
def test_catalog():
    """Sample course catalog for testing."""
    return [
        {"course_code": "CSC 1350", "credits": 3},
        {"course_code": "CSC 3380", "credits": 3},
    ]


@pytest.fixture
def test_supabase_users():
    """Fake users for testing without a real database."""
    return [
        {"id": "test-user-1", "email": "student1@example.com"},
        {"id": "test-user-2", "email": "student2@example.com"},
    ]

@pytest.fixture
def test_client():
    """Create a FastAPI client for testing API endpoints."""
    import sys
    from pathlib import Path
    from fastapi.testclient import TestClient

    app_dir = Path(__file__).resolve().parents[1] / "app"
    sys.path.insert(0, str(app_dir))

    from tiger_app import app

    return TestClient(app)
